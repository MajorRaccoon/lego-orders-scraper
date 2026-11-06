"""The CSV's default name is lego_orders.csv (matching lego_orders.json / lego_orders.html) in the
CLI, web UI and helper scripts; an old lego_order_items.csv is renamed once so it isn't left stale."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import contextlib, io, re, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, SRC)
import lego_orders_scraper as sc

assert sc.DEFAULT_CSV_PATH == "lego_orders.csv" and sc.DEFAULT_HTML_PATH == "lego_orders.html"
assert Path(sc.DEFAULT_CSV_PATH).stem == Path(sc.DEFAULT_HTML_PATH).stem == "lego_orders"
help_text = subprocess.run([sys.executable, f"{SRC}/lego_orders_scraper.py", "--help"], capture_output=True, text=True).stdout
assert "lego_order_items" not in help_text
print("CLI default CSV is lego_orders.csv (same base name as the JSON and HTML): OK")

try:
    import lego_orders_webapp as wa
except ImportError:
    print("SKIPPED web UI part: flask not installed")
else:
    assert wa._DEFAULT_OUTPUT_PATHS["csv"] == "lego_orders.csv"
    assert re.search(r'id="csv" value="lego_orders\.csv"', wa.INDEX_HTML)
    print("Web UI: CSV box pre-filled with lego_orders.csv, downloads look for it: OK")

for script in ("lego_repair_json_from_csv.py", "strip_non_ascii.py"):
    assert "lego_order_items" not in Path(SRC, script).read_text(), script
print("Helper scripts use the new name: OK")

# One-time rename of an old lego_order_items.csv.
tmp = Path(tempfile.mkdtemp(prefix="lego_csvname_"))
(tmp / "lego_order_items.csv").write_text("OLD")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    assert sc._rename_old_csv(tmp / "lego_orders.csv") is True
assert (tmp / "lego_orders.csv").read_text() == "OLD" and not (tmp / "lego_order_items.csv").exists()
assert "Renamed lego_order_items.csv to lego_orders.csv" in out.getvalue()
print("Old lego_order_items.csv renamed to lego_orders.csv: OK")

# Never overwrites an existing new file, and leaves custom --csv names alone.
(tmp / "lego_order_items.csv").write_text("OLDER")
assert sc._rename_old_csv(tmp / "lego_orders.csv") is False
assert (tmp / "lego_orders.csv").read_text() == "OLD" and (tmp / "lego_order_items.csv").read_text() == "OLDER"
assert sc._rename_old_csv(tmp / "mine.csv") is False and not (tmp / "mine.csv").exists()
assert sc._rename_old_csv(tmp / "missing_dir" / "lego_orders.csv") is False
print("Existing lego_orders.csv never overwritten; custom --csv names untouched: OK")
print("\nALL CSV-NAME TESTS PASSED")
