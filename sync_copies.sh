#!/bin/bash
# The scripts in this folder's root are the SOURCE OF TRUTH. docker/, mac-app/ and windows-app/
# need their own copies (Docker build context / PyInstaller bundles). The app launcher
# (lego_orders_app.py) lives in mac-app/ and is copied to windows-app/. Run this after editing.
set -e
cd "$(dirname "$0")"
for d in docker mac-app windows-app; do
  cp lego_orders_scraper.py lego_orders_webapp.py lego_orders_to_html.py lego_repair_json_from_csv.py strip_non_ascii.py "$d"/
done
cp mac-app/lego_orders_app.py mac-app/icon.png windows-app/
echo "Synced scripts into docker/, mac-app/ and windows-app/"
