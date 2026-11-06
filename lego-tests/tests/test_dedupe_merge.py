"""dedupe_orders and merge_with_existing."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import io, contextlib, sys
sys.path.insert(0, SRC)
from lego_orders_scraper import LegoOrder, dedupe_orders, merge_with_existing

def mk(num, items=0, status="Shipped", total="1.00", date="May 1, 2026"):
    return LegoOrder.from_dict({"order_number": num, "status": status, "order_date": date, "total": total,
        "item_count_listed": items, "url": f"u/{num}",
        "items": [{"name": f"i{k}", "item_number": str(k), "quantity": 1, "prices": {}, "is_free_gift": False}
                  for k in range(items)]})

with contextlib.redirect_stdout(io.StringIO()):
    out = dedupe_orders([mk("T1"), mk("T2", items=2), mk("T1", items=3), mk("T2")])
assert [o.order_number for o in out] == ["T1", "T2"]
assert len(out[0].items) == 3 and len(out[1].items) == 2
print("dedupe: one per order number, copy WITH items wins, order preserved: OK")

with contextlib.redirect_stdout(io.StringIO()):
    out = dedupe_orders([mk("T1", 1), mk("T1", 2)])
assert len(out) == 1 and len(out[0].items) == 1
print("dedupe: when both have items the first is kept: OK")

existing = {"T1": mk("T1", items=2, status="Backordered", total="9.00"), "T9": mk("T9", items=1)}
fresh = [mk("T2"), mk("T1", status="Shipped", total="9.50", date="June 2, 2026")]
merged = merge_with_existing(fresh, existing)
assert [o.order_number for o in merged] == ["T2", "T1", "T9"]       # fresh order first, leftovers last
t1 = merged[1]
assert len(t1.items) == 2                                           # items kept
assert (t1.status, t1.total, t1.order_date) == ("Shipped", "9.50", "June 2, 2026")   # list fields refreshed
assert merged[0].items == [] and len(merged[2].items) == 1
print("merge: items kept, list fields refreshed, new orders added, leftovers retained: OK")
print("\nALL DEDUPE/MERGE TESTS PASSED")
