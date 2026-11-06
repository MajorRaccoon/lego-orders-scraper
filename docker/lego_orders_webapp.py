#!/usr/bin/env python3
"""
lego_orders_webapp.py

A local web-based front end for lego_orders_scraper.py: one page where you
fill in the same options the command line takes, click Start, and watch
progress (which order / item is being fetched, login prompts, errors, the
final summary -- everything the CLI normally prints) live in the browser,
instead of only in a terminal.

This is a thin wrapper, not a rewrite of the scraper: clicking Start simply
launches

    python3 lego_orders_scraper.py <the same flags you'd type yourself>

as a subprocess, exactly as if you'd run it from a terminal, and streams its
output back to the page. lego_orders_scraper.py itself is completely
unmodified -- every existing feature (resuming, --since-date, --html,
--cookie-source, --fresh, etc.) works exactly the same through this
interface, because it IS that same interface underneath.

SETUP
-----
    pip install flask
(lego_orders_scraper.py's own requirements -- playwright, cryptography,
and on Windows pywin32 for --cookie-source -- are unchanged and still apply;
see its own docstring.)

USAGE
-----
    python lego_orders_webapp.py                  # serves http://127.0.0.1:8765
    python lego_orders_webapp.py --port 9000       # use a different port
    python lego_orders_webapp.py --no-browser      # don't auto-open a browser tab

Only listens on 127.0.0.1 (your own machine) by default -- it's not exposed
to your network, and there's no login/auth on it, so don't change that
(--host exists only for the Docker image, see Dockerfile / README-docker.md).

FIRST-TIME LOGIN
-----------------
When you click Start (unless you're reusing a --cookie-source or already
have a saved browser profile), a real Chromium window still opens on this
same machine, exactly like running the script from a terminal. Log in to
LEGO.com by hand in THAT window, then come back to this page and click
"I've logged in, continue" -- that's the same "Press Enter..." step the CLI
asks for, just as a button here instead of your terminal.

ONE JOB AT A TIME
------------------
This supports a single scrape running at a time (it's a personal tool for
one LEGO account) -- Start is disabled while a job is already running.
"""

import argparse
import json
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file

__version__ = "5"  # this webapp's own version, independent of lego_orders_scraper.py's

SCRIPT_DIR = Path(__file__).resolve().parent
SCRAPER_PATH = SCRIPT_DIR / "lego_orders_scraper.py"

# Where the scraper runs (so where relative --output/--csv/--html paths land
# and where the download links look). Defaults to this script's own folder,
# exactly as before; the Docker image sets LEGO_WORK_DIR=/data so results
# live on a mounted volume instead of inside the (disposable) container.
WORK_DIR = Path(os.environ.get("LEGO_WORK_DIR") or SCRIPT_DIR).resolve()

# Docker only: the port the in-container browser view (noVNC) is served on,
# so the page can link to it. Unset everywhere else -> no link shown.
NOVNC_PORT = os.environ.get("LEGO_NOVNC_PORT")

# Set by the macOS app launcher (lego_orders_app.py): "window" (native window)
# or "browser" (fallback: opened in the default browser). Unset otherwise.
APP_MODE = os.environ.get("LEGO_APP_MODE")
QUIT_HOOK = None  # the launcher installs a function here so /quit can shut the app down

# Mirrors lego_orders_scraper.py's own argparse defaults, so the "download
# this run's output" links know where to look even when the user left the
# output-path fields blank (in which case build_argv() omits the flag
# entirely and the scraper falls back to these same defaults itself).
_DEFAULT_OUTPUT_PATHS = {"output": "lego_orders.json", "csv": "lego_order_items.csv"}

# Pre-filled in the form's "Since date" box. Must match DEFAULT_SINCE_DATE in
# lego_orders_scraper.py (test_since_date_default.py checks they agree).
DEFAULT_SINCE_DATE = "02/01/2024"

