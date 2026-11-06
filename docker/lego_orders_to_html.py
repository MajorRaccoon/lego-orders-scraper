#!/usr/bin/env python3
"""
lego_orders_to_html.py

Builds the self-contained HTML order-history report from an EXISTING
lego_orders.json file -- no browser, no network, no LEGO.com involved at
all. This is "mode 2" of the HTML report feature; "mode 1" is passing
--html directly to lego_orders_scraper.py while it fetches.

Handy for regenerating the report any time (e.g. after manually editing the
JSON, or just to re-render with a newer version of the report styling)
without re-scraping anything.

USAGE
-----
    python lego_orders_to_html.py                       # uses the defaults
    python lego_orders_to_html.py --json lego_orders.json --html lego_orders.html
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lego_orders_scraper import (  # reuse the same data model/rendering/atomic-write logic
    LegoOrder,
    write_html_report,
    __version__,
)


def convert(json_path, html_path):
    json_path = Path(json_path)

    with open(json_path, "r", encoding="utf-8") as f:
        raw_orders = json.load(f)
    orders = [LegoOrder.from_dict(o) for o in raw_orders]

    write_html_report(orders, html_path)

    with_items = sum(1 for o in orders if o.items)
    print(
        f"Wrote {html_path}: {len(orders)} order(s), {with_items} of them "
        f"with item detail."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Build the self-contained HTML order-history report from an "
        "existing lego_orders.json, without fetching anything from LEGO.com."
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    parser.add_argument("--json", default="lego_orders.json", help="Path to the JSON file to read.")
    parser.add_argument("--html", default="lego_orders.html", help="Path to the HTML file to write.")
    args = parser.parse_args()
    convert(args.json, args.html)


if __name__ == "__main__":
    main()
