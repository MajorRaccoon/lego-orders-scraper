"""lego_repair_json_from_csv.repair(): rebuild missing JSON items from the CSV, keep a backup."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import contextlib, io, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, SRC)
from lego_orders_scraper import LegoOrder, write_outputs
from lego_repair_json_from_csv import repair

tmp = Path(tempfile.mkdtemp()); jp, cp = tmp / "o.json", tmp / "o.csv"
item = {"name": "Widget", "item_number": "111", "custom_id": "C1", "quantity": 2,
        "prices": {"product.regularPrice": "10.00", "product.salePrice": "8.00"},
        "is_free_gift": False, "is_piece": True, "is_gift_card": False, "status": "Shipped", "tracking_number": "1Z"}
good = LegoOrder.from_dict({"order_number": "T1", "status": "Shipped", "order_date": "June 1, 2026", "total": "16.00",
                            "item_count_listed": 1, "url": "u", "items": [item]})
write_outputs([good], tmp / "full.json", cp, quiet=True)            # CSV with T1's row

broken = [good.to_dict(), dict(good.to_dict(), order_number="T2", items=[])]
broken[0]["items"] = []                                              # T1 lost its items in the JSON
jp.write_text(json.dumps(broken))

with contextlib.redirect_stdout(io.StringIO()) as out:
    repair(jp, cp)
fixed = {d["order_number"]: d for d in json.loads(jp.read_text())}
assert len(fixed["T1"]["items"]) == 1
r = fixed["T1"]["items"][0]
assert (r["name"], r["item_number"], r["custom_id"], r["quantity"], r["is_piece"], r["tracking_number"]) == ("Widget", "111", "C1", 2, True, "1Z")
assert r["prices"] == {"product.regularPrice": "10.00", "product.salePrice": "8.00"}
assert fixed["T2"]["items"] == []                                    # no CSV rows -> untouched
assert Path(str(jp) + ".bak").exists()
print("repair: items rebuilt from CSV incl. prices/flags, unrepairable left alone, .bak written: OK")

with contextlib.redirect_stdout(io.StringIO()) as out2:
    repair(jp, cp)
assert "Nothing to repair" in out2.getvalue()
print("repair on already-good data: no-op: OK")

# legacy single 'price' column CSV
legacy = tmp / "legacy.csv"
legacy.write_text("order_number,item_name,item_number,quantity,price,is_free_gift\nT5,Old,9,1,7.50,False\n")
j2 = tmp / "l.json"; j2.write_text(json.dumps([{"order_number": "T5", "status": "x", "order_date": "d", "total": "7.50", "url": "u", "items": []}]))
with contextlib.redirect_stdout(io.StringIO()):
    repair(j2, legacy)
it = json.loads(j2.read_text())[0]["items"][0]
assert it["prices"] == {"product.regularPrice": "7.50", "product.salePrice": "7.50"}
print("repair: legacy single-price CSV used for both prices: OK")
print("\nALL REPAIR TESTS PASSED")
