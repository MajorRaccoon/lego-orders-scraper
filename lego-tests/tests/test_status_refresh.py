"""A saved order whose status changes (e.g. In Process -> Shipped) gets its detail page re-read, so
"Pre-order" items pick up their shipped status and tracking. Runs the real scrape() end to end against
a fake LEGO.com. A failed refresh keeps the saved items and is retried next run; orders before the
since date aren't refetched (their status still updates); unchanged orders aren't touched."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import contextlib, datetime, io, json, re, sys, tempfile
from pathlib import Path
import unittest.mock as mock
sys.path.insert(0, SRC)
import lego_orders_scraper as sc
from playwright.sync_api import TimeoutError as PWTimeoutError


class Site:
    """Fake LEGO.com: the My Orders list and each order's detail page, as page text."""
    def __init__(self):
        self.orders = {}      # number -> (status, date)
        self.details = {}     # number -> detail page text
        self.failing = set()  # numbers whose detail page times out
        self.visited = []

    def list_text(self):
        return "".join(f"{st}\nOrder Number: {n}\nOrder Date: {d}\nTotal: $10.00\n1 item in this order\n"
                       for n, (st, d) in self.orders.items())


class Loc:
    def __init__(self, page, role, name):
        self.page, self.role, self.name = page, role, name
    @property
    def first(self): return self
    def count(self):
        if self.role == "link" and not isinstance(self.name, str):  # order-number links
            return len(self.page.site.orders)
        return 0  # no cookie banner, no "Sign In" link, no "Load More"
    def wait_for(self, state="visible", timeout=0):
        if self.role == "button":
            raise PWTimeoutError("Load More never appears")
    def click(self, timeout=0): pass


class Page:
    def __init__(self, site): self.site, self.current = site, ""
    def goto(self, url, wait_until=None, timeout=None):
        num = url.rsplit("/", 1)[-1]
        if url != sc.ORDERS_URL:
            self.site.visited.append(num)
            if num in self.site.failing:
                raise Exception("Timeout 20000ms exceeded.")
        self.current = url
    def title(self): return "My Orders"
    def get_by_role(self, role, name=None): return Loc(self, role, name)
    def get_by_text(self, pattern): return Loc(self, "text", pattern)
    def locator(self, sel): return self
    def inner_text(self):
        if self.current == sc.ORDERS_URL:
            return self.site.list_text()
        return self.site.details[self.current.rsplit("/", 1)[-1]]
    def wait_for_timeout(self, ms): pass


def run(site, tmp, since=None):
    site.visited = []
    page = Page(site)
    context = mock.Mock(new_page=lambda: page)
    pw = mock.MagicMock()
    pw.__enter__.return_value.chromium.launch_persistent_context.return_value = context
    out = io.StringIO()
    with mock.patch.object(sc, "sync_playwright", return_value=pw), \
         mock.patch.object(sc, "PROFILE_DIR", tmp / "profile"), contextlib.redirect_stdout(out):
        sc.scrape(delay=0, load_more_delay=0, load_more_final_wait=0,
                  json_path=str(tmp / "o.json"), csv_path=str(tmp / "o.csv"), since_date=since)
    saved = {o["order_number"]: o for o in json.loads((tmp / "o.json").read_text())}
    return saved, out.getvalue()


def detail(status, name, tracking=None):
    return (f"{status}\n" + (f"Tracking number: {tracking}\n" if tracking else "")
            + f"{name}\nItem: 910072\nQuantity: 1\nPrice$99.99\n")


tmp = Path(tempfile.mkdtemp(prefix="lego_refresh_"))
site = Site()
site.orders = {"T100": ("In Process", "October 6, 2026"), "T200": ("Shipped", "May 1, 2026")}
site.details = {"T100": detail("Pre-order", "Depot"), "T200": detail("Shipped", "Train", "1ZOLD")}

saved, _ = run(site, tmp)
assert saved["T100"]["items"][0]["status"] == "Pre-order" and saved["T100"]["status"] == "In Process"
assert sorted(site.visited) == ["T100", "T200"]
print("Run 1: both orders fetched; the In Process order's item is 'Pre-order': OK")

# The pre-order ships: LEGO's list now says Shipped, and the detail page has a tracking number.
site.orders["T100"] = ("Shipped", "October 6, 2026")
site.details["T100"] = detail("Shipped", "Depot", "1ZNEW")
saved, log = run(site, tmp)
assert site.visited == ["T100"], site.visited                      # only the changed order is re-read
item = saved["T100"]["items"][0]
assert (item["status"], item["tracking_number"]) == ("Shipped", "1ZNEW") and saved["T100"]["status"] == "Shipped"
assert "fetch_error" not in saved["T100"]
assert "status changed from 'In Process' to 'Shipped'" in log and "(status changed, refreshing)" in log
print("Run 2: status changed -> that order re-read; item now Shipped with tracking; others untouched: OK")

# Status changes again, but the page fails to load: saved items are kept, and it's retried next run.
site.orders["T100"] = ("Complete", "October 6, 2026")
site.failing = {"T100"}
saved, log = run(site, tmp)
item = saved["T100"]["items"][0]
assert (item["status"], item["tracking_number"]) == ("Shipped", "1ZNEW")
assert saved["T100"]["status"] == "Complete" and "Timeout" in saved["T100"]["fetch_error"]
assert "couldn't refresh this order, keeping its saved detail" in log
print("Run 3: refresh fails -> saved items kept, error recorded: OK")

site.failing = set()
site.details["T100"] = detail("Delivered", "Depot", "1ZNEW")
saved, log = run(site, tmp)
assert site.visited == ["T100"] and saved["T100"]["items"][0]["status"] == "Delivered"
assert "fetch_error" not in saved["T100"] and "last refresh didn't finish" in log
print("Run 4: the failed refresh is retried and succeeds: OK")

# An order older than the since date changes status: not refetched, but its status updates.
site.orders["T200"] = ("Complete", "May 1, 2026")
saved, _ = run(site, tmp, since=datetime.date(2026, 6, 1))
assert site.visited == [] and saved["T200"]["status"] == "Complete"
assert saved["T200"]["items"][0]["tracking_number"] == "1ZOLD" and "fetch_error" not in saved["T200"]
print("Run 5: order before the since date -> status updated, not refetched, items kept: OK")

# Nothing changed -> nothing re-read.
saved, _ = run(site, tmp)
assert site.visited == []
print("Run 6: no status changes -> no detail pages re-read: OK")
print("\nALL STATUS-REFRESH TESTS PASSED")
