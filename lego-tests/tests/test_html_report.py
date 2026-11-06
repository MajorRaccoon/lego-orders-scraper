"""
Verifies render_orders_html() / write_html_report() (the new --html report
feature): orders with full item detail render correctly and are
HTML-escaped, orders with no item detail render a note instead of crashing,
order-summary fields render only when present, and write_html_report()
actually writes a well-formed file to disk (atomically, via the same
_atomic_write() the JSON/CSV outputs use).
"""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, SRC)
from lego_orders_scraper import LegoOrder, LegoOrderLine, render_orders_html, write_html_report

# --- Order 1: full detail, including a sale price, an item with HTML
# special characters in its name (must be escaped, not break the markup),
# a free-gift/piece/gift-card flag each, and a full order summary. ---------
order1 = LegoOrder.from_dict({
    "order_number": "T900000001",
    "status": "Shipped",
    "order_date": "June 15, 2026",
    "total": "123.45",
    "item_count_listed": 3,
    "url": "https://www.lego.com/en-us/account/orders/details/T900000001",
    "items": [
        {
            "name": 'Technic Hub <script>alert("x")</script> & Friends',
            "item_number": "42177", "custom_id": None, "quantity": 2,
            "prices": {"product.regularPrice": "59.99", "product.salePrice": "49.99"},
            "is_free_gift": False, "is_piece": False, "is_gift_card": False,
            "status": "Shipped", "tracking_number": "1Z999AA10123456784",
        },
        {
            "name": "Minifigure Wrench", "item_number": "6335381", "custom_id": "abc123",
            "quantity": 1, "prices": {"product.regularPrice": None, "product.salePrice": None},
            "is_free_gift": True, "is_piece": True, "is_gift_card": False,
            "status": "Shipped", "tracking_number": None,
        },
        {
            "name": "LEGO Gift Card", "item_number": None, "custom_id": None,
            "quantity": 1, "prices": {"product.regularPrice": "25.00", "product.salePrice": "25.00"},
            "is_free_gift": False, "is_piece": False, "is_gift_card": True,
            "status": None, "tracking_number": None,
        },
    ],
    "summary": {
        "subtotal": "134.98", "delivery": "0.00", "tax": "8.47",
        "insiders_discount": "-20.00", "total": "123.45",
    },
})

# --- Order 2: no item detail at all (e.g. skipped by --since-date) --
# must render a note, not crash, and must not claim any items. -------------
order2 = LegoOrder.from_dict({
    "order_number": "T900000002",
    "status": "Processing",
    "order_date": "July 1, 2026",
    "total": "10.00",
    "item_count_listed": 1,
    "url": "https://www.lego.com/en-us/account/orders/details/T900000002",
    # no "items" key, no "summary" key
})

orders = [order1, order2]

html_out = render_orders_html(orders, title="Test Order History")

# --- Basic structural sanity -----------------------------------------------
assert html_out.startswith("<!doctype html>"), html_out[:50]
assert "<title>Test Order History</title>" in html_out
assert html_out.count("<html") == 1 and html_out.count("</html>") == 1
print("Renders a single well-formed HTML document: OK")

# --- Both orders appear, in the index and as sections ----------------------
assert 'id="order-T900000001"' in html_out
assert 'id="order-T900000002"' in html_out
assert html_out.count("T900000001") >= 2  # index row + section heading
assert html_out.count("T900000002") >= 2
print("Both orders appear in the index and as their own sections: OK")

# --- HTML-escaping: the raw script tag must never appear unescaped --------
assert "<script>alert" not in html_out, "unescaped HTML found in output -- injection risk"
assert "&lt;script&gt;" in html_out
assert "&amp; Friends" in html_out
print("Item names with HTML special characters are escaped, not injected: OK")

# --- Sale price shown as a strikethrough regular price + sale price -------
assert "$59.99" in html_out and "$49.99" in html_out
print("Regular vs. sale price both render when they differ: OK")

# --- Flags render as tags -----------------------------------------------
assert ">free gift<" in html_out
assert ">piece<" in html_out
assert ">gift card<" in html_out
print("is_free_gift / is_piece / is_gift_card flags render as tags: OK")

# --- Tracking number renders when present ----------------------------------
assert "1Z999AA10123456784" in html_out
print("Tracking number renders: OK")

# --- Order summary renders every present field, correctly formatted -------
assert "$134.98" in html_out  # subtotal
assert "$8.47" in html_out  # tax
assert "-$20.00" in html_out  # insiders discount (negative)
assert "LEGO Insiders discount" in html_out
assert "$123.45" in html_out  # total (also order1's order.total)
print("Order summary (subtotal/tax/insiders discount/total) renders with correct formatting: OK")

# --- Order 2 (no items) gets a "no detail" note, not a crash or a fake
# empty table claiming 0 items silently. ------------------------------------
assert "No item detail fetched for this order yet." in html_out
assert "no detail" in html_out  # index badge
print("Order with no item detail renders a clear note instead of crashing or hiding the gap: OK")

# --- Stats block reflects the actual counts --------------------------------
assert "Orders</div>" in html_out
# 2 orders total, 1 with items, 3 total items
import re
stat_numbers = re.findall(r'<div class="n">([^<]*)</div>', html_out)
assert "2" in stat_numbers, stat_numbers  # total orders
assert "1" in stat_numbers, stat_numbers  # with item detail
assert "3" in stat_numbers, stat_numbers  # total items
print("Summary stat cards reflect accurate counts: OK")

# --- An order with an empty summary dict renders no summary table at all --
order3 = LegoOrder.from_dict({
    "order_number": "T900000003", "status": "Shipped", "order_date": "Aug 1, 2026",
    "total": "5.00", "item_count_listed": 1,
    "url": "https://www.lego.com/en-us/account/orders/details/T900000003",
    "items": [{
        "name": "Small Part", "item_number": "1", "custom_id": None, "quantity": 1,
        "prices": {"product.regularPrice": "5.00", "product.salePrice": "5.00"},
        "is_free_gift": False, "is_piece": False, "is_gift_card": False,
        "status": "Shipped", "tracking_number": None,
    }],
    # no "summary" key at all
})
html_no_summary = render_orders_html([order3])
assert '<table class="summary-table">' not in html_no_summary
print("Order with no summary data renders no summary table (not an empty/broken one): OK")

# --- write_html_report(): writes a real file, atomically, and it matches
# what render_orders_html() produces for the same orders. -------------------
tmp_dir = Path(tempfile.mkdtemp(prefix="lego_html_test_"))
html_path = tmp_dir / "report.html"
write_html_report(orders, html_path)
assert html_path.exists()
written = html_path.read_text(encoding="utf-8")
assert written.startswith("<!doctype html>")
assert "T900000001" in written and "T900000002" in written
# No leftover .tmp file from the atomic-write dance.
leftover_tmp_files = list(tmp_dir.glob("*.tmp*"))
assert not leftover_tmp_files, f"atomic write left temp file(s) behind: {leftover_tmp_files}"
print("write_html_report() writes a complete, well-formed file to disk with no leftover temp file: OK")

print("\nALL HTML REPORT TESTS PASSED")
