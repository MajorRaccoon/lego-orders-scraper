"""load_all_orders_text() prints an incrementing counter + order number per newly seen order."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import io, sys, contextlib
sys.path.insert(0, SRC)
from lego_orders_scraper import load_all_orders_text
from playwright.sync_api import TimeoutError as PWTimeoutError

def _orders_block(n): return "\n".join(f"Order Number: T{500000000 + i}" for i in range(n))

class FakeLocator:
    def __init__(self, page, kind): self.page, self.kind = page, kind
    def count(self):
        return (1 if self.page.load_more_visible else 0) if self.kind == "load_more" else self.page.order_count
    @property
    def first(self): return self
    def click(self):
        self.page.clicks += 1; self.page.load_more_visible = False; self.page.order_count += 2
    def wait_for(self, state="visible", timeout=0):
        if self.kind == "order_link":
            if self.page.order_count == 0: raise PWTimeoutError("no order links")
            return
        raise PWTimeoutError("Load More never reappeared")

class FakePage:
    def __init__(self): self.order_count, self.load_more_visible, self.clicks = 2, True, 0
    def get_by_role(self, role, name=None):
        return FakeLocator(self, "order_link" if role == "link" else "load_more")
    def locator(self, sel): assert sel == "main"; return self
    def inner_text(self): return _orders_block(self.order_count)
    def wait_for_timeout(self, ms): pass

page = FakePage()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    load_all_orders_text(page, load_more_delay=0.01, load_more_final_wait=0.01)
lines = [l for l in buf.getvalue().splitlines() if l.strip().startswith("[")]
assert lines == ["  [1] T500000000", "  [2] T500000001", "  [3] T500000002", "  [4] T500000003"], lines
assert page.clicks == 1
print("Progress lines print an incrementing counter + order number: OK")
print("\nALL LOAD-MORE-PROGRESS TESTS PASSED")
