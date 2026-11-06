"""load_all_orders_text() stops clicking 'Load More' once the oldest loaded order is before --since-date."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys, datetime
sys.path.insert(0, SRC)
from lego_orders_scraper import load_all_orders_text, parse_order_list
from playwright.sync_api import TimeoutError as PWTimeoutError

def _order_block(order_num, date_str, total="10.00"):
    return (f"Shipped\nOrder Number: T{order_num}\nOrder Date: {date_str}\n"
            f"Total: ${total}\n1 item in this order\nManage my order\n")

class FakeLocator:
    def __init__(self, page, kind): self.page, self.kind = page, kind
    def count(self):
        return (1 if self.page.load_more_visible() else 0) if self.kind == "load_more" else self.page.order_count()
    @property
    def first(self): return self
    def click(self):
        assert self.kind == "load_more"; self.page.clicks += 1; self.page.loaded_batches += 1
    def wait_for(self, state="visible", timeout=0):
        if self.kind == "order_link":
            if self.page.order_count() == 0: raise PWTimeoutError("no order links")
            return
        raise PWTimeoutError("Load More never reappeared")

class FakePage:
    def __init__(self, batches): self.batches, self.loaded_batches, self.clicks = batches, 1, 0
    def order_count(self): return sum(b.count("Order Number:") for b in self.batches[: self.loaded_batches])
    def load_more_visible(self): return self.loaded_batches < len(self.batches)
    def get_by_role(self, role, name=None):
        return FakeLocator(self, "order_link" if role == "link" else "load_more")
    def locator(self, sel): assert sel == "main"; return self
    def inner_text(self): return "".join(self.batches[: self.loaded_batches])
    def wait_for_timeout(self, ms): pass

since = datetime.date(2026, 6, 1)

batches = [
    _order_block(1, "June 15, 2026") + _order_block(2, "June 10, 2026"),
    _order_block(3, "June 2, 2026") + _order_block(4, "May 20, 2026"),
    _order_block(5, "April 1, 2026") + _order_block(6, "March 1, 2026"),
]
page = FakePage(batches)
text = load_all_orders_text(page, since_date=since, load_more_delay=0.01)
assert page.clicks == 1, page.clicks
assert [o.order_number for o in parse_order_list(text)] == ["T1", "T2", "T3", "T4"]
print("Stops right after the batch that crosses --since-date: OK")

page2 = FakePage([_order_block(10, "June 15, 2026") + _order_block(11, "May 1, 2026"), _order_block(12, "April 1, 2026")])
load_all_orders_text(page2, since_date=since, load_more_delay=0.01)
assert page2.clicks == 0
print("First batch already crosses the cutoff -> zero clicks: OK")

page3 = FakePage([_order_block(20, "June 15, 2026") + _order_block(21, "June 1, 2026"), _order_block(22, "May 31, 2026")])
load_all_orders_text(page3, since_date=since, load_more_delay=0.01)
assert page3.clicks == 1
print("Same-day order doesn't trigger an early stop: OK")

page4 = FakePage([_order_block(30, "June 15, 2026"), _order_block(31, "January 1, 2020")])
load_all_orders_text(page4, since_date=None, load_more_delay=0.01)
assert page4.clicks == 1
print("since_date=None: full pagination: OK")
print("\nALL SINCE-DATE-EARLY-STOP TESTS PASSED")
