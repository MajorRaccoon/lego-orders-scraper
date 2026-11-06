"""--since-date helpers: _parse_order_date, _before_since_date."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import datetime, sys
sys.path.insert(0, SRC)
from lego_orders_scraper import LegoOrder, _parse_order_date, _before_since_date

assert _parse_order_date("September 7, 2026") == datetime.date(2026, 9, 7)
assert _parse_order_date("January 31, 2024") == datetime.date(2024, 1, 31)
for bad in (None, "", "garbage", "2026-09-07", "Sept 7, 2026"):
    assert _parse_order_date(bad) is None, bad
print("_parse_order_date: LEGO format parsed; anything else -> None: OK")

def o(d): return LegoOrder(order_number="T1", status=None, order_date=d, total=None, item_count_listed=None, url="u")
since = datetime.date(2026, 6, 1)
assert _before_since_date(o("May 31, 2026"), since) is True
assert _before_since_date(o("June 1, 2026"), since) is False       # same day is kept
assert _before_since_date(o("June 2, 2026"), since) is False
assert _before_since_date(o("not a date"), since) is False         # unparseable -> fetch anyway
assert _before_since_date(o(None), since) is False
assert _before_since_date(o("May 31, 2026"), None) is False        # no cutoff
print("_before_since_date: strictly-before only; unparseable/None never skipped: OK")
print("\nALL SINCE-DATE TESTS PASSED")
