# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Windows app. Built on Windows only (PyInstaller can't cross-build):
#   - automatically by GitHub Actions (.github/workflows/windows-app.yml), or
#   - on a Windows PC with build_windows.ps1.
# The scripts in this folder are copies made by ../sync_copies.sh (the repo root is the source
# of truth; lego_orders_app.py comes from mac-app/).
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []
d, b, h = collect_all("playwright")  # playwright ships a Node.js driver that must be bundled
datas += d; binaries += b; hiddenimports += h
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
    "win32crypt",  # --cookie-source on Windows (pywin32)
]

icon = "icon.ico" if os.path.exists("icon.ico") else None

a = Analysis(
    ["lego_orders_app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "webview"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [("u", None, "OPTION")],  # unbuffered stdio: live progress in the web page
    exclude_binaries=True,
    name="LEGO Order Scraper",
    console=True,  # the console window shows progress; closing it quits the app
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.datas, name="LEGO Order Scraper")
