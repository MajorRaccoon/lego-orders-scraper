"""The native Swift Mac app (mac-swift/) must parse pages and write files EXACTLY like the Python
scraper: same orders/items/summary from the same page text, byte-identical JSON and CSV, and the
same HTML report (apart from the "Generated ..." timestamp). Builds the small `lego-parity`
helper with `swift build`; skipped where Swift isn't installed (e.g. Linux/Docker)."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import json, re, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, SRC)
from lego_orders_scraper import (LegoOrder, parse_order_list, parse_order_detail, _parse_order_summary,
                                 _parse_order_date, write_outputs, write_html_report)

PKG = Path(SRC) / "mac-swift"
if not (PKG / "Package.swift").exists() or not shutil.which("swift"):
    print("SKIPPED: mac-swift/ or the swift compiler not found"); sys.exit(0)

r = subprocess.run(["swift", "build", "--product", "lego-parity"], cwd=PKG, capture_output=True, text=True, timeout=170)
assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
BIN = subprocess.run(["swift", "build", "--show-bin-path"], cwd=PKG, capture_output=True, text=True).stdout.strip() + "/lego-parity"

def swift(*args, stdin=""):
    p = subprocess.run([BIN, *args], input=stdin.encode(), capture_output=True, timeout=60)
    assert p.returncode == 0, p.stderr.decode()
    return p.stdout.decode()

def py_json(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False)

# ---- page text fixtures (every shape the parser tests cover, plus nasty edge cases) ----
LISTS = [
    """My Orders\nBackordered\nOrder Number: T514535382\nOrder Date: September 7, 2026\nTotal: $1,369.95
6 items in this order\n+2\nManage my order\nDelivered\nOrder Number: T500000001\nOrder Date: June 1, 2025
Total: $12.34\n1 item in this order\n""",
    """Shipped\nOrder Number: T111111111\nOrder Date: June 1, 2026\nTotal: $10.00\n1 gift card in this order
Shipped\nOrder Number: T222222222\nOrder Date: May 1, 2026\nTotal: $99.99\n2 items in this order
Backordered\nOrder Number: T333333333\nOrder Date: April 1, 2026\n2 items in this order\n""",
    "Just placed\nOrder Number: T555555555\nOrder Date: October 6, 2026\nIn Process\nOrder Number: T666666666\n"
    "Order Date: October 6, 2026\nTotal: $579.13\n2 items in this order\n",
    "Order Number: T1\n  Order Date:   May 1, 2026  \r\n\n\nTotal: $5\n\u00a0\n3 items in this order\nOrder Number: X9\n",
    "", "nothing here",
]
DETAILS = [
    """Order details\nShipped\nTracking number: 1Z999AA10123456784\nTechnic\u2122 Hub\nItem: 88012\nQuantity: 2
