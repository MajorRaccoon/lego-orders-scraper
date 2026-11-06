"""Spending-by-month table in the HTML report (years = columns, months = rows,
TOTALS row after December)."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import re, sys
sys.path.insert(0, SRC)
from lego_orders_scraper import LegoOrder, render_orders_html, write_html_report

def o(num, date, total):
    return LegoOrder.from_dict({"order_number": num, "status": "Shipped", "order_date": date,
                                "total": total, "item_count_listed": 1, "url": "u"})

orders = [
    o("T1", "February 3, 2024", "100.00"),
    o("T2", "February 20, 2024", "50.50"),     # same month -> summed
    o("T3", "December 31, 2024", "1,200.00"),  # comma in total
    o("T4", "January 5, 2026", "10.00"),       # 2025 has no orders -> still a column
    o("T5", "October 6, 2026", "107.23"),
    o("T6", "not a date", "5.00"),             # unplaceable -> noted, not crashed
    o("T7", "March 1, 2026", None),            # no total -> noted
]
html = render_orders_html(orders)
sec = html[html.index('class="section-title"'):html.index('class="index-table"')]

# Columns are 2024, 2025, 2026 in order (2025 empty but present).
head = re.search(r"<thead><tr>(.*?)</tr></thead>", sec).group(1)
assert re.findall(r"<th>(.*?)</th>", head) == ["Month", "2024", "2025", "2026"], head

rows = re.findall(r"<tr(?: class=\"totals\")?><td>(.*?)</td>(.*?)</tr>", sec)
names = [r[0] for r in rows]
assert names == ["January","February","March","April","May","June","July","August",
                 "September","October","November","December","Total"], names
cells = {n: re.findall(r"<td[^>]*>(.*?)</td>", rest) for n, rest in rows}
assert cells["February"] == ["$150.50", "—", "—"], cells["February"]
assert cells["December"] == ["$1,200.00", "—", "—"], cells["December"]
assert cells["January"] == ["—", "—", "$10.00"]
assert cells["October"] == ["—", "—", "$107.23"]
assert cells["Total"] == ["$1,350.50", "—", "$117.23"] or cells["Total"] == ["$1,350.50", "$0.00", "$117.23"], cells["Total"]
assert 'class="totals"' in sec and sec.index("December") < sec.index('class="totals"')
assert "2 order(s) with no readable date or total" in sec
print("Grid values, ordering, summing, gap year, TOTALS after December, skipped-order note: OK")

# Placement: after the stat cards, before the order index table.
assert html.index('class="stats"') < html.index("Spending by month") < html.index('class="index-table"')
print("Table sits between the stat cards and the orders index: OK")

# Empty / unplaceable-only input renders no table and doesn't crash.
assert "Spending by month" not in render_orders_html([])
assert "Spending by month" not in render_orders_html([o("T9", "garbage", "1.00")])
print("No placeable orders -> table omitted, no crash: OK")

import tempfile, pathlib
p = pathlib.Path(tempfile.mkdtemp()) / "r.html"; write_html_report(orders, p)
assert "Spending by month" in p.read_text(); print("write_html_report includes it: OK")
print("\nALL MONTHLY TABLE TESTS PASSED")
