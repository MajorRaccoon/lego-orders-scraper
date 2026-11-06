"""Windows app (windows-app/): data folder and log in %LOCALAPPDATA%\\LEGO Order Scraper; the launcher
opens the page in the default browser with a visible console and a working Quit; the scraper and
web UI use the same folder when run directly on Windows; the build files are consistent; and every
copied script (docker/, mac-app/, windows-app/) matches its source. The real .exe is built and
exercised on Windows by .github/workflows/windows-app.yml."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import contextlib, filecmp, io, os, sys, tempfile, types
from pathlib import Path
import unittest.mock as mock
ROOT = Path(SRC)
WIN = ROOT / "windows-app"
if not WIN.is_dir():
    print("SKIPPED: windows-app/ not found next to the scripts"); sys.exit(0)
sandbox = Path(tempfile.mkdtemp(prefix="lego_win_"))
os.environ["LEGO_WORK_DIR"] = str(sandbox / "data")
os.environ["LEGO_LOG_FILE"] = str(sandbox / "test.log")
sys.path.insert(0, str(ROOT / "mac-app"))
sys.path.insert(0, SRC)
import lego_orders_app as app
import lego_orders_scraper as sc

local = sandbox / "AppData" / "Local"

def env(**kw):
    clean = {k: v for k, v in os.environ.items() if not k.startswith("LEGO_")}
    clean.update(kw)
    return mock.patch.dict(os.environ, clean, clear=True)

# --- folders on Windows ----------------------------------------------------
with env(LOCALAPPDATA=str(local)), mock.patch.object(app.platform, "system", return_value="Windows"):
    assert app.support_dir() == local / "LEGO Order Scraper"
    assert app.log_path() == local / "LEGO Order Scraper" / "LEGO Order Scraper.log"
with env(LOCALAPPDATA=str(local)), mock.patch.object(sc.platform, "system", return_value="Windows"):
    assert sc.data_dir() == local / "LEGO Order Scraper"
    assert sc.log_file_path() == local / "LEGO Order Scraper" / "LEGO Order Scraper.log"
with env(LEGO_APP_DATA_DIR=str(sandbox / "override")), mock.patch.object(app.platform, "system", return_value="Windows"):
    assert app.support_dir() == sandbox / "override" and app.log_path() == sandbox / "override" / "app.log"
try:
    import lego_orders_webapp as wa
except ImportError:
    print("(web UI part skipped: flask not installed)")
else:
    with env(LOCALAPPDATA=str(local)), mock.patch.object(wa.platform, "system", return_value="Windows"):
        assert wa._default_work_dir() == local / "LEGO Order Scraper"
print("Windows: app, scraper and web UI all use %LOCALAPPDATA%\\LEGO Order Scraper (+ log there): OK")

# --- the Windows launcher: browser mode, banner, Quit works, console + log --
events = []
fake_web = types.SimpleNamespace(APP_MODE=None, QUIT_HOOK=None, job=types.SimpleNamespace(status="idle"))
fake_server = mock.Mock()
def fake_open(url):
    events.append(("open", url))
    fake_web.QUIT_HOOK()          # the user clicks "Quit app" right away
out = io.StringIO()
real_out, real_err = sys.stdout, sys.stderr
try:
    with env(LEGO_APP_DATA_DIR=str(sandbox / "winapp")), \
         mock.patch.object(app.platform, "system", return_value="Windows"), \
         mock.patch.object(app, "start_server", return_value=(fake_server, fake_web)), \
         mock.patch.object(app, "free_port", return_value=8811), \
         mock.patch.object(app.webbrowser, "open", side_effect=fake_open), \
         mock.patch.object(app.os, "_exit", side_effect=SystemExit), \
         contextlib.redirect_stdout(out):
        try:
            app.run_gui()
        except SystemExit:
            pass
        mode = os.environ["LEGO_APP_MODE"]
finally:
    sys.stdout, sys.stderr = real_out, real_err
assert mode == "browser", mode                                     # page shows "Quit app"
assert events == [("open", "http://127.0.0.1:8811/")]
assert fake_server.shutdown.called                                  # Quit stops the server
banner = out.getvalue()
assert "is running at http://127.0.0.1:8811/" in banner and "close this window" in banner, banner
assert "Your orders are saved in:" in banner
log = (sandbox / "winapp" / "app.log").read_text()
assert "is running at http://127.0.0.1:8811/" in log                # console text also logged
print("Windows launcher: opens the default browser, shows a 'close this window to quit' banner, "
      "Quit stops the server, console output also logged: OK")

# --- build files -------------------------------------------------------------
spec = (WIN / "LEGO_Order_Scraper_win.spec").read_text()
assert '"lego_orders_app.py"' in spec and "console=True" in spec and 'collect_all("playwright")' in spec
assert "win32crypt" in spec and '"webview"' in spec   # pywin32 bundled; pywebview not used on Windows
reqs = (WIN / "requirements-windows.txt").read_text()
assert all(p in reqs for p in ("playwright", "cryptography", "flask", "pywin32", "pyinstaller", "pillow"))
wf = (ROOT / ".github" / "workflows" / "windows-app.yml").read_text()
assert "runs-on: windows-latest" in wf and "--self-test" in wf and "--serve-only" in wf
assert "upload-artifact" in wf and "LEGO-Order-Scraper-windows.zip" in wf and "${{ runner." not in wf.split("steps:")[0]
print("Windows build spec, requirements and GitHub Actions workflow are consistent: OK")

# --- every copy matches its source (a stale copy would be built into an app) --
copies = {d: ["lego_orders_scraper.py", "lego_orders_webapp.py", "lego_orders_to_html.py",
              "lego_repair_json_from_csv.py", "strip_non_ascii.py"] for d in ("docker", "mac-app", "windows-app")}
for d, files in copies.items():
    for f in files:
        assert filecmp.cmp(ROOT / f, ROOT / d / f, shallow=False), f"{d}/{f} is out of date -- run ./sync_copies.sh"
assert filecmp.cmp(ROOT / "mac-app" / "lego_orders_app.py", WIN / "lego_orders_app.py", shallow=False), \
    "windows-app/lego_orders_app.py is out of date -- run ./sync_copies.sh"
print("docker/, mac-app/ and windows-app/ copies all match their sources: OK")
print("\nALL WINDOWS APP TESTS PASSED")
