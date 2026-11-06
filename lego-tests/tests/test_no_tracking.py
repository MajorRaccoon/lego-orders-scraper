"""--no-tracking: tracking numbers are left out (blank) of the JSON, CSV and HTML; the field/column stays;
nothing changes when the option is off (the default); the web UI checkbox maps to the flag."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import csv, json, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, SRC)
from lego_orders_scraper import LegoOrder, write_outputs, write_html_report, without_tracking, load_existing_orders

order = LegoOrder.from_dict({
    "order_number": "T1", "status": "Shipped", "order_date": "June 1, 2026", "total": "10.00",
    "item_count_listed": 2, "url": "u/T1",
    "items": [{"name": "A", "item_number": "1", "quantity": 1, "prices": {"product.regularPrice": "5.00",
               "product.salePrice": "5.00"}, "is_free_gift": False, "status": "Shipped", "tracking_number": "1ZSECRET1"},
              {"name": "B", "item_number": "2", "quantity": 1, "prices": {}, "is_free_gift": True,
               "status": "Shipped", "tracking_number": "1ZSECRET2"}]})
tmp = Path(tempfile.mkdtemp(prefix="lego_notrack_"))

# Default (option off): tracking numbers everywhere, exactly as before.
write_outputs([order], tmp / "on.json", tmp / "on.csv", quiet=True)
write_html_report([order], tmp / "on.html")
for f in ("on.json", "on.csv", "on.html"):
    assert "1ZSECRET1" in (tmp / f).read_text(), f
print("Default: tracking numbers written to JSON, CSV and HTML: OK")

# Option on: no tracking number anywhere; field/column still present and empty.
write_outputs([order], tmp / "off.json", tmp / "off.csv", quiet=True, include_tracking=False)
write_html_report([order], tmp / "off.html", include_tracking=False)
for f in ("off.json", "off.csv", "off.html"):
    assert "1ZSECRET" not in (tmp / f).read_text(), f
data = json.loads((tmp / "off.json").read_text())
assert all("tracking_number" in i and i["tracking_number"] is None for i in data[0]["items"])
rows = list(csv.DictReader(open(tmp / "off.csv", newline="", encoding="utf-8")))
assert "tracking_number" in rows[0] and all(r["tracking_number"] == "" for r in rows)
assert [r["item_name"] for r in rows] == ["A", "B"] and rows[0]["sale_price"] == "5.00"   # everything else intact
print("include_tracking=False: blank in JSON/CSV/HTML, column kept, other fields intact: OK")

# The in-memory orders aren't modified (only the written copies are).
assert order.items[0].tracking_number == "1ZSECRET1"
assert without_tracking([order])[0].items[1].tracking_number is None and order.items[1].tracking_number == "1ZSECRET2"
print("without_tracking() returns copies, originals untouched: OK")

# A file written without tracking still loads/resumes normally.
assert set(load_existing_orders(tmp / "off.json")) == {"T1"}
print("No-tracking JSON resumes like any other: OK")

# CLI flag exists, and the HTML helper script accepts it too.
help_text = subprocess.run([sys.executable, f"{SRC}/lego_orders_scraper.py", "--help"], capture_output=True, text=True).stdout
assert "--no-tracking" in help_text
r = subprocess.run([sys.executable, f"{SRC}/lego_orders_to_html.py", "--json", str(tmp / "on.json"),
                    "--html", str(tmp / "helper.html"), "--no-tracking"], capture_output=True, text=True)
assert r.returncode == 0, r.stderr
assert "1ZSECRET" not in (tmp / "helper.html").read_text()
print("--no-tracking in scraper --help; lego_orders_to_html.py --no-tracking works: OK")

# Web UI checkbox -> CLI flag (absent/false -> no flag).
try:
    from lego_orders_webapp import build_argv
except ImportError:
    print("SKIPPED web UI part: flask not installed")
else:
    assert "--no-tracking" in build_argv({"no_tracking": True})
    assert "--no-tracking" not in build_argv({"no_tracking": False}) and "--no-tracking" not in build_argv({})
    print("Web UI: 'Leave out tracking numbers' checkbox -> --no-tracking only when checked: OK")
print("\nALL NO-TRACKING TESTS PASSED")