_SINCE_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def build_argv(config):
    """Translate the web form's config dict into the exact argv
    lego_orders_scraper.py's own --help documents, so this interface and
    the CLI always stay in lockstep -- every option here is spelled exactly
    the way the CLI already expects it. Raises ValueError (with a
    user-facing message) for anything that won't parse, so /start can
    report a clear error before ever spawning a process."""
    argv = []

    def _opt_str(key, flag):
        value = config.get(key)
        if value is None:
            return
        value = str(value).strip()
        if value:
            argv.extend([flag, value])

    def _opt_number(key, flag, kind):
        value = config.get(key)
        if value in (None, ""):
            return
        try:
            parsed = int(float(value)) if kind is int else float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{flag} must be a number, got {value!r}")
        argv.extend([flag, str(parsed)])

    def _flag(key, flag):
        if config.get(key):
            argv.append(flag)

    _opt_number("max_orders", "--max-orders", int)
    _flag("headless", "--headless")
    _opt_number("delay", "--delay", float)
    _opt_number("load_more_delay", "--load-more-delay", float)
    _opt_number("load_more_final_wait", "--load-more-final-wait", float)
    _opt_str("output", "--output")
    _opt_str("csv", "--csv")
    _opt_str("cookie_source", "--cookie-source")
    _flag("fresh", "--fresh")

    # Key absent -> flag omitted (scraper uses its own default). Key present
    # but blank -> the user cleared the box on purpose: fetch everything.
    since_date = config.get("since_date")
    if since_date is not None and not str(since_date).strip():
        argv.extend(["--since-date", "all"])
    elif since_date is not None:
        since_date = str(since_date).strip()
        if since_date.lower() in ("all", "none"):
            argv.extend(["--since-date", "all"])
        elif not _SINCE_DATE_RE.match(since_date):
            raise ValueError(f"--since-date must be MM/DD/YYYY (or blank/'all' for no cutoff), got {since_date!r}")
        else:
            argv.extend(["--since-date", since_date])

    _opt_str("html", "--html")

    return argv


