"""Per-item status on real order-page shapes: an "In Process" order's items sit under a "Pre-order"
label (it must become their status, not be skipped or read as an item); e-gift cards sit under
"Digital gifting" and have no shipment status, so theirs stays empty."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys
sys.path.insert(0, SRC)
from lego_orders_scraper import parse_order_detail

# WebKit-style text (glued "Price$"), as captured from a real In Process order.
PREORDER = """Order overview
Cancel order
Where are my LEGO® Insiders points?
Your LEGO® Insiders points are on their way.
Pre-order
Freight Depot
Item: 910072
Quantity: 2
Price$439.98
Support
"""
items = parse_order_detail(PREORDER)
assert len(items) == 1, [i.name for i in items]
assert items[0].status == "Pre-order" and items[0].name == "Freight Depot" and items[0].quantity == 2
assert items[0].prices["product.salePrice"] == "439.98"
print("'Pre-order' label becomes the item status (In Process orders): OK")

# A pre-order section followed by a shipped one: each item keeps its own section's status.
MIXED = PREORDER.replace("Support\n", "") + "Shipped\nTracking number: 1Z9\nBag Tag\nItem: 5008114\nQuantity: 1\nPrice$9.99\n"
by = {i.name: i for i in parse_order_detail(MIXED)}
assert by["Freight Depot"].status == "Pre-order" and by["Freight Depot"].tracking_number is None
assert by["Bag Tag"].status == "Shipped" and by["Bag Tag"].tracking_number == "1Z9"
print("Pre-order and Shipped sections on one order keep separate statuses: OK")

GIFT = "Order overview\nDigital gifting\nLEGO E-Gift Card\nQuantity: 1\nPrice$200.00\nSupport\n"
gift = parse_order_detail(GIFT)
assert len(gift) == 1 and gift[0].is_gift_card and gift[0].status is None
print("E-gift cards ('Digital gifting') have no shipment status -> stays empty: OK")

# A gift card after a shipped or pre-order section must not inherit that section's status/tracking.
after = parse_order_detail(MIXED + GIFT.replace("Order overview\n", ""))
card = [i for i in after if i.is_gift_card][0]
assert card.status is None and card.tracking_number is None, card
assert {i.name: i.status for i in after}["Bag Tag"] == "Shipped"
print("Gift card after a Shipped/Pre-order section doesn't inherit its status or tracking: OK")
print("\nALL ITEM-STATUS TESTS PASSED")
