"""Safari/WebKit page text (the native Mac app's browser) runs LEGO's hidden "Price" label into the
amount: "Price$119.99", "Price-", "product.salePrice$4.99". Prices must still be read, exactly as from
Chromium's text where those are separate lines."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys
sys.path.insert(0, SRC)
from lego_orders_scraper import parse_order_detail, _split_glued_price_line

WEBKIT = """Order overview
Shipped
Tracking number: 1Z0000000000000001
Holiday Set
Item: 11111
Quantity: 1
Price$119.99
Free Promo Set
Item: 40000
Quantity: 1
Price-
Bag Tag
Item: 5008114
Quantity: 2
Price$9.99
product.salePrice$4.99
Insiders Set
Item: 21330
Quantity: 1
Price$69.99$48.99LEGO® Insiders Price
Minifigure Factory
Item: 3850082
ID: ABCDEF123
Quantity: 1
Price $11.99
Canceled
Reward Item
Item: 910053
Quantity: 2
Price$0.00
Support
"""
CHROMIUM = (WEBKIT.replace("Price$", "Price\n$").replace("Price-", "Price\n-")
            .replace("product.salePrice$", "product.salePrice\n$").replace("$69.99$48.99LEGO", "$69.99\n$48.99\nLEGO")
            .replace("Price $11.99", "Price\n$11.99"))

w, c = parse_order_detail(WEBKIT), parse_order_detail(CHROMIUM)
assert [i.to_dict() for i in w] == [i.to_dict() for i in c], "WebKit and Chromium text parse differently"
by = {i.name: i for i in w}
assert len(w) == 6, [i.name for i in w]
assert by["Holiday Set"].prices == {"product.regularPrice": "119.99", "product.salePrice": "119.99"}
assert not by["Holiday Set"].is_free_gift
assert by["Free Promo Set"].is_free_gift and by["Free Promo Set"].prices["product.salePrice"] is None
assert by["Bag Tag"].prices == {"product.regularPrice": "9.99", "product.salePrice": "4.99"}
assert by["Insiders Set"].prices == {"product.regularPrice": "69.99", "product.salePrice": "48.99"}
assert by["Minifigure Factory"].custom_id == "ABCDEF123" and by["Minifigure Factory"].prices["product.salePrice"] == "11.99"
assert by["Reward Item"].status == "Canceled" and by["Reward Item"].prices["product.salePrice"] == "0.00"
print("Glued WebKit price lines parse exactly like Chromium's separate lines (normal, free, sale, Insiders): OK")

# Only genuine price lines are split.
for keep in ["-$15.00", "Price", "$9.99", "Prices may vary", "Price match", "Holiday Set", "Price$", "Pricey$5.00", ""]:
    assert _split_glued_price_line(keep) == [keep], keep
assert _split_glued_price_line("Price$1,234.50") == ["Price", "$1,234.50"]
print("Other lines (summary discounts, words starting with 'Price', plain amounts) left alone: OK")
print("\nALL WEBKIT PRICE-LINE TESTS PASSED")