def scraper_command(argv):
    """The command that runs lego_orders_scraper.py with `argv`. Normally that's
    the current Python running the script. Inside the frozen macOS app,
    sys.executable is the app itself (not a Python), so the app is re-run
    with --run-scraper and lego_orders_app.py dispatches to the scraper."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-scraper", *argv]
    return [sys.executable, "-u", str(SCRAPER_PATH), *argv]


class ScrapeJob:
    """Tracks (at most) one running lego_orders_scraper.py subprocess: its
    output lines, for the web page's live log, and its exit state. All
    state is behind one lock since the Flask dev server may field requests
    (/start, /status, /stop, ...) from more than one thread at once, and a
    background thread is continuously reading the subprocess's output."""

    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.reader_thread = None
        self.log_lines = []
        # The line currently being written by the subprocess but not yet
        # newline-terminated -- notably, input()'s own prompt (e.g.
        # "Press Enter once you're signed in...") is written WITHOUT a
        # trailing newline while it waits, so without tracking this
        # separately that prompt would never show up on the page until
        # after the user had already answered it, defeating the point.
        self.partial_line = ""
        self.status = "idle"  # idle | running | finished | error | stopped
        self.return_code = None
        self.config = None  # the config dict the current/last run used
        self.interrupt_count = 0
        self.stop_requested = False

    def start(self, config):
        with self.lock:
            if self.status == "running":
                raise RuntimeError("A scrape is already running.")
            argv = build_argv(config)  # ValueError propagates to the caller as-is
            self.log_lines = []
            self.partial_line = ""
            self.status = "running"
            self.return_code = None
            self.config = dict(config)
            self.interrupt_count = 0
            self.stop_requested = False

        cmd = scraper_command(argv)
        popen_kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=str(WORK_DIR),
        )
        if platform.system() == "Windows":
            # Needed so a later Stop can send CTRL_BREAK_EVENT to just this
            # child (and not to this webapp process's own console group).
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        self._append_line(f"$ {' '.join(cmd)}")
        self.process = subprocess.Popen(cmd, **popen_kwargs)

        self.reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self.reader_thread.start()

    def _append_line(self, line):
        with self.lock:
            self.log_lines.append(line)
            self.partial_line = ""
        print(line)  # also mirror to this webapp's own terminal, not just the page

    def _set_partial(self, text):
        with self.lock:
            self.partial_line = text

    def _read_output(self):
        # Deliberately NOT line-buffered (no readline()/iterating a file
        # object as lines): a prompt like input()'s own (e.g. "Press Enter
        # once you're signed in...") is written WITHOUT a trailing newline
        # while it waits for an answer, and readline() blocks until it
        # sees one -- so reading line-at-a-time would leave that prompt
        # invisible on the page until after the user had already answered
        # it. Reading one character at a time instead surfaces it (and any
        # other no-newline-yet output) immediately, via partial_line.
        process = self.process
        buf = ""
        try:
            while True:
                ch = process.stdout.read(1)
                if ch == "":
                    break  # EOF
                if ch == "\n":
                    self._append_line(buf)
                    buf = ""
                else:
                    buf += ch
                    self._set_partial(buf)
        finally:
            if buf:
                self._append_line(buf)
            try:
                process.stdout.close()
            except Exception:
                pass
            return_code = process.wait()
            with self.lock:
                self.return_code = return_code
                if self.stop_requested:
                    self.status = "stopped"
                elif return_code == 0:
                    self.status = "finished"
                else:
                    self.status = "error"
            self._append_line(f"\n[process exited with code {return_code}]")

    def send_enter(self, text=""):
        with self.lock:
            process = self.process
            running = self.status == "running"
        if not running or process is None or process.stdin is None:
            raise RuntimeError("No scrape is running.")
        try:
            process.stdin.write(text + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"Couldn't send input to the running scrape: {e}")

    def stop(self):
        """Send the same interrupt the CLI's own Ctrl+C handling expects:
        the scraper already does a graceful stop (finish the current step,
        save, close the browser) on the 1st and an immediate exit on the
        2nd, so forwarding each Stop click as one more signal just reuses
        that existing, already-tested logic instead of re-implementing it."""
        with self.lock:
            process = self.process
            running = self.status == "running"
            self.stop_requested = True
            self.interrupt_count += 1
            count = self.interrupt_count
        if not running or process is None:
            raise RuntimeError("No scrape is running.")
        if platform.system() == "Windows":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGINT)
        self._append_line(f"\n[Stop requested -- sent Ctrl+C (#{count}) to the running scrape]")

    def force_kill(self):
        """Last-resort escape hatch if the process doesn't respond to Stop
        (e.g. it's stuck in something that doesn't check for interrupts).
        May leave the browser window open or the profile folder locked --
        Stop is always the better choice when it works."""
        with self.lock:
            process = self.process
            running = self.status == "running"
            self.stop_requested = True
        if not running or process is None:
            raise RuntimeError("No scrape is running.")
        process.kill()
        self._append_line("\n[Force-killed the scrape process]")

    def snapshot(self, since=0):
        with self.lock:
            lines = self.log_lines[max(since, 0):]
            return {
                "status": self.status,
                "return_code": self.return_code,
                "next_index": len(self.log_lines),
                "lines": lines,
                "partial": self.partial_line,
            }

    def available_downloads(self):
        if not self.config:
            return {}
        files = {}
        for kind, config_key in (("json", "output"), ("csv", "csv"), ("html", "html")):
            raw_path = self.config.get(config_key) or _DEFAULT_OUTPUT_PATHS.get(config_key)
            if not raw_path:
                continue
            path = Path(raw_path)
            if not path.is_absolute():
                path = WORK_DIR / path
            if path.is_file():
                files[kind] = str(path)
        return files


job = ScrapeJob()

app = Flask(__name__)


@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")


@app.route("/config")
def config_route():
    return jsonify({"novnc_port": NOVNC_PORT, "work_dir": str(WORK_DIR), "app_mode": APP_MODE})


@app.route("/reveal", methods=["POST"])
def reveal_route():
    """macOS app only: open the data folder (saved orders, login) in Finder."""
    if not APP_MODE or platform.system() != "Darwin":
        return jsonify({"ok": False, "error": "Only available in the macOS app."}), 404
    subprocess.Popen(["open", str(WORK_DIR)])
    return jsonify({"ok": True})


