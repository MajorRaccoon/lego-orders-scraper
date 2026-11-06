"""write_outputs()'s final summary line reflects how many orders actually got item detail."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import io, sys, contextlib, tempfile
from pathlib import Path
sys.path.insert(0, SRC)
from lego_orders_scraper import LegoOrder, write_outputs

tmp_dir = Path(tempfile.mkdtemp(prefix="lego_summary_test_"))
orders_all_fetched = [
    LegoOrder.from_dict({
        "order_number": f"T{i}", "status": "Shipped", "order_date": "June 1, 2026",
        "total": "10.00", "item_count_listed": 1, "url": f"https://x/T{i}",
        "items": [{"name": "Widget", "item_number": "1", "quantity": 1,
                   "prices": {"product.regularPrice": "10.00", "product.salePrice": "10.00"},
                   "is_free_gift": False, "status": "Shipped", "tracking_number": None}],
    }) for i in range(3)
]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    write_outputs(orders_all_fetched, tmp_dir / "a.json", tmp_dir / "a.csv")
output = buf.getvalue()
assert "Wrote" in output and "3 order(s))." in output, output
assert "with item detail" not in output, output
print("All orders have items: simple summary message: OK")

orders_mixed = orders_all_fetched + [
    LegoOrder.from_dict({"order_number": "T100", "status": "Shipped", "order_date": "January 1, 2020",
                         "total": "5.00", "item_count_listed": 1, "url": "https://x/T100"}),
    LegoOrder.from_dict({"order_number": "T101", "status": "Shipped", "order_date": "January 2, 2020",
                         "total": "5.00", "item_count_listed": 1, "url": "https://x/T101", "items": []}),
]
buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    write_outputs(orders_mixed, tmp_dir / "b.json", tmp_dir / "b.csv")
output2 = buf2.getvalue()
assert "5 order(s) listed" in output2 and "3 of them with item detail" in output2 and "other 2 have no items yet" in output2, output2
print("Mixed: summary distinguishes listed vs. with-item-detail counts: OK")

buf3 = io.StringIO()
with contextlib.redirect_stdout(buf3):
    write_outputs(orders_mixed, tmp_dir / "c.json", tmp_dir / "c.csv", quiet=True)
assert buf3.getvalue() == ""
print("quiet=True prints nothing: OK")
print("\nALL WRITE-OUTPUTS-SUMMARY TESTS PASSED")
