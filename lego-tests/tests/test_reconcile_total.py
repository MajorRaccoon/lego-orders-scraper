"""An order's own detail-page Total must win over a (possibly wrong) list-page total."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import io, contextlib, sys
sys.path.insert(0, SRC)
from lego_orders_scraper import LegoOrder, merge_with_existing, _reconcile_total

def mk(num, total, summary, items=True):
    return LegoOrder.from_dict({
        "order_number": num, "status": "x", "order_date": "October 6, 2026",
        "total": total, "item_count_listed": 2, "url": "u",
        "items": [{"name": "A", "item_number": "1", "quantity": 2,
                   "prices": {}, "is_free_gift": False}] if items else [],
        "summary": summary})

a = mk("T517109946", "579.13", {"subtotal": "99.98", "delivery": "0.00", "tax": "7.25", "total": "107.23"})
b = mk("T517109748", "579.13", {"subtotal": "539.98", "delivery": "0.00", "tax": "39.15", "total": "579.13"})
with contextlib.redirect_stdout(io.StringIO()) as out:
    assert _reconcile_total(a) is True
    assert _reconcile_total(b) is False
assert a.total == "107.23" and b.total == "579.13"
assert "T517109946" in out.getvalue() and "T517109748" not in out.getvalue()
print("Wrong list total is corrected from the detail summary; correct one untouched: OK")

a2 = mk("T517109946", "579.13", {"total": "107.23"})
fresh = [mk("T517109946", "579.13", {}, items=False)]
with contextlib.redirect_stdout(io.StringIO()):
    merged = merge_with_existing(fresh, {"T517109946": a2})
assert merged[0].total == "107.23", merged[0].total
print("merge_with_existing re-applies the detail total over the list total: OK")

c = mk("T1", "5.00", {})
assert _reconcile_total(c) is False and c.total == "5.00"
print("No summary total -> list total kept: OK")
print("\nALL RECONCILE-TOTAL TESTS PASSED")