@app.route("/quit", methods=["POST"])
def quit_route():
    """App running in the default browser (no window to close): quit it."""
    if APP_MODE != "browser" or QUIT_HOOK is None:
        return jsonify({"ok": False, "error": "Not available."}), 404
    threading.Timer(0.3, QUIT_HOOK).start()
    return jsonify({"ok": True})


@app.route("/start", methods=["POST"])
def start_route():
    config = request.get_json(force=True, silent=True) or {}
    try:
        job.start(config)
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True})


@app.route("/input", methods=["POST"])
def input_route():
    data = request.get_json(force=True, silent=True) or {}
    try:
        job.send_enter(data.get("text", ""))
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    return jsonify({"ok": True})


@app.route("/stop", methods=["POST"])
def stop_route():
    try:
        job.stop()
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    return jsonify({"ok": True})


@app.route("/kill", methods=["POST"])
def kill_route():
    try:
        job.force_kill()
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 409
    return jsonify({"ok": True})


@app.route("/status")
def status_route():
    since = request.args.get("since", default=0, type=int)
    snap = job.snapshot(since=since)
    snap["files"] = job.available_downloads()
    return jsonify(snap)


@app.route("/events")
def events_route():
    since = request.args.get("since", default=0, type=int)

    def _stream():
        idx = since
        last_status = None
        last_partial = None
        idle_cycles = 0
        while True:
            snap = job.snapshot(since=idx)
            changed = False
            if snap["lines"]:
                changed = True
                for line in snap["lines"]:
                    yield f"data: {json.dumps({'type': 'line', 'text': line})}\n\n"
                idx = snap["next_index"]
            if snap["partial"] != last_partial:
                changed = True
                last_partial = snap["partial"]
                yield f"data: {json.dumps({'type': 'partial', 'text': snap['partial']})}\n\n"
            if snap["status"] != last_status:
                changed = True
                last_status = snap["status"]
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "status",
                            "status": snap["status"],
                            "return_code": snap["return_code"],
                            "files": job.available_downloads(),
                        }
                    )
                    + "\n\n"
                )
            if snap["status"] != "running" and not snap["lines"] and not snap["partial"]:
                # Terminal state, fully drained -- nothing more will ever
                # arrive, so stop holding the connection open.
                break
            idle_cycles = 0 if changed else idle_cycles + 1
            if idle_cycles and idle_cycles % 40 == 0:  # ~ every 14s at the 0.35s poll below
                yield ": keep-alive\n\n"
            time.sleep(0.35)

    return Response(_stream(), mimetype="text/event-stream")