Price\n$49.99\nFree Poster\nItem: 5006\nQuantity: 1\nPrice\n-\nSale Set\nItem: 10300\nQuantity: 1\nPrice
$22.99\nproduct.salePrice\n$16.09\nInsiders Set\nItem: 21330\nQuantity: 1\nPrice\n$69.99\n$48.99
LEGO\u00ae Insiders Price\nBackordered\nBack Item\nItem: 76000\nQuantity: 3\nPrice\n$10.00\nBricks and Pieces
Pick A Brick Container\nItem: 999\nPrice\n$5.00\nRound Brick 1x1\nSKU: 300121\nQuantity: 25\nPrice\n$2.50
Digital Gifting\nLEGO E-Gift Card\nQuantity: 1\nPrice\n$25.00\nCustom Minifigure\nItem: 3850083
ID: ABC-123-XYZ\nQuantity: 1\nPrice\n$9.99\nOrder summary\nSubtotal\n$754.96\nDelivery\n$0.00\nTax\n$54.08
LEGO\u00ae Insiders discount\n-$9.00\nTotal\n$800.04\n""",
    "Caf\u00e9 \u201cQuoted\u201d \"Set\", with comma\nItem: 1\nQuantity: x\nPrice\n$1,234.50\n"
    "Delivered\nTracking number: ABC\nTracking number: has space\nWeird\nSKU:   77  \nPrice\n$$3.00\n",
    "Order summary\nSubtotal $10.00\nShipping $4.99\nTax $0.80\nDiscount -$2.00\nTotal $13.79\n",
    "Order summary\nSubtotal $100.00\nLEGO\u00ae Insiders discount -$10.00\nDiscount -$5.00\nTotal $85.00\nTotal $1.00\n",
    "Order summary\nSubtotal\nTotal\n$5.00\n", "Order summary\nSubtotal $1.00\n", "no summary block", "",
    # WebKit (Safari engine) runs the hidden "Price" label into the amount:
    "Set A\nItem: 1\nQuantity: 1\nPrice$119.99\nFree\nItem: 2\nQuantity: 1\nPrice-\nTag\nItem: 3\nQuantity: 2\n"
    "Price$9.99\nproduct.salePrice$4.99\nIns\nItem: 4\nQuantity: 1\nPrice$69.99$48.99LEGO® Insiders Price\n"
    "Gift\nQuantity: 1\nPrice $25.00\nOdd\nItem: 5\nQuantity: 1\nPricey$5.00\n-$15.00\nPrice$\nPrice match\n",
]

for text in LISTS:
    assert swift("list", stdin=text) == py_json([o.to_dict() for o in parse_order_list(text)]), text
    assert swift("list", "1", stdin=text) == py_json([o.to_dict() for o in parse_order_list(text, max_orders=1)]), text
print(f"parse_order_list: Swift == Python on {len(LISTS)} pages (+ max_orders): OK")

for text in DETAILS + LISTS:
    assert swift("detail", stdin=text) == py_json([i.to_dict() for i in parse_order_detail(text)]), text
    assert swift("summary", stdin=text) == py_json(_parse_order_summary(text)), text
print(f"parse_order_detail + order summary: Swift == Python on {len(DETAILS + LISTS)} pages: OK")

dates = ["September 7, 2026", "january 31, 2024", "MAY  1,  2026", "June 07, 2025", "February 29, 2024",
         "February 29, 2025", "February 30, 2024", "Sept 7, 2026", "2026-09-07", "garbage", "June 1, 26",
         "June 1 2026", "June 32, 2026", "December 31, 0000"]
py_dates = [(_parse_order_date(d).strftime("%m/%d/%Y") if _parse_order_date(d) else "None") for d in dates]
assert swift("dates", stdin="\n".join(dates) + "\n").splitlines() == py_dates
print("order-date parsing: Swift == Python (case, spacing, leap years, junk): OK")

# ---- full file outputs from the same orders ----
orders = [
    {"order_number": "T900000001", "status": "Shipped", "order_date": "June 15, 2026", "total": "123.45",
     "item_count_listed": 3, "url": "https://www.lego.com/en-us/member/orders/details/T900000001",
     "items": [
        {"name": 'Technic Hub <script>alert("x")</script> & Friends, \'quoted\'', "item_number": "42177",
         "custom_id": None, "quantity": 2, "prices": {"product.regularPrice": "59.99", "product.salePrice": "49.99"},
         "is_free_gift": False, "is_piece": False, "is_gift_card": False, "status": "Shipped",
         "tracking_number": "1Z999AA10123456784"},
        {"name": "Line\nbreak \u00e9\u2122 \t tab \u0001 ctl", "item_number": "6335381", "custom_id": "abc123",
         "quantity": 1, "prices": {"product.regularPrice": None, "product.salePrice": None},
         "is_free_gift": True, "is_piece": True, "is_gift_card": False, "status": "Shipped", "tracking_number": None},
        {"name": "LEGO Gift Card", "item_number": None, "custom_id": None, "quantity": 1,
         "prices": {"product.salePrice": "25.00", "product.regularPrice": "25.00"},
         "is_free_gift": False, "is_piece": False, "is_gift_card": True, "status": None, "tracking_number": None}],
     "summary": {"total": "123.45", "subtotal": "134.98", "delivery": "0.00", "tax": "8.47", "insiders_discount": "-20.00"}},
    {"order_number": "T900000002", "status": "Processing", "order_date": "July 1, 2026", "total": "10.00",
     "item_count_listed": 1, "url": "u/2"},
    {"order_number": "T3", "status": None, "order_date": "December 31, 2024", "total": "1,200.00",
     "item_count_listed": None, "url": None, "fetch_error": "Timeout 20000ms exceeded.",
     "items": [{"name": "Old style", "item_number": "1", "quantity": 1, "prices": {}, "is_free_gift": False}]},
    {"order_number": "T4", "status": "Shipped", "order_date": "February 3, 2024", "total": "-5.5", "url": "u"},
    {"order_number": "T5", "status": "Shipped", "order_date": "not a date", "total": "abc", "url": "u"},
    {"order_number": "T6", "status": "Shipped", "order_date": "January 5, 2026", "total": "0.105", "url": "u"},
    {"order_number": "T900000002", "status": "dup", "order_date": "July 1, 2026", "total": "1", "url": "u",
     "items": [{"name": "dup wins", "item_number": "9", "quantity": 1,
                "prices": {"product.regularPrice": "1.00", "product.salePrice": "1.00"}, "is_free_gift": False}]},
]
tmp = Path(tempfile.mkdtemp(prefix="lego_parity_"))
src = tmp / "in.json"; src.write_text(json.dumps(orders, ensure_ascii=False), encoding="utf-8")
py_orders = [LegoOrder.from_dict(d) for d in json.loads(src.read_text(encoding="utf-8"))]
write_outputs(py_orders, tmp / "py.json", tmp / "py.csv", quiet=True)
write_html_report(py_orders, tmp / "py.html")
swift("render", str(src), str(tmp / "sw.json"), str(tmp / "sw.csv"), str(tmp / "sw.html"))

assert (tmp / "sw.json").read_bytes() == (tmp / "py.json").read_bytes(), "JSON differs"
print("JSON output: byte-identical (key order, escaping, unicode, dedupe, old-style items): OK")
assert (tmp / "sw.csv").read_bytes() == (tmp / "py.csv").read_bytes(), "CSV differs"
print("CSV output: byte-identical (quoting, newlines, True/False, blanks): OK")

def no_stamp(p): return re.sub(r'<p class="generated">Generated [^<]*</p>', "", p.read_text(encoding="utf-8"))
sw_html, py_html = no_stamp(tmp / "sw.html"), no_stamp(tmp / "py.html")
if sw_html != py_html:
    for n, (a, b) in enumerate(zip(sw_html, py_html)):
        if a != b: raise AssertionError(f"HTML differs at {n}: swift={sw_html[n-80:n+80]!r} python={py_html[n-80:n+80]!r}")
    raise AssertionError("HTML differs in length")
stamp = re.search(r'<p class="generated">Generated ([^<]*)</p>', (tmp / "sw.html").read_text()).group(1)
assert re.fullmatch(r"[A-Z][a-z]+ \d\d, \d{4} at \d\d:\d\d [AP]M", stamp), stamp
print("HTML report: identical apart from the timestamp, which uses the same format: OK")

# "Leave out tracking numbers": identical output with the option on, too.
write_outputs(py_orders, tmp / "pyn.json", tmp / "pyn.csv", quiet=True, include_tracking=False)
write_html_report(py_orders, tmp / "pyn.html", include_tracking=False)
swift("render", str(src), str(tmp / "swn.json"), str(tmp / "swn.csv"), str(tmp / "swn.html"), "--no-tracking")
assert (tmp / "swn.json").read_bytes() == (tmp / "pyn.json").read_bytes()
assert (tmp / "swn.csv").read_bytes() == (tmp / "pyn.csv").read_bytes()
assert no_stamp(tmp / "swn.html") == no_stamp(tmp / "pyn.html")
assert "1Z999AA10123456784" not in (tmp / "swn.csv").read_text()
print("No-tracking option: JSON/CSV/HTML identical between Swift and Python: OK")

# A Python-written file loads in Swift and re-saves unchanged (and vice versa): resume works across versions.
swift("render", str(tmp / "py.json"), str(tmp / "sw2.json"), str(tmp / "sw2.csv"), str(tmp / "sw2.html"))
assert (tmp / "sw2.json").read_bytes() == (tmp / "py.json").read_bytes()
print("Python-written lego_orders.json round-trips through Swift unchanged: OK")
print("\nALL SWIFT PARITY TESTS PASSED")
