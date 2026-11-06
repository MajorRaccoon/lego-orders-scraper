#!/usr/bin/env python3
"""
lego_orders_app.py -- entry point of the standalone macOS app "LEGO Order Scraper".

Double-clicking the app runs this file (frozen by PyInstaller). It:
  1. picks a user-writable data folder (~/Library/Application Support/LEGO Order Scraper):
     saved orders (JSON/CSV/HTML), the saved LEGO.com login, and the downloaded browser;
  2. starts the web UI (lego_orders_webapp.py) on a free local port, and shows it in a
     native window (pywebview). If a native window can't be created it falls back to
     your default browser, with a "Quit app" button on the page;
  3. when you click Start, the web UI re-runs THIS executable as
         "LEGO Order Scraper" --run-scraper <flags>
     which is dispatched below to lego_orders_scraper.py -- the scraper itself is
     unmodified; the app is the same program you'd run from a terminal.

The scraper's Chromium is downloaded on first use (about 150 MB, once) into the data
folder, not bundled, so the app stays small and signing stays simple.

Debug options (also handy in a terminal):
    "LEGO Order Scraper" --serve-only [--port N]   run just the server, print its URL
    "LEGO Order Scraper" --run-scraper --help      the scraper's own command-line
Log file: ~/Library/Logs/LEGO Order Scraper.log
"""

import os
import platform
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

APP_NAME = "LEGO Order Scraper"


def support_dir():
    override = os.environ.get("LEGO_APP_DATA_DIR")  # tests / power users
    if override:
        return Path(override).expanduser()
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path.home() / ".lego-order-scraper"  # only reached when testing off-Mac


def log_path():
    if platform.system() == "Darwin" and not os.environ.get("LEGO_APP_DATA_DIR"):
        return Path.home() / "Library" / "Logs" / f"{APP_NAME}.log"
    return support_dir() / "app.log"


def configure_environment():
    """Point the scraper/webapp at the data folder. Must run before they are imported
    (they read these variables at import time) and before spawning the scraper (the
    child inherits them). Returns the folders in use."""
    base = support_dir()
    paths = {
        "work": base,
        "profile": base / "lego_browser_profile",
        "browsers": base / "browsers",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    os.environ["LEGO_WORK_DIR"] = str(paths["work"])
    os.environ["LEGO_PROFILE_DIR"] = str(paths["profile"])
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(paths["browsers"])
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    return paths


def _playwright_version():
    try:
        from playwright._repo_version import version
        return version
    except Exception:
        return "unknown"


def ensure_browser():
    """Download Playwright's Chromium into the data folder the first time it's needed.
    A marker file (per Playwright version) records a COMPLETE install, so an
    interrupted download is retried next time instead of being trusted."""
    if os.environ.get("LEGO_SKIP_BROWSER_INSTALL"):
        return
    browsers = Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])
    marker = browsers / f".installed-{_playwright_version()}"
    if marker.exists():
        return
    print(
        "First run: downloading the browser this tool uses (about 150 MB). "
        "This happens once -- please wait...",
        flush=True,
    )
    from playwright._impl._driver import compute_driver_executable, get_driver_env

    node, cli = compute_driver_executable()
    env = {**os.environ, **get_driver_env()}
    result = subprocess.run([str(node), str(cli), "install", "chromium"], env=env)
    if result.returncode != 0:
        raise SystemExit(
            "Couldn't download the browser (check your internet connection) -- "
            "just click Start again to retry."
        )
    marker.write_text("ok")
    print("Browser downloaded.", flush=True)


def run_scraper(args):
    """--run-scraper mode: behave exactly like `python lego_orders_scraper.py <args>`."""
    configure_environment()
    try:  # live output into the web page, even when stdout is a pipe
        sys.stdout.reconfigure(line_buffering=True, write_through=True)
        sys.stderr.reconfigure(line_buffering=True, write_through=True)
    except Exception:
        pass
    if not any(a in ("--version", "-h", "--help") for a in args):
        ensure_browser()
    import lego_orders_scraper

    sys.argv = ["lego_orders_scraper.py", *args]
    try:
        lego_orders_scraper.main()
    except KeyboardInterrupt:
        print("\nInterrupted -- exiting.")
        sys.exit(1)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port):
    from werkzeug.serving import make_server
    import lego_orders_webapp as web

    server = make_server("127.0.0.1", port, web.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, web


def shutdown(web, server):
    """Stop a running scrape gracefully (it saves progress), then the server."""
    job = web.job
    try:
        if job.status == "running":
            try:
                job.stop()
            except Exception:
                pass
            for _ in range(100):  # up to ~10 s for the scraper's graceful stop
                if job.status != "running":
                    break
                time.sleep(0.1)
            if job.status == "running":
                try:
                    job.force_kill()
                except Exception:
                    pass
    finally:
        try:
            server.shutdown()
        except Exception:
            pass


def run_gui(serve_only=False, port=None):
    paths = configure_environment()
    os.environ["LEGO_APP_MODE"] = "window"
    if not serve_only:
        try:  # no terminal under Finder: keep a log instead
            lp = log_path()
            lp.parent.mkdir(parents=True, exist_ok=True)
            sys.stdout = sys.stderr = open(lp, "a", buffering=1, encoding="utf-8")
            print(f"\n--- {APP_NAME} started {time.ctime()} ---")
        except Exception:
            pass

    port = port or free_port()
    server, web = start_server(port)
    url = f"http://127.0.0.1:{port}/"
    print(f"Serving {url} (data folder: {paths['work']})", flush=True)

    if serve_only:
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        shutdown(web, server)
        return

    try:
        import webview

        try:
            webview.settings["ALLOW_DOWNLOADS"] = True
        except Exception:
            pass
        webview.create_window(APP_NAME, url, width=1100, height=920, min_size=(760, 560))
        webview.start()  # blocks until the window is closed
    except Exception as e:
        print(f"Native window unavailable ({e!r}) -- opening in your default browser.", flush=True)
        web.APP_MODE = "browser"
        done = threading.Event()
        web.QUIT_HOOK = done.set
        webbrowser.open(url)
        done.wait()
    shutdown(web, server)
    os._exit(0)  # don't wait on any lingering GUI threads


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--run-scraper":
        run_scraper(argv[1:])
        return
    port = None
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    run_gui(serve_only="--serve-only" in argv, port=port)


if __name__ == "__main__":
    main()
