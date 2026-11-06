"""Output files and the log go to the same places for every version on a Mac:
~/Library/Application Support/LEGO Order Scraper/ and ~/Library/Logs/LEGO Order Scraper.log
(LEGO_WORK_DIR / LEGO_LOG_FILE override them; Docker sets LEGO_WORK_DIR=/data). Relative --output /
--csv / --html paths go in the data folder. Every scrape run is recorded in the log."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import contextlib, io, json, os, subprocess, sys, tempfile
from pathlib import Path
import unittest.mock as mock
sandbox = Path(tempfile.mkdtemp(prefix="lego_datafolder_"))
os.environ["LEGO_WORK_DIR"] = str(sandbox / "data")
os.environ["LEGO_LOG_FILE"] = str(sandbox / "logs" / "test.log")
sys.path.insert(0, SRC)
import lego_orders_scraper as sc

HOME = Path.home()
MAC_DATA = HOME / "Library" / "Application Support" / "LEGO Order Scraper"
MAC_LOG = HOME / "Library" / "Logs" / "LEGO Order Scraper.log"

def env(**kw):
    """Patch os.environ for the LEGO_ variables only (others untouched)."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith("LEGO_")}
    clean.update(kw)
    return mock.patch.dict(os.environ, clean, clear=True)

# --- data folder ---------------------------------------------------------
with env(), mock.patch.object(sc.platform, "system", return_value="Darwin"):
    assert sc.data_dir() == MAC_DATA and sc.log_file_path() == MAC_LOG
with env(), mock.patch.object(sc.platform, "system", return_value="Linux"):
    assert sc.data_dir() == Path.cwd() and sc.log_file_path() is None
with env(LEGO_WORK_DIR="/data", LEGO_LOG_FILE=""), mock.patch.object(sc.platform, "system", return_value="Darwin"):
    assert sc.data_dir() == Path("/data") and sc.log_file_path() is None   # Docker-style folder; blank = no log
print("Mac default: Application Support folder + ~/Library/Logs log; LEGO_WORK_DIR / LEGO_LOG_FILE override; "
      "elsewhere: current folder, no log: OK")

with env(LEGO_WORK_DIR=str(sandbox / "d")):
    assert sc.resolve_output_path("lego_orders.json") == sandbox / "d" / "lego_orders.json"
    assert sc.resolve_output_path("/tmp/x.json") == Path("/tmp/x.json")
    assert sc.resolve_output_path("~/x.json") == HOME / "x.json"
print("Relative paths go in the data folder; absolute and ~ paths are used as given: OK")

# --- web UI uses the same folder, and hands it to each scrape -------------
try:
    import lego_orders_webapp as wa
except ImportError:
    print("SKIPPED web UI part: flask not installed")
else:
    for e in ({}, {"LEGO_WORK_DIR": "/data"}):
        with env(**e), mock.patch.object(wa.platform, "system", return_value="Darwin"), \
             mock.patch.object(sc.platform, "system", return_value="Darwin"):
            assert wa._default_work_dir() == sc.data_dir(), e
    assert wa.scraper_env()["LEGO_WORK_DIR"] == str(wa.WORK_DIR)
    assert "LEGO_LOG_FILE" not in wa.scraper_env() or wa.scraper_env()["LEGO_LOG_FILE"] != ""
    with mock.patch.object(wa, "APP_MODE", "window"):
        assert wa.scraper_env()["LEGO_LOG_FILE"] == ""   # Python Mac app: its own log already has every line
    print("Web UI: same folder rule as the scraper; scrapes get LEGO_WORK_DIR; no double logging in the Python Mac app: OK")

# --- a real CLI run (scrape() faked): files in the data folder, run recorded in the log ---
order = sc.LegoOrder(order_number="T1", status="Shipped", order_date="June 1, 2026", total="5.00",
                     item_count_listed=0, url="u")
data, log = sandbox / "run" / "data", sandbox / "run" / "logs" / "LEGO Order Scraper.log"
seen = {}
out = io.StringIO()
real_stdout, real_stderr = sys.stdout, sys.stderr
try:
    with env(LEGO_WORK_DIR=str(data), LEGO_LOG_FILE=str(log)), \
         mock.patch.object(sc, "scrape", lambda **kw: (seen.update(kw), print("scraping...")) and [order]), \
         mock.patch.object(sys, "argv", ["x"]), contextlib.redirect_stdout(out):
        sc.main()
finally:
    sys.stdout, sys.stderr = real_stdout, real_stderr   # main() wraps them to also write the log
assert seen["json_path"] == str(data / "lego_orders.json") and seen["csv_path"] == str(data / "lego_orders.csv")
assert (data / "lego_orders.html").is_file() and data.is_dir()
text = log.read_text()
assert "===== " in text and f"lego_orders_scraper.py v{sc.__version__} =====" in text
assert f"Output folder: {data}" in text and "scraping..." in text and f"Wrote {data / 'lego_orders.html'}" in text
assert "scraping..." in out.getvalue() and f"Log file: {log}" in out.getvalue()   # still shown on screen too
print("CLI run: outputs in the data folder (created if missing); everything printed also goes to the log: OK")

# --- helper scripts read/write the data folder by default ------------------
hd = sandbox / "helpers"
hd.mkdir()
(hd / "lego_orders.json").write_text(json.dumps([order.to_dict()]))
r = subprocess.run([sys.executable, f"{SRC}/lego_orders_to_html.py"], cwd=sandbox, capture_output=True, text=True,
                   env={**os.environ, "LEGO_WORK_DIR": str(hd)})
assert r.returncode == 0, r.stderr
assert (hd / "lego_orders.html").is_file() and not (sandbox / "lego_orders.html").exists()
print("lego_orders_to_html.py with no arguments uses the data folder, not the current folder: OK")
print("\nALL DATA-FOLDER TESTS PASSED")
