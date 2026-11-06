#!/bin/bash
# The scripts in this folder's root are the SOURCE OF TRUTH. docker/ and mac-app/ need their own
# copies (Docker build context / PyInstaller bundle). Run this after editing any root script.
set -e
cd "$(dirname "$0")"
for d in docker mac-app; do
  cp lego_orders_scraper.py lego_orders_webapp.py lego_orders_to_html.py lego_repair_json_from_csv.py strip_non_ascii.py "$d"/
done
echo "Synced scripts into docker/ and mac-app/"
