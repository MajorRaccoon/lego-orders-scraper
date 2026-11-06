"""
Regression: when one order's block in the My Orders list lacks a
recognizable "N items in this order" line, parse_order_list()'s lookahead
used to run on into the NEXT order's block and hand the earlier order the
next one's date/total. Each order must only ever get fields from its own block.
"""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys
sys.path.insert(0, SRC)
from lego_orders_scraper import parse_order_list

text = """Shipped
Order Number: T111111111
Order Date: June 1, 2026
Total: $10.00
1 gift card in this order
Shipped
Order Number: T222222222
Order Date: May 1, 2026
Total: $99.99
2 items in this order
Backordered
Order Number: T333333333
Order Date: April 1, 2026
2 items in this order
Shipped
Order Number: T444444444
Order Date: March 1, 2026
Total: $7.50
1 item in this order
"""
o = {x.order_number: x for x in parse_order_list(text)}
assert (o["T111111111"].order_date, o["T111111111"].total, o["T111111111"].item_count_listed) == ("June 1, 2026", "10.00", None), o["T111111111"]
assert (o["T222222222"].order_date, o["T222222222"].total, o["T222222222"].item_count_listed) == ("May 1, 2026", "99.99", 2)
assert (o["T333333333"].order_date, o["T333333333"].total) == ("April 1, 2026", None), o["T333333333"]
assert (o["T444444444"].total, o["T444444444"].item_count_listed) == ("7.50", 1)
assert len({x.total for x in o.values() if x.total}) == 3
# The case the stop-at-next-order guard exists for: an order with NO Total line
# AND no item-count line (e.g. a just-placed order), directly followed by
# another order that has both. It must not inherit the neighbor's total.
t2 = {x.order_number: x for x in parse_order_list("""Just placed
Order Number: T555555555
Order Date: October 6, 2026
In Process
Order Number: T666666666
Order Date: October 6, 2026
Total: $579.13
2 items in this order
""")}
assert t2["T555555555"].total is None and t2["T555555555"].item_count_listed is None, t2["T555555555"]
assert t2["T666666666"].total == "579.13"
print("Adjacent orders never borrow each other's date/total, even with a missing item-count or Total line: OK")
print("\nALL ORDER-LIST NO-BLEED TESTS PASSED")
