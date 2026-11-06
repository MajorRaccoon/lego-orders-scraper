# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the macOS app. Build with build_mac.sh (or:
#   pyinstaller --noconfirm --clean LEGO_Order_Scraper.spec)
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []
for pkg in ("playwright", "webview"):  # playwright ships a Node driver that must be bundled
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:  # webview is optional (the app falls back to your browser)
        print(f"spec: skipping {pkg}: {e}")
for pkg in ("playwright", "flask", "werkzeug", "cryptography"):
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

# modules the launcher imports lazily / that run in the child process
hiddenimports += [
    "lego_orders_scraper", "lego_orders_webapp", "lego_orders_to_html",
    "lego_repair_json_from_csv", "strip_non_ascii",
    "cryptography.hazmat.primitives.ciphers.aead",
    "cryptography.hazmat.primitives.kdf.pbkdf2",
    "werkzeug.serving",
]

icon = "icon.icns" if os.path.exists("icon.icns") else None

a = Analysis(
    ["lego_orders_app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [("u", None, "OPTION")],  # unbuffered stdio: live progress in the web page
    exclude_binaries=True,
    name="LEGO Order Scraper",
    console=False,
    argv_emulation=False,  # must stay False: the app re-runs itself with --run-scraper
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.datas, name="LEGO Order Scraper")
app = BUNDLE(
    coll,
    name="LEGO Order Scraper.app",
    icon=icon,
    bundle_identifier="local.lego-order-scraper",
    info_plist={
        "CFBundleName": "LEGO Order Scraper",
        "CFBundleDisplayName": "LEGO Order Scraper",
        "CFBundleShortVersionString": "1.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)