@app.route("/download/<kind>")
def download_route(kind):
    files = job.available_downloads()
    path = files.get(kind)
    if not path or not Path(path).is_file():
        return jsonify({"ok": False, "error": "No such file for this run."}), 404
    return send_file(path, as_attachment=True)


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LEGO Order Scraper</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f7f7f5; --panel: #ffffff; --text: #1d1d1f; --muted: #6b6b70;
    --border: #e3e3e0; --accent: #d01012; --accent-soft: #fdeceb;
    --ok: #1c7c3c; --ok-soft: #e7f6ec; --warn: #9a6700; --warn-soft: #fff3d6;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #17171a; --panel: #212125; --text: #ededf0; --muted: #9a9aa2;
      --border: #313136; --accent: #ff5a5c; --accent-soft: #3a1e1f;
      --ok: #4ade80; --ok-soft: #123a22; --warn: #e6b34d; --warn-soft: #3a2f10;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 16px 64px; background: var(--bg); color: var(--text);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }
  .wrap { max-width: 880px; margin: 0 auto; }
  h1 { font-size: 1.5em; margin: 0 0 4px; }
  .sub { color: var(--muted); font-size: 0.92em; margin: 0 0 24px; }
  .panel {
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 18px 20px; margin-bottom: 20px;
  }
  .panel h2 { font-size: 1em; margin: 0 0 14px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 14px 18px; }
  label { display: block; font-size: 0.85em; color: var(--muted); margin-bottom: 4px; }
  input[type=text], input[type=number] {
    width: 100%; padding: 7px 9px; border: 1px solid var(--border); border-radius: 7px;
    background: var(--bg); color: var(--text); font-size: 0.95em;
  }
  .field { margin-bottom: 2px; }
  .hint { font-size: 0.78em; color: var(--muted); margin-top: 3px; }
  .check { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
  .check label { margin: 0; color: var(--text); font-size: 0.95em; }
  .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; align-items: center; }
  button {
    font-size: 0.92em; font-weight: 600; padding: 9px 16px; border-radius: 8px; border: 1px solid transparent;
    cursor: pointer;
  }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn-start { background: var(--accent); color: white; }
  .btn-secondary { background: var(--bg); color: var(--text); border-color: var(--border); }
  .btn-danger { background: var(--bg); color: var(--accent); border-color: var(--accent); }
  .status-pill {
    display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 999px;
    font-size: 0.85em; font-weight: 600; background: var(--bg); border: 1px solid var(--border); color: var(--muted);
  }
  .status-pill.running { background: var(--warn-soft); color: var(--warn); border-color: transparent; }
  .status-pill.finished { background: var(--ok-soft); color: var(--ok); border-color: transparent; }
  .status-pill.error, .status-pill.stopped { background: var(--accent-soft); color: var(--accent); border-color: transparent; }
  #log {
    background: #101012; color: #d7d7da; border-radius: 10px; padding: 14px 16px; height: 360px;
    overflow-y: auto; font: 12.5px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    white-space: pre-wrap; word-break: break-word;
  }
  #downloads a {
    display: inline-block; margin-right: 12px; color: var(--accent); text-decoration: none; font-size: 0.92em;
  }
  #downloads a:hover { text-decoration: underline; }
  .msg {
    display: none; margin-top: 10px; padding: 10px 12px; border-radius: 8px;
    background: var(--accent-soft); color: var(--accent); font-size: 0.88em;
  }
  .login-note {
    display: none; margin-top: 10px; padding: 10px 12px; border-radius: 8px;
    background: var(--warn-soft); color: var(--warn); font-size: 0.88em;
  }
</style>
</head>
<body>
<div class="wrap">
  <h1>LEGO Order Scraper</h1>
  <p class="sub">A web front end for lego_orders_scraper.py -- set your options, click Start, watch it run.</p>

  <div class="panel">
    <h2>Options</h2>
    <div class="grid">
      <div class="field">
        <label for="max_orders">Max orders</label>
        <input type="number" id="max_orders" step="1" min="0" placeholder="all">
        <div class="hint">Leave blank to fetch every order.</div>
      </div>
      <div class="field">
        <label for="delay">Delay between order pages (s)</label>
        <input type="number" id="delay" step="0.1" min="0" value="1.5">
      </div>
      <div class="field">
        <label for="load_more_delay">Delay after "Load More" (s)</label>
        <input type="number" id="load_more_delay" step="0.1" min="0" value="1.2">
      </div>
      <div class="field">
        <label for="load_more_final_wait">Final wait for "Load More" (s)</label>
        <input type="number" id="load_more_final_wait" step="0.5" min="0" value="5.0">
      </div>
      <div class="field">
        <label for="since_date">Since date (MM/DD/YYYY)</label>
        <input type="text" id="since_date" value="02/01/2024" placeholder="blank = all orders" pattern="\d{1,2}/\d{1,2}/\d{4}">
        <div class="hint">Only fetch item detail for orders on/after this date. Clear it to fetch every order.</div>
      </div>
      <div class="field">
        <label for="output">Output JSON path</label>
        <input type="text" id="output" value="lego_orders.json">
      </div>
      <div class="field">
        <label for="csv">Output CSV path</label>
        <input type="text" id="csv" value="lego_order_items.csv">
      </div>
      <div class="field">
        <label for="html">HTML report path</label>
        <input type="text" id="html" placeholder="e.g. lego_orders.html">
        <div class="hint">Leave blank to skip the HTML report.</div>
      </div>
      <div class="field">
        <label for="cookie_source">Cookie source (optional)</label>
        <input type="text" id="cookie_source" placeholder="path to another Chrome profile">
      </div>
    </div>
    <div class="check">
      <input type="checkbox" id="headless">
      <label for="headless">Headless (only works once already logged in)</label>
    </div>
    <div class="check">
      <input type="checkbox" id="fresh">
      <label for="fresh">Fresh (ignore saved progress, refetch everything)</label>
    </div>

    <div class="actions">
      <button class="btn-start" id="btnStart">Start</button>
      <button class="btn-secondary" id="btnEnter">I've logged in, continue</button>
      <button class="btn-secondary" id="btnStop" disabled>Stop</button>
      <button class="btn-danger" id="btnKill" disabled>Force quit</button>
      <button class="btn-secondary" id="btnReveal" style="display:none">Open data folder</button>
      <button class="btn-secondary" id="btnQuit" style="display:none">Quit app</button>
      <span class="status-pill" id="statusPill">idle</span>
    </div>
    <div class="msg" id="msgBox"></div>
    <div class="login-note" id="loginNote">
      A browser window should have opened on this machine. Log in to LEGO.com
      there, then click "I've logged in, continue" above.
      <span id="novncHint" style="display:none">
        (Running in Docker: <a id="novncLink" href="#" target="_blank" rel="noopener">open the browser view</a>.)
      </span>
    </div>
  </div>

  <div class="panel">
    <h2>Progress</h2>
    <div id="log"></div>
    <div id="downloads" style="margin-top:12px;"></div>
  </div>
