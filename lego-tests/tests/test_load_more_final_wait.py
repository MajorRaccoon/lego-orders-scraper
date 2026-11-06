"""load_all_orders_text(): the 'give Load More one more, longer chance to reappear' behavior."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys
sys.path.insert(0, SRC)
from lego_orders_scraper import load_all_orders_text
from playwright.sync_api import TimeoutError as PWTimeoutError

class FakeLocator:
    def __init__(self, page, kind): self.page, self.kind = page, kind
    def count(self):
        return (1 if self.page.load_more_visible else 0) if self.kind == "load_more" else self.page.order_count
    @property
    def first(self): return self
    def click(self):
        assert self.kind == "load_more"; self.page.clicks += 1; self.page.on_click()
    def wait_for(self, state="visible", timeout=0):
        if self.kind == "order_link":
            if self.page.order_count == 0: raise PWTimeoutError("no order links")
            return
        delay_ms = self.page.load_more_reappear_after_ms
        if delay_ms is None or delay_ms > timeout: raise PWTimeoutError("never reappeared in time")
        self.page.load_more_visible = True

class FakePage:
    def __init__(self, reappear_after_ms=3000, num_load_more_rounds=1):
        self.order_count, self.load_more_visible, self.clicks = 2, True, 0
        self.load_more_reappear_after_ms, self.num_load_more_rounds = reappear_after_ms, num_load_more_rounds
    def on_click(self):
        self.load_more_visible = False
        self.order_count += 2
        if self.clicks >= self.num_load_more_rounds: self.load_more_reappear_after_ms = None
    def get_by_role(self, role, name=None):
        return FakeLocator(self, "order_link" if role == "link" else "load_more")
    def locator(self, sel): assert sel == "main"; return self
    def inner_text(self): return f"<{self.order_count} orders rendered>"
    def wait_for_timeout(self, ms): pass

page = FakePage(3000, 2)
load_all_orders_text(page, load_more_delay=0.01, load_more_final_wait=5.0)
assert page.clicks == 2 and page.order_count == 6
print("Slow reappearance, final_wait long enough: keeps going: OK")

page2 = FakePage(3000, 2)
load_all_orders_text(page2, load_more_delay=0.01, load_more_final_wait=0.1)
assert page2.clicks == 1 and page2.order_count == 4
print("final_wait too short: stops early as expected: OK")

page3 = FakePage(3000, 1)
load_all_orders_text(page3, load_more_delay=0.01, load_more_final_wait=0.05)
assert page3.clicks == 1 and page3.order_count == 4
print("Genuinely done: terminates cleanly: OK")
print("\nALL LOAD-MORE-FINAL-WAIT TESTS PASSED")
