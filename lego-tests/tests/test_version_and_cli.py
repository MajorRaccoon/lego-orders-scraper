"""__version__ is a whole number, printed at startup, exposed via --version; CLI flags reach scrape()."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import contextlib, datetime, io, subprocess, sys
import unittest.mock as mock
sys.path.insert(0, SRC)
import lego_orders_scraper as sc
import os, tempfile
os.chdir(tempfile.mkdtemp(prefix="lego_cli_"))  # main() writes lego_orders.html by default; keep it out of the repo

assert sc.__version__.isdigit()
out = subprocess.run([sys.executable, SRC + "/lego_orders_scraper.py", "--version"], capture_output=True, text=True)
assert sc.__version__ in out.stdout, out
print("--version prints the version number: OK")

def run_main(argv):
    seen, buf = {}, io.StringIO()
    with mock.patch.object(sc, "scrape", lambda **kw: seen.update(kw) or []), \
         mock.patch.object(sys, "argv", ["x"] + argv), contextlib.redirect_stdout(buf):
        sc.main()
    return seen, buf.getvalue()

seen, text = run_main([])
assert f"v{sc.__version__}" in text.splitlines()[0]
print("version printed on startup: OK")

seen, _ = run_main(["--max-orders", "5", "--headless", "--delay", "2.5", "--load-more-delay", "3",
                    "--load-more-final-wait", "9", "--output", "a.json", "--csv", "a.csv",
                    "--cookie-source", "/p", "--fresh", "--since-date", "03/04/2025", "--no-tracking"])
assert seen == {"max_orders": 5, "headless": True, "delay": 2.5, "load_more_delay": 3.0,
                "load_more_final_wait": 9.0, "cookie_source": "/p", "json_path": "a.json", "csv_path": "a.csv",
                "fresh": True, "since_date": datetime.date(2025, 3, 4), "include_tracking": False}, seen
seen, _ = run_main([])
assert (seen["max_orders"], seen["headless"], seen["delay"], seen["load_more_delay"], seen["load_more_final_wait"],
        seen["json_path"], seen["csv_path"], seen["fresh"], seen["include_tracking"]) == (
        None, False, 1.5, 1.2, 5.0, "lego_orders.json", "lego_orders.csv", False, True)
print("every CLI option reaches scrape(); defaults unchanged: OK")

# --html: writes the report from scrape()'s result
import tempfile, pathlib
hp = pathlib.Path(tempfile.mkdtemp()) / "r.html"
order = sc.LegoOrder(order_number="T1", status="Shipped", order_date="June 1, 2026", total="5.00", item_count_listed=0, url="u")
with mock.patch.object(sc, "scrape", lambda **kw: [order]), mock.patch.object(sys, "argv", ["x", "--html", str(hp)]), \
     contextlib.redirect_stdout(io.StringIO()):
    sc.main()
assert "T1" in hp.read_text()
print("--html writes the HTML report from the run's orders: OK")

# HTML report is ON by default (lego_orders.html in the current folder); --no-html skips it.
here = pathlib.Path(tempfile.mkdtemp(prefix="lego_html_default_"))
os.chdir(here)
with mock.patch.object(sc, "scrape", lambda **kw: [order]), mock.patch.object(sys, "argv", ["x"]), \
     contextlib.redirect_stdout(io.StringIO()) as out:
    sc.main()
assert (here / "lego_orders.html").is_file() and "T1" in (here / "lego_orders.html").read_text()
assert "Wrote lego_orders.html" in out.getvalue()
(here / "lego_orders.html").unlink()
with mock.patch.object(sc, "scrape", lambda **kw: [order]), mock.patch.object(sys, "argv", ["x", "--no-html"]), \
     contextlib.redirect_stdout(io.StringIO()):
    sc.main()
assert not (here / "lego_orders.html").exists()
assert sc.DEFAULT_HTML_PATH == "lego_orders.html"
print("No --html given -> lego_orders.html written by default; --no-html skips it: OK")
print("\nALL VERSION/CLI TESTS PASSED")