</div>

<script>
const $ = (id) => document.getElementById(id);
const logEl = $("log");
const statusPill = $("statusPill");
const btnStart = $("btnStart");
const btnStop = $("btnStop");
const btnKill = $("btnKill");
const btnEnter = $("btnEnter");
const loginNote = $("loginNote");

let nextIndex = 0;
let evtSource = null;
let finalizedLines = [];
let partialText = "";

function renderLog() {
  const atBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 8;
  let text = finalizedLines.join("\n");
  if (partialText) text += (text ? "\n" : "") + partialText;
  logEl.textContent = text;
  if (atBottom) logEl.scrollTop = logEl.scrollHeight;
  if (/press enter once you're signed in/i.test(partialText) ||
      finalizedLines.some((l) => /press enter once you're signed in/i.test(l))) {
    loginNote.style.display = "block";
  }
}

function appendLine(text) {
  finalizedLines.push(text);
  renderLog();
}

function setPartial(text) {
  partialText = text;
  renderLog();
}

function setStatus(status) {
  statusPill.textContent = status;
  statusPill.className = "status-pill " + status;
  const running = status === "running";
  btnStart.disabled = running;
  btnStop.disabled = !running;
  btnKill.disabled = !running;
  btnEnter.disabled = !running;
  if (!running) loginNote.style.display = "none";
}

function renderDownloads(files) {
  const el = $("downloads");
  el.innerHTML = "";
  const labels = {json: "Download JSON", csv: "Download CSV", html: "Download HTML report"};
  for (const kind of ["json", "csv", "html"]) {
    if (files && files[kind]) {
      const a = document.createElement("a");
      a.href = "/download/" + kind;
      a.textContent = labels[kind];
      el.appendChild(a);
    }
  }
}

// Inline replacements for alert()/confirm(): native dialogs aren't reliable in
// every embedded web view, and a page-level message is friendlier anyway.
function showMessage(text) {
  const box = $("msgBox");
  box.textContent = text || "";
  box.style.display = text ? "block" : "none";
}

// Two-step button: first click arms it (label changes), second click within 4s acts.
function confirmClick(btn, armedLabel, action) {
  if (btn.dataset.armed) {
    clearTimeout(Number(btn.dataset.armed));
    delete btn.dataset.armed;
    btn.textContent = btn.dataset.label;
    action();
    return;
  }
  btn.dataset.label = btn.textContent;
  btn.textContent = armedLabel;
  btn.dataset.armed = String(setTimeout(() => {
    delete btn.dataset.armed;
    btn.textContent = btn.dataset.label;
  }, 4000));
}

function collectConfig() {
  return {
    max_orders: $("max_orders").value,
    delay: $("delay").value,
    load_more_delay: $("load_more_delay").value,
    load_more_final_wait: $("load_more_final_wait").value,
    since_date: $("since_date").value,
    output: $("output").value,
    csv: $("csv").value,
    html: $("html").value,
    cookie_source: $("cookie_source").value,
    headless: $("headless").checked,
    fresh: $("fresh").checked,
  };
}

function connectStream() {
  if (evtSource) evtSource.close();
  evtSource = new EventSource("/events?since=" + nextIndex);
  evtSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "line") {
      appendLine(msg.text);
      nextIndex += 1;
    } else if (msg.type === "partial") {
      setPartial(msg.text);
    } else if (msg.type === "status") {
      setStatus(msg.status);
      renderDownloads(msg.files);
      if (msg.status !== "running") {
        evtSource.close();
        evtSource = null;
      }
    }
  };
  evtSource.onerror = () => {
    // The connection closes normally once a terminal status is reached;
    // for any other drop, just stop trying rather than spamming retries.
    if (evtSource) { evtSource.close(); evtSource = null; }
  };
}

