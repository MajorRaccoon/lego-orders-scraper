"""Two simulated scrape 'runs' using the real functions together:
list -> merge -> dedupe -> detail parse -> reconcile -> write, then resume on run 2."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import io, contextlib, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, SRC)
from lego_orders_scraper import (parse_order_list, parse_order_detail, _parse_order_summary, _reconcile_total,
    merge_with_existing, dedupe_orders, load_existing_orders, write_outputs, _before_since_date, _parse_cli_date)

LIST = """Shipped
Order Number: T100
Order Date: June 5, 2026
Total: $20.00
1 item in this order
Shipped
Order Number: T100
Order Date: June 5, 2026
Total: $20.00
1 item in this order
Shipped
Order Number: T200
Order Date: January 5, 2020
Total: $8.00
1 item in this order
"""
DETAIL = {
 "T100": "Shipped\nTracking number: 1Z\nWidget™\nItem: 111\nQuantity: 1\nPrice\n$18.50\nOrder summary\nSubtotal $18.50\nTax $1.50\nTotal $20.00\n",
 "T200": "Old Thing\nItem: 222\nQuantity: 1\nPrice\n$8.00\n",
}
tmp = Path(tempfile.mkdtemp()); jp, cp = tmp / "o.json", tmp / "o.csv"
since = _parse_cli_date("01/01/2026")

def run(existing):
    fetched = []
    orders = dedupe_orders(merge_with_existing(parse_order_list(LIST), existing))
    for o in orders:
        if o.items or _before_since_date(o, since): continue
        fetched.append(o.order_number)
        o.items = parse_order_detail(DETAIL[o.order_number])
        o.summary = _parse_order_summary(DETAIL[o.order_number])
        _reconcile_total(o)
        write_outputs(orders, jp, cp, quiet=True)
    write_outputs(orders, jp, cp, quiet=True)
    return orders, fetched

with contextlib.redirect_stdout(io.StringIO()):
    orders, fetched = run({})
assert [o.order_number for o in orders] == ["T100", "T200"]          # duplicate T100 collapsed
assert fetched == ["T100"]                                            # T200 older than cutoff: not fetched
assert orders[0].items[0].name == "Widget" and orders[0].summary["total"] == "20.00" and orders[1].items == []
print("Run 1: dedupe, since-date skip, detail+summary parsed, outputs written: OK")

with contextlib.redirect_stdout(io.StringIO()):
    orders2, fetched2 = run(load_existing_orders(jp))
assert fetched2 == []                                                 # resume: nothing refetched
assert orders2[0].items[0].tracking_number == "1Z" and len(json.loads(jp.read_text())) == 2
print("Run 2 (resume): saved orders not refetched, data intact: OK")
print("\nALL PIPELINE INTEGRATION TESTS PASSED")
