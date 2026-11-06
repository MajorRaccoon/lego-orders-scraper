"""Per-year bar charts in the HTML report: one chart per year (gap years included), after the
'Spending by month' table and before the orders index; a bar per month with spending, all on one
shared scale; hover tooltips; the busiest month labeled; nothing rendered when there's no data."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import re, sys
sys.path.insert(0, SRC)
from lego_orders_scraper import LegoOrder, render_orders_html, _nice_scale

def o(num, date, total):
    return LegoOrder.from_dict({"order_number": num, "status": "Shipped", "order_date": date,
                                "total": total, "item_count_listed": 1, "url": "u"})

orders = [o("T1", "February 3, 2024", "100.00"), o("T2", "February 20, 2024", "50.50"),
          o("T3", "December 31, 2024", "1,200.00"), o("T4", "January 5, 2026", "10.00"),
          o("T5", "October 6, 2026", "107.23"), o("T6", "not a date", "5.00")]
html = render_orders_html(orders)

# Placement: table, then charts, then the orders index.
assert html.index("Spending by month</h2>") < html.index('class="monthly-table"') \
    < html.index("Spending by month, by year</h2>") < html.index('class="year-charts"') < html.index('class="index-table"')
print("Charts come right after the 'Spending by month' table, before the orders index: OK")

charts = re.findall(r'<figure class="year-chart">(.*?)</figure>', html)
years = [re.search(r'<span class="year">(\d+)</span>', c).group(1) for c in charts]
assert years == ["2024", "2025", "2026"], years                      # 2025 has no orders but still gets a chart
c2024, c2025, c2026 = charts
assert '<span class="year-total">$1,350.50</span>' in c2024 and '<span class="year-total">$117.23</span>' in c2026
print("One chart per year (gap year included), each titled with the year's total: OK")

assert c2024.count('class="bar"') == 2 and c2026.count('class="bar"') == 2 and c2025.count('class="bar"') == 0
assert "No spending this year" in c2025 and "No spending this year" not in c2024
assert "<title>February 2024: $150.50</title>" in c2024 and "<title>December 2024: $1,200.00</title>" in c2024
print("A bar per month with spending, exact amount on hover; empty year says so: OK")

assert c2024.count('class="peak"') == 1 and ">$1,200.00</text>" in c2024      # busiest month labeled, once
assert c2026.count('class="peak"') == 1 and ">$107.23</text>" in c2026
print("Only the busiest month of each year gets a value label: OK")

ticks = [re.findall(r'class="tick"[^>]*>([^<]*)<', c) for c in charts]
assert ticks[0] == ticks[1] == ticks[2] == ["$0", "$500", "$1,000", "$1,500"], ticks   # one shared scale
print("All charts share one scale (same ticks), so years compare by bar height: OK")

assert all(re.search(r'<svg viewBox="0 0 920 230" role="img" aria-label="Spending by month in \d+">', c) for c in charts)
assert "<tr" not in "".join(charts)
print("Charts are accessible inline SVG (role=img + label), no table rows mixed in: OK")

assert _nice_scale(0) == (1, 1) and _nice_scale(9) == (10, 5) and _nice_scale(1200) == (1500, 500)
assert _nice_scale(5049.54) == (6000, 2000) and _nice_scale(40) == (40, 10) and _nice_scale(0.5) == (1, 1)
print("Axis scale picks round 1/2/5 steps with at most 4 intervals: OK")

assert "<figure" not in render_orders_html([]) and "<figure" not in render_orders_html([o("T9", "x", "1")])
print("No placeable orders -> no charts: OK")
print("\nALL MONTHLY CHART TESTS PASSED")
