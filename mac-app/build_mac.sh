#!/bin/bash
# Builds "LEGO Order Scraper.app" (run on a Mac; builds for THIS Mac's chip).
# Needs Python 3.10+ (e.g. `brew install python`). Usage:  ./build_mac.sh
set -euo pipefail
cd "$(dirname "$0")"

[ "$(uname)" = "Darwin" ] || { echo "This must be run on macOS (PyInstaller can't cross-build a Mac app)."; exit 1; }
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || { echo "Need Python 3.10 or newer ('$PY' is $("$PY" -V)). Try: brew install python  (or PYTHON=python3.12 ./build_mac.sh)"; exit 1; }

echo "==> Creating build environment"
"$PY" -m venv .venv-build
source .venv-build/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements-mac.txt

echo "==> Making the icon"
python make_icon.py
rm -rf icon.iconset && mkdir icon.iconset
for s in 16 32 128 256 512; do
  sips -z $s $s icon.png --out "icon.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) icon.png --out "icon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns icon.iconset -o icon.icns

echo "==> Building the app (takes a few minutes)"
rm -rf build dist
pyinstaller --noconfirm --clean LEGO_Order_Scraper.spec

APP="dist/LEGO Order Scraper.app"
# Remove the loose onedir folder PyInstaller also leaves in dist/ -- only the .app should be used/copied.
rm -rf "dist/LEGO Order Scraper"
echo "==> Ad-hoc signing (needed for Apple Silicon to run it)"
codesign --force --deep --sign - "$APP"

echo "==> Zipping for sharing"
ditto -c -k --keepParent "$APP" "dist/LEGO-Order-Scraper-mac.zip"

echo
echo "Done:  $PWD/$APP"
echo "Drag the .app (the icon named 'LEGO Order Scraper' ending in .app) to /Applications, then double-click."
echo "Do NOT copy anything from inside it."
echo "(Shared copies: see README-mac.md for the one-time 'Open Anyway' step.)"
