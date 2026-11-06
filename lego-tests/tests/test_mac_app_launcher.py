"""lego_orders_app.py (macOS app launcher): data-dir/env setup, first-run browser download
logic, --run-scraper dispatch, frozen-app scraper command, --serve-only server, app-mode routes."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import json, os, subprocess, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path
import unittest.mock as mock
APPDIR = SRC if os.path.exists(SRC + "/lego_orders_app.py") else SRC + "/mac-app"
if not os.path.exists(APPDIR + "/lego_orders_app.py"):
    print("SKIPPED: mac-app/lego_orders_app.py not found next to the scripts"); sys.exit(0)
sys.path.insert(0, APPDIR)
if SRC != APPDIR: sys.path.insert(0, SRC)
data = tempfile.mkdtemp(prefix="lego_app_data_")
os.environ["LEGO_APP_DATA_DIR"] = data
import lego_orders_app as app

# --- data folder + environment ------------------------------------------
paths = app.configure_environment()
assert paths["work"] == Path(data) and paths["profile"].is_dir() and paths["browsers"].is_dir()
assert os.environ["LEGO_WORK_DIR"] == data
assert os.environ["LEGO_PROFILE_DIR"] == str(Path(data) / "lego_browser_profile")
assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(Path(data) / "browsers")
print("configure_environment: data/profile/browser folders created, env vars set: OK")

# --- scraper honors LEGO_PROFILE_DIR ------------------------------------
code = f"import sys; sys.path.insert(0, {SRC!r}); import lego_orders_scraper as s; print(s.PROFILE_DIR)"
env = dict(os.environ)
r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
assert r.stdout.strip() == str(Path(data) / "lego_browser_profile"), r
env.pop("LEGO_PROFILE_DIR")
r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
assert r.stdout.strip().endswith("lego_browser_profile") and data not in r.stdout
print("scraper PROFILE_DIR: env override honored, default unchanged: OK")

# --- ensure_browser ------------------------------------------------------
marker = Path(data) / "browsers" / f".installed-{app._playwright_version()}"
with mock.patch.dict(os.environ, {"LEGO_SKIP_BROWSER_INSTALL": "1"}), mock.patch.object(app.subprocess, "run") as run:
    app.ensure_browser(); assert not run.called
print("ensure_browser: skip flag respected: OK")

with mock.patch.object(app.subprocess, "run", return_value=mock.Mock(returncode=1)) as run:
    try: app.ensure_browser(); assert False
    except SystemExit as e: assert "download the browser" in str(e)
    assert run.call_args[0][0][-2:] == ["install", "chromium"]
    assert run.call_args[1]["env"]["PLAYWRIGHT_BROWSERS_PATH"] == str(Path(data) / "browsers")
assert not marker.exists()
print("ensure_browser: failed download -> clear error, no marker (retried next time): OK")

with mock.patch.object(app.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
    app.ensure_browser(); assert run.call_count == 1
assert marker.exists()
with mock.patch.object(app.subprocess, "run") as run:
    app.ensure_browser(); assert not run.called
print("ensure_browser: successful download writes marker; later runs don't re-download: OK")

# --- run_scraper dispatch ------------------------------------------------
import lego_orders_scraper as sc
seen = {}
with mock.patch.object(sc, "main", lambda: seen.update(argv=list(sys.argv))), \
     mock.patch.object(app, "ensure_browser") as eb:
    app.run_scraper(["--max-orders", "3", "--headless"])
assert seen["argv"] == ["lego_orders_scraper.py", "--max-orders", "3", "--headless"] and eb.called
with mock.patch.object(sc, "main", lambda: None), mock.patch.object(app, "ensure_browser") as eb:
    app.run_scraper(["--version"]); assert not eb.called
print("run_scraper: argv passed through; --version/--help don't trigger a download: OK")

r = subprocess.run([sys.executable, APPDIR + "/lego_orders_app.py", "--run-scraper", "--version"],
                   env=dict(os.environ, PYTHONPATH=SRC), capture_output=True, text=True)
assert sc.__version__ in r.stdout, r
print("end-to-end: `lego_orders_app.py --run-scraper --version` reaches the scraper's CLI: OK")

# --- webapp builds the right command when frozen -------------------------
import lego_orders_webapp as web
assert web.scraper_command(["--fresh"])[1:2] == ["-u"] and web.scraper_command(["--fresh"])[-1] == "--fresh"
with mock.patch.object(sys, "frozen", True, create=True):
    assert web.scraper_command(["--fresh"]) == [sys.executable, "--run-scraper", "--fresh"]
print("webapp.scraper_command: python script normally, '--run-scraper' when frozen: OK")

# --- --serve-only server + app-mode routes -------------------------------
proc = subprocess.Popen([sys.executable, APPDIR + "/lego_orders_app.py", "--serve-only"],
                        env=dict(os.environ, PYTHONPATH=SRC), stdout=subprocess.PIPE, text=True)
try:
    url = None
    for _ in range(100):
        line = proc.stdout.readline()
        if line.startswith("Serving "): url = line.split()[1]; break
    assert url and url.startswith("http://127.0.0.1:"), url
    def call(path, method="GET"):
        req = urllib.request.Request(url.rstrip("/") + path, method=method, data=b"" if method == "POST" else None)
        try:
            with urllib.request.urlopen(req, timeout=5) as r: return r.status, r.read()
        except urllib.error.HTTPError as e: return e.code, e.read()
    st, body = call("/config"); cfg = json.loads(body)
    expected_mode = "browser" if sys.platform == "win32" else "window"   # Windows app: page in the default browser
    assert st == 200 and cfg["app_mode"] == expected_mode and os.path.realpath(cfg["work_dir"]) == os.path.realpath(data), cfg  # macOS: /var -> /private/var
    assert call("/")[0] == 200 and b"Open data folder" in call("/")[1]
    assert call("/quit", "POST")[0] == 404          # window mode: no Quit route
    if sys.platform != "darwin": assert call("/reveal", "POST")[0] == 404
    assert json.loads(call("/status")[1])["status"] == "idle"
    print("--serve-only: free port, /config reports app_mode+data folder, /quit disabled in window mode: OK")
finally:
    proc.terminate(); proc.wait(timeout=10)

# --- shutdown helper -------------------------------------------------------
fake = mock.Mock(); fake.job.status = "idle"; srv = mock.Mock()
app.shutdown(fake, srv); assert srv.shutdown.called and not fake.job.stop.called
print("shutdown: idle job just stops the server: OK")
# a job that ignores the graceful stop gets force-killed, then the server stops
fake2 = mock.Mock(); fake2.job.status = "running"; srv2 = mock.Mock()
with mock.patch.object(app.time, "sleep", lambda _: None):
    app.shutdown(fake2, srv2)
assert fake2.job.stop.called and fake2.job.force_kill.called and srv2.shutdown.called
# a job that stops by itself is NOT force-killed
fake3 = mock.Mock(); srv3 = mock.Mock()
fake3.job.status = "running"
fake3.job.stop.side_effect = lambda: setattr(fake3.job, "status", "stopped")
with mock.patch.object(app.time, "sleep", lambda _: None):
    app.shutdown(fake3, srv3)
assert fake3.job.stop.called and not fake3.job.force_kill.called and srv3.shutdown.called
print("shutdown: graceful stop first, force-kill only if it doesn't stop: OK")
print("\nALL MAC APP LAUNCHER TESTS PASSED")
