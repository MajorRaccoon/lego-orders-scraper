#!/usr/bin/env python3
"""
lego_repair_json_from_csv.py

One-time repair tool for lego_orders_scraper.py output. If your JSON file
has some orders with item detail missing (no "items", or an empty items
list) while the CSV file *does* have item rows for those same order
numbers, this rebuilds the missing "items" in the JSON from the CSV data
and writes the JSON back.

This can happen because of a bug (now fixed in lego_orders_scraper.py)
where LEGO's order list occasionally renders the same order twice while
paginating through "Load More" -- that produced two separate copies of the
order internally, and depending on which one ended up in each output file,
you could end up with an order's items showing correctly in the CSV but
missing from the JSON. This tool reconciles the two using the CSV (which
still has the real data) as the source of truth for anything the JSON is
missing.

The CSV's "regular_price"/"sale_price" columns are used directly to rebuild
each item's "prices" dict. If your CSV predates that split (it only has a
single "price" column), that one value is used for both -- the "was this
on sale, and what was the original price" distinction can't be recovered
from an old-format CSV, since it was never stored there separately.
Everything else (name, item number, custom ID, quantity, free-gift/piece/
gift-card flags, status, tracking number) is fully recovered either way.

USAGE
-----
    python lego_repair_json_from_csv.py                       # uses the defaults
    python lego_repair_json_from_csv.py --json lego_orders.json --csv lego_orders.csv

A backup of the original JSON is written alongside it (e.g.
lego_orders.json.bak) before anything is overwritten.
"""

import argparse
import csv
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lego_orders_scraper import (  # reuse the same data model/atomic-write/dedupe logic
    LegoOrder,
    LegoOrderLine,
    _atomic_write,
    dedupe_orders,
    resolve_output_path,
)


def _to_bool(value):
    return str(value).strip().lower() == "true"


def _prices_from_row(row, has_split_price_columns):
    if has_split_price_columns:
        regular = row.get("regular_price") or None
        sale = row.get("sale_price") or None
        return {"product.regularPrice": regular, "product.salePrice": sale}
    # Legacy CSV (before regular_price/sale_price were split out): one
    # "price" column held whatever was actually paid -- use it for both,
    # since there's no way to recover the pre-sale price separately.
    legacy_price = row.get("price") or None
    return {"product.regularPrice": legacy_price, "product.salePrice": legacy_price}


def load_items_by_order(csv_path):
    """Read the CSV and group its rows back into a per-order list of
    LegoOrderLine objects, in the same shape parse_order_detail() produces."""
    items_by_order = defaultdict(list)
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        has_split_price_columns = bool(
            reader.fieldnames and
            ("regular_price" in reader.fieldnames or "sale_price" in reader.fieldnames)
        )
        for row in reader:
            order_number = row["order_number"]
            item_number = row.get("item_number") or None
            quantity = row.get("quantity")
            items_by_order[order_number].append(
                LegoOrderLine(
                    name=row["item_name"],
                    item_number=item_number,
                    custom_id=row.get("custom_id") or None,
                    quantity=int(quantity) if quantity not in (None, "") else None,
                    prices=_prices_from_row(row, has_split_price_columns),
                    is_free_gift=_to_bool(row.get("is_free_gift", "")),
                    is_piece=_to_bool(row.get("is_piece", "")),
                    is_gift_card=_to_bool(row.get("is_gift_card", "")),
                    status=row.get("item_status") or None,
                    tracking_number=row.get("tracking_number") or None,
                )
            )
    return items_by_order


def repair(json_path, csv_path):
    json_path = Path(json_path)
    csv_path = Path(csv_path)

    with open(json_path, "r", encoding="utf-8") as f:
        raw_orders = json.load(f)
    orders = [LegoOrder.from_dict(o) for o in raw_orders]
    orders = dedupe_orders(orders)

    items_by_order = load_items_by_order(csv_path)

    repaired = []
    for order in orders:
        num = order.order_number
        if not order.items and items_by_order.get(num):
            order.items = items_by_order[num]
            order.fetch_error = None
            repaired.append(num)

    if not repaired:
        print("Nothing to repair -- every order's JSON item detail already matches (or the CSV has nothing extra).")
        return

    backup_path = json_path.with_suffix(json_path.suffix + ".bak")
    shutil.copy2(json_path, backup_path)
    print(f"Backed up the original JSON to {backup_path}")

    def _write_json(tmp_path):
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump([o.to_dict() for o in orders], f, indent=2, ensure_ascii=False)

    _atomic_write(json_path, _write_json)

    print(f"Repaired {len(repaired)} order(s) using item detail found in {csv_path}:")
    for num in repaired:
        print(f"  {num}")
    print(f"\nWrote the repaired data back to {json_path}.")


def main():
    parser = argparse.ArgumentParser(
        description="Repair a lego_orders.json whose item detail for some orders is missing "
        "but is still present in the matching lego_orders.csv."
    )
    parser.add_argument("--json", default="lego_orders.json", help="Path to the JSON file to repair (in place).")
    parser.add_argument("--csv", default="lego_orders.csv", help="Path to the CSV file to repair from.")
    args = parser.parse_args()
    # Relative paths (including the defaults) are in the data folder, same as the scraper's.
    repair(resolve_output_path(args.json), resolve_output_path(args.csv))


if __name__ == "__main__":
    main()
