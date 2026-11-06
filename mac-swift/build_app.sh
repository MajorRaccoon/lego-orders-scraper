#!/bin/bash
# Builds "dist/LEGO Order Scraper.app" (native Swift version) and a zip of it.
# Needs Xcode (or its command-line tools) installed. Usage:  ./build_app.sh
set -euo pipefail
cd "$(dirname "$0")"

APP="LEGO Order Scraper"
BUNDLE_ID="local.lego-order-scraper"
VERSION=$(sed -n 's/^public let legoSwiftVersion = "\(.*\)"/\1/p' Sources/LegoCore/Models.swift)
OUT="dist/$APP.app"

echo "==> Running the tests"
swift test 2>&1 | grep -E "Executed [0-9]+ tests" | tail -1   # fails the build if any test fails

echo "==> Building v$VERSION (release)"
ARCHS=(--arch arm64 --arch x86_64)   # universal: runs on Apple Silicon and Intel Macs
if ! swift build -c release --product LegoOrderScraperApp "${ARCHS[@]}" >/dev/null 2>&1; then
  echo "    (universal build not available here -- building for this Mac's chip only)"
  ARCHS=()
  swift build -c release --product LegoOrderScraperApp
fi
BIN_DIR=$(swift build -c release --product LegoOrderScraperApp ${ARCHS[@]+"${ARCHS[@]}"} --show-bin-path)

echo "==> Assembling $OUT"
rm -rf "$OUT"
mkdir -p "$OUT/Contents/MacOS" "$OUT/Contents/Resources"
cp "$BIN_DIR/LegoOrderScraperApp" "$OUT/Contents/MacOS/$APP"
printf 'APPL????' > "$OUT/Contents/PkgInfo"

echo "==> Making the icon"
ICONSET=$(mktemp -d)/AppIcon.iconset
mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s Resources/icon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) Resources/icon.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$OUT/Contents/Resources/AppIcon.icns"

cat > "$OUT/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>$APP</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleName</key><string>$APP</string>
  <key>CFBundleDisplayName</key><string>$APP</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>2.$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSHumanReadableCopyright</key><string>Personal tool. Not affiliated with the LEGO Group.</string>
</dict>
</plist>
PLIST

echo "==> Ad-hoc signing (needed for Apple Silicon to run it)"
codesign --force --deep --sign - "$OUT"
codesign --verify --deep "$OUT"

echo "==> Zipping"
rm -f "dist/LEGO-Order-Scraper-native-mac.zip"
ditto -c -k --keepParent "$OUT" "dist/LEGO-Order-Scraper-native-mac.zip"

echo
echo "Built: mac-swift/$OUT ($(lipo -archs "$OUT/Contents/MacOS/$APP"))"
echo "Drag 'LEGO Order Scraper.app' to Applications, then double-click it."
