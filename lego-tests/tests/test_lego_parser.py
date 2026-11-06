"""parse_order_list() and parse_order_detail() on every page shape seen in the wild:
normal, free gift, sale price, Insiders price, multi-shipment + tracking, per-item status,
Bricks and Pieces (SKU pieces), digital gift card, custom ID (Minifigure Factory)."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys
sys.path.insert(0, SRC)
from lego_orders_scraper import parse_order_list, parse_order_detail

# ---- order list ----------------------------------------------------------
LIST = """My Orders
Backordered
Order Number: T514535382
Order Date: September 7, 2026
Total: $1,369.95
6 items in this order
+2
Manage my order
Delivered
Order Number: T500000001
Order Date: June 1, 2025
Total: $12.34
1 item in this order
"""
orders = parse_order_list(LIST)
assert [o.order_number for o in orders] == ["T514535382", "T500000001"]
a, b = orders
assert (a.status, a.order_date, a.total, a.item_count_listed) == ("Backordered", "September 7, 2026", "1,369.95", 6)
assert (b.status, b.order_date, b.total, b.item_count_listed) == ("Delivered", "June 1, 2025", "12.34", 1)
assert a.url.endswith("/T514535382") and a.items == [] and a.summary == {}
assert [o.order_number for o in parse_order_list(LIST, max_orders=1)] == ["T514535382"]
print("parse_order_list: fields, thousands-comma totals, singular 'item', +N marker ignored, max_orders: OK")

# ---- order detail --------------------------------------------------------
DETAIL = """Order details
Shipped
Tracking number: 1Z999AA10123456784
Technic™ Hub
Item: 88012
Quantity: 2
Price
$49.99
Free Poster
Item: 5006
Quantity: 1
Price
-
Sale Set
Item: 10300
Quantity: 1
Price
$22.99
product.salePrice
$16.09
Insiders Set
Item: 21330
Quantity: 1
Price
$69.99
$48.99
LEGO® Insiders Price
Backordered
Back Item
Item: 76000
Quantity: 3
Price
$10.00
Bricks and Pieces
Pick A Brick Container
Item: 999
Price
$5.00
Round Brick 1x1
SKU: 300121
Quantity: 25
Price
$2.50
Digital Gifting
LEGO E-Gift Card
Quantity: 1
Price
$25.00
Custom Minifigure
Item: 3850083
ID: ABC-123-XYZ
Quantity: 1
Price
$9.99
"""
items = parse_order_detail(DETAIL)
by = {i.name: i for i in items}
assert len(items) == 9, [i.name for i in items]

hub = by["Technic Hub"]                       # ™ stripped
assert (hub.item_number, hub.quantity, hub.status, hub.tracking_number) == ("88012", 2, "Shipped", "1Z999AA10123456784")
assert hub.prices == {"product.regularPrice": "49.99", "product.salePrice": "49.99"}
assert not hub.is_free_gift and not hub.is_piece and not hub.is_gift_card and hub.custom_id is None
print("normal item (+ non-ASCII stripped, shipment status/tracking applied): OK")

free = by["Free Poster"]
assert free.is_free_gift and free.prices == {"product.regularPrice": None, "product.salePrice": None}
print("free gift ('Price / -'): OK")

assert by["Sale Set"].prices == {"product.regularPrice": "22.99", "product.salePrice": "16.09"}
assert by["Insiders Set"].prices == {"product.regularPrice": "69.99", "product.salePrice": "48.99"}
print("sale price and Insiders price both -> regular/sale pair: OK")

back = by["Back Item"]
assert back.status == "Backordered" and back.quantity == 3 and back.tracking_number == "1Z999AA10123456784"
print("per-item status line applies to following items: OK")

cont, piece = by["Pick A Brick Container"], by["Round Brick 1x1"]
assert cont.quantity is None and not cont.is_piece and cont.item_number == "999"
assert piece.is_piece and piece.item_number == "300121" and piece.quantity == 25
print("Bricks and Pieces: container has no quantity; SKU lines are pieces: OK")

gift = by["LEGO E-Gift Card"]
assert gift.is_gift_card and gift.item_number is None and gift.quantity == 1 and gift.prices["product.salePrice"] == "25.00"
print("digital gift card (no Item/SKU line): OK")

mini = by["Custom Minifigure"]
assert mini.custom_id == "ABC-123-XYZ" and mini.item_number == "3850083" and mini.quantity == 1
assert "ID: ABC-123-XYZ" not in by                       # ID line not misread as an item
print("custom ID (Minifigure Factory) captured, not misread as an item: OK")

# serialization shape is stable
d = hub.to_dict()
assert set(d) == {"name", "item_number", "custom_id", "quantity", "prices", "is_free_gift",
                  "is_piece", "is_gift_card", "status", "tracking_number"}, set(d)
print("LegoOrderLine.to_dict key set unchanged: OK")

assert parse_order_detail("") == [] and parse_order_detail("nothing useful here\nat all") == []
print("empty / junk page -> no items, no crash: OK")
print("\nALL PARSER TESTS PASSED")
