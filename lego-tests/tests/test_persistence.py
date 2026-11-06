"""write_outputs JSON/CSV content, load_existing_orders resume behavior, and _atomic_write safety."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import csv, io, contextlib, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, SRC)
from lego_orders_scraper import (LegoOrder, write_outputs, load_existing_orders, _atomic_write)

tmp = Path(tempfile.mkdtemp(prefix="lego_persist_"))
full = LegoOrder.from_dict({
    "order_number": "T1", "status": "Shipped", "order_date": "June 1, 2026", "total": "123.45",
    "item_count_listed": 2, "url": "u/T1",
    "items": [
        {"name": "Hub, with comma", "item_number": "88012", "quantity": 2,
         "prices": {"product.regularPrice": "59.99", "product.salePrice": "49.99"},
         "is_free_gift": False, "status": "Shipped", "tracking_number": "1Z1"},
        {"name": "Gift", "item_number": "5006", "custom_id": "ID9", "quantity": 1,
         "prices": {"product.regularPrice": None, "product.salePrice": None},
         "is_free_gift": True, "is_piece": True, "is_gift_card": False},
    ],
    "summary": {"subtotal": "134.98", "delivery": "0.00", "tax": "8.47", "insiders_discount": "-20.00",
                "discount": "-1.00", "total": "123.45"},
})
empty = LegoOrder.from_dict({"order_number": "T2", "status": "Processing", "order_date": "July 1, 2026",
                             "total": "5.00", "item_count_listed": 1, "url": "u/T2"})
fail = LegoOrder.from_dict({"order_number": "T3", "status": "Shipped", "order_date": "July 2, 2026",
                            "total": "6.00", "item_count_listed": 1, "url": "u/T3", "fetch_error": "timeout"})
jp, cp = tmp / "o.json", tmp / "o.csv"
write_outputs([full, empty, fail], jp, cp, quiet=True)

data = json.loads(jp.read_text())
assert [d["order_number"] for d in data] == ["T1", "T2", "T3"]
assert data[0]["summary"]["insiders_discount"] == "-20.00" and len(data[0]["items"]) == 2
assert "fetch_error" not in data[0] and data[2]["fetch_error"] == "timeout"
print("JSON: all orders, nested items/summary, fetch_error only when set: OK")

rows = list(csv.DictReader(open(cp, newline="", encoding="utf-8")))
assert list(rows[0].keys()) == ["order_number", "order_date", "order_status", "order_total",
    "order_subtotal", "order_delivery", "order_tax", "order_insiders_discount", "order_discount",
    "item_name", "item_number", "custom_id", "quantity", "regular_price", "sale_price",
    "is_free_gift", "is_piece", "is_gift_card", "item_status", "tracking_number"]
assert len(rows) == 2 and {r["order_number"] for r in rows} == {"T1"}      # one row per ITEM; item-less orders add none
r0, r1 = rows
assert r0["item_name"] == "Hub, with comma" and r0["regular_price"] == "59.99" and r0["sale_price"] == "49.99"
assert (r0["order_subtotal"], r0["order_tax"], r0["order_insiders_discount"], r0["order_discount"]) == ("134.98", "8.47", "-20.00", "-1.00")
assert r1["is_free_gift"] == "True" and r1["is_piece"] == "True" and r1["custom_id"] == "ID9" and r1["regular_price"] == ""
print("CSV: exact header, one row per item, commas quoted, summary + price columns, blanks for null: OK")

# resume: only orders WITH items are treated as already done
loaded = load_existing_orders(jp)
assert set(loaded) == {"T1"} and len(loaded["T1"].items) == 2 and loaded["T1"].summary["total"] == "123.45"
print("load_existing_orders: only item-bearing orders count as done: OK")

with contextlib.redirect_stdout(io.StringIO()):
    assert load_existing_orders(tmp / "missing.json") == {}
    (tmp / "bad.json").write_text("{not json")
    assert load_existing_orders(tmp / "bad.json") == {}
print("missing / corrupt JSON -> start fresh, no crash: OK")

# round trip is lossless
write_outputs(list(loaded.values()), tmp / "r.json", tmp / "r.csv", quiet=True)
assert json.loads((tmp / "r.json").read_text())[0] == data[0]
print("JSON round trip is lossless: OK")

# atomic write: a failure leaves the old file intact and no .tmp behind
target = tmp / "keep.txt"; target.write_text("OLD")
def boom(p):
    p.write_text("PARTIAL"); raise RuntimeError("disk full")
try: _atomic_write(target, boom); assert False
except RuntimeError: pass
assert target.read_text() == "OLD" and not list(tmp.glob("*.tmp"))
def interrupted(p):
    p.write_text("PARTIAL"); raise KeyboardInterrupt
try: _atomic_write(target, interrupted); assert False
except KeyboardInterrupt: pass
assert target.read_text() == "OLD" and not list(tmp.glob("*.tmp"))
_atomic_write(target, lambda p: p.write_text("NEW")); assert target.read_text() == "NEW"
print("_atomic_write: old file survives errors AND Ctrl+C, temp cleaned, success replaces: OK")

# defensive dedupe inside write_outputs: JSON and CSV built from the same list
dup_with, dup_empty = full, LegoOrder.from_dict(full.to_dict()); dup_empty.items = []
with contextlib.redirect_stdout(io.StringIO()):
    write_outputs([dup_empty, dup_with], tmp / "d.json", tmp / "d.csv", quiet=True)
dj = json.loads((tmp / "d.json").read_text())
assert len(dj) == 1 and len(dj[0]["items"]) == 2
assert len(list(csv.DictReader(open(tmp / "d.csv", newline="")))) == 2
print("write_outputs dedupes so JSON and CSV agree: OK")
print("\nALL PERSISTENCE TESTS PASSED")
