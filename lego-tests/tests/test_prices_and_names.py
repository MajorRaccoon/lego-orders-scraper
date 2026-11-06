"""_build_prices_dict and _clean_item_name."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys
sys.path.insert(0, SRC)
from lego_orders_scraper import _build_prices_dict, _clean_item_name

assert _build_prices_dict([]) == {"product.regularPrice": None, "product.salePrice": None}
assert _build_prices_dict(["10.00"]) == {"product.regularPrice": "10.00", "product.salePrice": "10.00"}
assert _build_prices_dict(["22.99", "16.09"]) == {"product.regularPrice": "22.99", "product.salePrice": "16.09"}
print("_build_prices_dict: none / one / two prices: OK")

assert _clean_item_name("Technic™ Hub") == "Technic Hub"
assert _clean_item_name("NINJAGO® City Workshops") == "NINJAGO City Workshops"
assert _clean_item_name("Café “Quoted”") == "Caf Quoted"       # deleted, not replaced
assert _clean_item_name("Plain Name 123") == "Plain Name 123"
assert _clean_item_name("") == ""
print("_clean_item_name: non-ASCII deleted (not substituted), ASCII untouched: OK")
print("\nALL PRICES/NAMES TESTS PASSED")
