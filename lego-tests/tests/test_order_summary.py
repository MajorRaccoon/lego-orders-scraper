"""_parse_order_summary: Subtotal/Delivery/Tax/Insiders discount/Discount/Total."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys
sys.path.insert(0, SRC)
from lego_orders_scraper import _parse_order_summary

two_line = """Items...
Order summary
Subtotal
$754.96
Delivery
$0.00
Tax
$54.08
LEGO® Insiders discount
-$9.00
Total
$800.04
"""
assert _parse_order_summary(two_line) == {"subtotal": "754.96", "delivery": "0.00", "tax": "54.08",
                                          "insiders_discount": "-9.00", "total": "800.04"}
print("two-line label/amount layout, Insiders discount kept separate: OK")

same_line = "Order summary\nSubtotal $10.00\nShipping $4.99\nTax $0.80\nDiscount -$2.00\nTotal $13.79\n"
r = _parse_order_summary(same_line)
assert r == {"subtotal": "10.00", "delivery": "4.99", "tax": "0.80", "discount": "-2.00", "total": "13.79"}, r
print("same-line layout, 'Shipping' alias -> delivery, generic Discount: OK")

both = "Order summary\nSubtotal $100.00\nLEGO® Insiders discount -$10.00\nDiscount -$5.00\nTotal $85.00\n"
r = _parse_order_summary(both)
assert r["insiders_discount"] == "-10.00" and r["discount"] == "-5.00"
print("Insiders discount and generic Discount tracked under separate keys: OK")

assert _parse_order_summary("no summary block on this page") == {}
r = _parse_order_summary("Order summary\nSubtotal\nTotal\n$5.00\n")
assert "subtotal" not in r or r["subtotal"] != "5.00"
assert _parse_order_summary("Order summary\nSubtotal $1.00\n") == {"subtotal": "1.00"}
print("absent block -> {}; absent lines omitted, never fabricated: OK")
print("\nALL ORDER-SUMMARY TESTS PASSED")
