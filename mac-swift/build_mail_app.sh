#!/bin/bash
# Builds "dist/LEGO Mail Orders.app" (reads LEGO order emails from Apple Mail) and a zip of it.
# Needs Xcode (or its command-line tools) installed. Usage:  ./build_mail_app.sh
set -euo pipefail
cd "$(dirname "$0")"

APP="LEGO Mail Orders"
BUNDLE_ID="local.lego-mail-orders"
VERSION=$(sed -n 's/^public let legoMailVersion = "\(.*\)"/\1/p' Sources/LegoMail/Version.swift)
OUT="dist/$APP.app"
ZIP="dist/LEGO-Mail-Orders-mac.zip"

echo "==> Running the tests"
TEST_LOG=$(mktemp)
if ! swift test >"$TEST_LOG" 2>&1; then   # fails the build if any test fails
  echo "    Tests failed or didn't build. Last lines of the output:"
  tail -80 "$TEST_LOG"
  exit 1
fi
grep -E "Executed [0-9]+ tests" "$TEST_LOG" | tail -1

echo "==> Building v$VERSION (release)"
ARCHS=(--arch arm64 --arch x86_64)   # universal: runs on Apple Silicon and Intel Macs
if ! swift build -c release --product LegoMailOrdersApp "${ARCHS[@]}" >/dev/null 2>&1; then
  echo "    (universal build not available here -- building for this Mac's chip only)"
  ARCHS=()
  swift build -c release --product LegoMailOrdersApp
fi
BIN_DIR=$(swift build -c release --product LegoMailOrdersApp ${ARCHS[@]+"${ARCHS[@]}"} --show-bin-path)

echo "==> Assembling $OUT"
rm -rf "$OUT"
mkdir -p "$OUT/Contents/MacOS" "$OUT/Contents/Resources"
cp "$BIN_DIR/LegoMailOrdersApp" "$OUT/Contents/MacOS/$APP"
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
  <key>CFBundleShortVersionString</key><string>1.$VERSION</string>
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
rm -f "$ZIP"
ditto -c -k --keepParent "$OUT" "$ZIP"

echo
echo "Built: mac-swift/$OUT ($(lipo -archs "$OUT/Contents/MacOS/$APP"))"
echo "Drag 'LEGO Mail Orders.app' to Applications, then give it Full Disk Access (see README-mail.md)."