async function refreshStatus() {
  const res = await fetch("/status?since=0");
  const snap = await res.json();
  finalizedLines = snap.lines;
  partialText = snap.partial || "";
  renderLog();
  nextIndex = snap.next_index;
  setStatus(snap.status);
  renderDownloads(snap.files);
  if (snap.status === "running") connectStream();
}

btnStart.addEventListener("click", async () => {
  const res = await fetch("/start", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(collectConfig()),
  });
  const data = await res.json();
  if (!data.ok) { showMessage(data.error); return; }
  showMessage("");
  finalizedLines = [];
  partialText = "";
  renderLog();
  nextIndex = 0;
  setStatus("running");
  connectStream();
});

btnStop.addEventListener("click", () => fetch("/stop", {method: "POST"}));
btnKill.addEventListener("click", () => {
  confirmClick(btnKill, "Click again to force quit", () => fetch("/kill", {method: "POST"}));
});
btnEnter.addEventListener("click", () => fetch("/input", {
  method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({text: ""}),
}));

fetch("/config").then((r) => r.json()).then((cfg) => {
  if (cfg.app_mode) {
    $("btnReveal").style.display = "inline-block";
    $("btnReveal").onclick = () => fetch("/reveal", {method: "POST"});
  }
  if (cfg.app_mode === "browser") {
    $("btnQuit").style.display = "inline-block";
    $("btnQuit").onclick = () => {
      confirmClick($("btnQuit"), "Click again to quit", () => {
        fetch("/quit", {method: "POST"}).then(() => { document.body.innerHTML = "<p style='padding:2em'>App closed. You can close this tab.</p>"; });
      });
    };
  }
  if (cfg.novnc_port) {
    const url = location.protocol + "//" + location.hostname + ":" + cfg.novnc_port +
      "/vnc.html?autoconnect=1&resize=scale";
    $("novncLink").href = url;
    $("novncHint").style.display = "inline";
  }
}).catch(() => {});

refreshStatus();
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(
        description="Run a local web front end for lego_orders_scraper.py."
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    parser.add_argument("--port", type=int, default=8765,
        help="Port to serve on (default 8765; not 5000, which macOS AirPlay Receiver "
        "occupies and answers with a 403).")
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Address to listen on (default 127.0.0.1 = this machine only). "
        "There is NO login on this page, so only change this inside a "
        "container whose published port you've restricted yourself (the "
        "provided Docker setup does exactly that).",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Don't automatically open a browser tab on startup.",
    )
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/"
    print(f"lego_orders_webapp.py v{__version__}")
    print(f"Serving at {url} (Ctrl+C to stop)")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(host=args.host, port=args.port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
