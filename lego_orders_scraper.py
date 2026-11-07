#!/usr/bin/env python3
"""
lego_orders_scraper.py

Scrapes YOUR OWN LEGO.com order history (lego.com/en-us/member/orders) and
fetches item-level detail (product name, item number, quantity, price,
free-gift/backorder status, tracking number) for every order.

HOW LOGIN WORKS
---------------
There are two ways to authenticate. Neither one has this script ask you for
your LEGO username or password, and neither stores them.

Option A -- log in fresh (default):
    It opens a real, visible Chromium browser window (via Playwright) using
    a persistent profile folder saved next to this script
    (./lego_browser_profile/). The first time you run it:
        1. A browser window opens to LEGO.com.
        2. If you're not signed in, the script pauses and asks you to log in
           BY HAND in that window (this also lets you handle any CAPTCHA or
           2FA yourself).
        3. Once you're on "My Orders" with your order history visible, go
           back to the terminal and press Enter to let the script continue.
    Because the profile folder keeps your session cookies, later runs will
    already be signed in and won't need step 2 (until the session expires).

Option B -- reuse another Chrome instance's session (--cookie-source):
    If you're already signed in to LEGO.com in some other Chrome window /
    profile, point --cookie-source at that Chrome PROFILE folder and this
    script will read its lego.com cookies straight off disk (decrypting
    them the same way Chrome itself does) and inject them into its own
    Playwright browser, instead of logging in again. Typical profile paths:
        macOS:   ~/Library/Application Support/Google/Chrome/Default
        Linux:   ~/.config/google-chrome/Default
        Windows: %LOCALAPPDATA%/Google/Chrome/User Data/Default
    That other Chrome instance can stay open -- the Cookies database is
    copied before reading, so an active lock doesn't block this. Treat the
    cookies this reads the same way you'd treat a password: they grant
    access to your LEGO account, so don't paste script output containing
    them anywhere, and this script never prints cookie values, only counts.

SETUP
-----
    pip install playwright cryptography
    playwright install chromium
    # Windows only, and only needed for --cookie-source:
    pip install pywin32

USAGE
-----
    python lego_orders_scraper.py                    # scrape everything, log in fresh
    python lego_orders_scraper.py --headless          # once already logged in
    python lego_orders_scraper.py --max-orders 5      # only 5 most recent orders
    python lego_orders_scraper.py --output my.json --csv my.csv
    python lego_orders_scraper.py --delay 2.5         # slower / more polite between order-detail pages
    python lego_orders_scraper.py --load-more-delay 3 # slower / more polite between "Load More" clicks
    python lego_orders_scraper.py --load-more-final-wait 10
                                                       # wait longer before assuming Load More is really gone
    python lego_orders_scraper.py --cookie-source "~/Library/Application Support/Google/Chrome/Default"
                                                       # reuse another Chrome's session
    python lego_orders_scraper.py --fresh             # ignore any saved progress, refetch all
    python lego_orders_scraper.py --since-date 01/31/2026
                                                       # only fetch item detail for orders placed
                                                       # on or after that date (format MM/DD/YYYY)
                                                       # (DEFAULT is 02/01/2024 if not given)
    python lego_orders_scraper.py --since-date all   # no cutoff: every order in your history
    python lego_orders_scraper.py --html report.html  # HTML report to a different file
                                                       # (default: lego_orders.html)
    python lego_orders_scraper.py --no-html           # skip the HTML report

HTML REPORT
-----------
Every run also writes a single self-contained HTML file (no external
CSS/JS -- just open it in a browser) listing every order and its full
line-item detail, built from this same run's results: lego_orders.html by
default, --html PATH for another file, --no-html to skip it. To build that
same report later from an existing --output JSON file WITHOUT fetching
anything from LEGO.com again, use the separate script instead:
    python lego_orders_to_html.py                     # reads lego_orders.json, writes lego_orders.html
    python lego_orders_to_html.py --json my.json --html my.html

OUTPUT & RESUMING
-----------------
Files are saved in the data folder: on a Mac ~/Library/Application Support/
LEGO Order Scraper/ (the same folder the Mac apps use), or LEGO_WORK_DIR if
set; elsewhere the current folder. Relative --output/--csv/--html paths go
there too. Each run is also recorded in ~/Library/Logs/LEGO Order Scraper.log
on a Mac (LEGO_LOG_FILE to change it; blank = no log).

A JSON file (default lego_orders.json) — one object per order, each with a
nested "items" list — and a flat CSV (default lego_orders.csv) with one
row per item, handy for opening in Excel/Sheets. Each item has an "is_piece"
flag: true for an individual loose part from a Bricks and Pieces / Pick A
Brick order (identified by "SKU:" on the page), false for a normal set or
product (identified by "Item:"). Each item also has an "is_gift_card" flag:
true for a digital LEGO E-Gift Card (a "Digital Gifting" order, which has no
item number at all, so "item_number" is null for these), false otherwise.
Each item also has a "custom_id" field: for a custom/personalized item like
a Minifigure Factory build, this is the unique ID for that specific build
(separate from "item_number", which is the same for every Minifigure
Factory order); null for anything else.

Each item's price is a "prices" object with two keys: "product.regularPrice"
and "product.salePrice". If the item wasn't on sale, both keys hold the same
value. If it was, "product.regularPrice" is the original price and
"product.salePrice" is the discounted price actually paid. For a free gift
item (no price shown on the page at all), both are null. The flat CSV
mirrors this as two separate columns, "regular_price" and "sale_price".

Both files are rewritten after EVERY order, not just at the end, so if you
interrupt the script (Ctrl+C) or it dies partway through, whatever it already
fetched is safely on disk. Just re-run the exact same command afterward: it
reads its own previous --output file first and skips any order it already
has item detail for, only fetching what's still missing. Pass --fresh to
ignore that and refetch everything from scratch instead. A single order that
fails to load (timeout, etc.) is logged and skipped rather than stopping the
whole run -- it'll simply be retried the next time you run the script.

NOTE ON FRAGILITY
------------------
LEGO.com doesn't publish a supported API for order history, so this reads
the same page text a person would see and parses it with pattern matching.
If LEGO redesigns the order pages, the parsing functions (parse_order_list /
parse_order_detail) are the place to fix things -- each is a small, separate
function you can test on its own (see test snippets in the docstring of
parse_order_detail).

Please keep --delay reasonable and don't run this in a tight loop -- it's
hitting LEGO's normal website like a person clicking through it, just
automated.
"""

import argparse
import base64
import csv
import datetime
import html
import json
import math
import os
import platform
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

__version__ = "43"  # bump by 1 with every change to this script

# --since-date value used when the option isn't given on the command line
# (MM/DD/YYYY). Pass --since-date all to turn the cutoff off entirely.
DEFAULT_SINCE_DATE = "02/01/2024"

# The HTML report is written by default, to this file (--html PATH to change it,
# --no-html to skip it).
DEFAULT_HTML_PATH = "lego_orders.html"

# Default CSV file. Versions before v36 called it lego_order_items.csv; an old
# file of that name next to a not-yet-created lego_orders.csv is renamed (see
# _rename_old_csv) so it isn't left behind, stale, after the switch.
DEFAULT_CSV_PATH = "lego_orders.csv"
OLD_DEFAULT_CSV_NAME = "lego_order_items.csv"

APP_NAME = "LEGO Order Scraper"


def data_dir():
    """The folder output files go in (and relative --output/--csv/--html paths
    are resolved against). The same folder for every version on a given OS:
      - LEGO_WORK_DIR, if set (Docker sets it to /data; the apps set it too)
      - on macOS: ~/Library/Application Support/LEGO Order Scraper
      - on Windows: %LOCALAPPDATA%\\LEGO Order Scraper
      - anywhere else (Linux): the current folder"""
    env = os.environ.get("LEGO_WORK_DIR")
    if env:
        return Path(env).expanduser()
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if platform.system() == "Windows":
        return _windows_local_appdata() / APP_NAME
    return Path.cwd()


def _windows_local_appdata():
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def log_file_path():
    """Where each run's output is also recorded: LEGO_LOG_FILE if set (blank =
    no log file), else on macOS ~/Library/Logs/LEGO Order Scraper.log, on
    Windows %LOCALAPPDATA%\\LEGO Order Scraper\\LEGO Order Scraper.log (the same
    logs the apps use), else no log file."""
    env = os.environ.get("LEGO_LOG_FILE")
    if env is not None:
        return Path(env).expanduser() if env.strip() else None
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Logs" / f"{APP_NAME}.log"
    if platform.system() == "Windows":
        return _windows_local_appdata() / APP_NAME / f"{APP_NAME}.log"
    return None


def resolve_output_path(path, base=None):
    """An absolute path (or ~/...) is used as given; a relative one goes in
    `base` (the --output-dir folder), or data_dir() when there isn't one."""
    p = Path(path).expanduser()
    return p if p.is_absolute() else Path(base or data_dir()) / p


def choose_output_dir(value):
    """--output-dir: a folder path (relative = from the current folder), or
    "browse" to pick one in the system's folder dialog. None = data_dir()."""
    if value is None:
        return None
    if str(value).strip().lower() in ("browse", "choose"):
        from lego_folder_picker import choose_folder

        chosen = choose_folder(start=data_dir())
        if chosen is None:
            raise SystemExit("No folder chosen (or no folder dialog available here) -- nothing done.")
        return chosen
    return Path(value).expanduser().resolve()


class _Tee:
    """Writes to the terminal (or the web UI's pipe) and to the log file at once.
    Flushes on every write so prompts without a newline show up immediately."""

    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        self.stream.write(text)
        self.stream.flush()
        try:
            self.log.write(text)
            self.log.flush()
        except (OSError, ValueError):
            pass  # a log problem must never stop a scrape
        return len(text)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def _start_log():
    """Record everything this run prints in the log file too (appended, with a
    header line). Returns the log path, or None when there's no log file."""
    path = log_file_path()
    if path is None:
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        log = open(path, "a", encoding="utf-8")
    except OSError as e:
        print(f"(couldn't open the log file {path}: {e})")
        return None
    log.write(f"\n===== {datetime.datetime.now().isoformat(timespec='seconds')} "
              f"lego_orders_scraper.py v{__version__} =====\n")
    sys.stdout = _Tee(sys.stdout, log)
    sys.stderr = _Tee(sys.stderr, log)
    return path

BASE = "https://www.lego.com"
ORDERS_URL = f"{BASE}/en-us/member/orders"
ORDER_DETAIL_URL = f"{BASE}/en-us/member/orders/details/{{order_number}}"
# Where the saved browser login lives. Defaults to a folder next to this script;
# the macOS app (and Docker) set LEGO_PROFILE_DIR so it lands in a user-writable
# place instead of inside a read-only app bundle / disposable container.
PROFILE_DIR = Path(os.environ.get("LEGO_PROFILE_DIR") or Path(__file__).parent / "lego_browser_profile")


# ---------------------------------------------------------------------------
# Chrome cookie import (--cookie-source)
#
# Reads cookies straight out of another Chrome profile's SQLite "Cookies"
# database and decrypts them the same way Chrome itself would, so we can
# hand LEGO's site an already-authenticated session instead of logging in
# again. This only uses cookies that are already sitting on disk in a
# profile you point it at -- it never touches a password, and it's the same
# basic technique Chrome's own "you're signed in everywhere" sync relies on
# conceptually (though the mechanics here are local-disk-only).
# ---------------------------------------------------------------------------

def _find_cookie_db(profile_path):
    """Locate a Chrome profile's 'Cookies' SQLite file. Accepts either the
    profile folder itself (e.g. '.../User Data/Default') or the top-level
    'User Data' folder, in which case we assume the 'Default' profile."""
    profile_path = Path(profile_path).expanduser()
    candidates = [
        profile_path / "Cookies",                    # older Chrome
        profile_path / "Network" / "Cookies",         # Chrome 96+
        profile_path / "Default" / "Cookies",         # a "User Data" root was given
        profile_path / "Default" / "Network" / "Cookies",
    ]
    for c in candidates:
        if c.is_file():
            return c
    tried = "\n  ".join(str(c) for c in candidates)
    raise FileNotFoundError(
        f"Couldn't find a Chrome 'Cookies' file under {profile_path}.\n"
        f"Tried:\n  {tried}\n"
        "Point --cookie-source at the Chrome PROFILE folder itself "
        "(e.g. '.../User Data/Default'), not a random parent folder."
    )


def _find_local_state(profile_path):
    """Windows only: the AES key used to decrypt cookies is stored
    (DPAPI-wrapped) in 'Local State', one level up from the profile."""
    profile_path = Path(profile_path).expanduser()
    for c in (profile_path / "Local State", profile_path.parent / "Local State"):
        if c.is_file():
            return c
    raise FileNotFoundError(
        f"Couldn't find Chrome's 'Local State' file near {profile_path} "
        "(needed on Windows to decrypt cookies)."
    )


def _copy_locked_db(db_path):
    """Chrome keeps the Cookies file open while running, so copy it (and its
    -wal/-shm sidecars, if present) to a temp location before reading --
    this lets us read it even while that Chrome instance is still open."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="lego_cookie_"))
    tmp_db = tmp_dir / "Cookies.copy"
    shutil.copy2(db_path, tmp_db)
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.is_file():
            shutil.copy2(side, Path(str(tmp_db) + suffix))
    return tmp_db


def _cookie_columns(cur):
    """Chrome has renamed a couple of these columns over the years (e.g.
    'httponly' -> 'is_httponly'). Look at what's actually in this DB instead
    of hard-coding one version's schema."""
    cur.execute("PRAGMA table_info(cookies)")
    available = {row[1] for row in cur.fetchall()}

    def pick(*names):
        for n in names:
            if n in available:
                return n
        raise RuntimeError(
            f"None of {names} found in the cookies table. "
            f"Columns present: {sorted(available)}"
        )

    return {
        "host": pick("host_key"),
        "name": pick("name"),
        "value": pick("value"),
        "encrypted_value": pick("encrypted_value"),
        "path": pick("path"),
        "expires": pick("expires_utc", "expires"),
        "secure": pick("is_secure", "secure"),
        "httponly": pick("is_httponly", "httponly"),
        "samesite": pick("samesite", "same_site"),
    }


def _chrome_time_to_unix(chrome_time):
    """Chrome stores timestamps as microseconds since 1601-01-01 (Windows
    epoch). 0 / missing means 'no expiry' (session cookie)."""
    if not chrome_time:
        return -1
    WINDOWS_TO_UNIX_EPOCH_SECONDS = 11644473600
    return chrome_time / 1_000_000 - WINDOWS_TO_UNIX_EPOCH_SECONDS


def _require_cryptography():
    """--cookie-source needs the 'cryptography' package to decrypt Chrome's
    cookies. It's optional: some builds (the Windows on ARM app) leave it out
    because it isn't available there. Fail with a clear message instead."""
    try:
        import cryptography  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "--cookie-source needs the 'cryptography' package, which isn't "
            "available in this build (for example the Windows on ARM app). "
            "Log in to LEGO.com in the scraper's own browser window instead."
        ) from None


def _macos_derive_key():
    _require_cryptography()
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "Couldn't read the 'Chrome Safe Storage' item from macOS Keychain "
            "(you may need to click Allow on the Keychain access prompt)."
        ) from e
    chrome_password = proc.stdout.strip().encode("utf-8")
    return PBKDF2HMAC(
        algorithm=hashes.SHA1(), length=16, salt=b"saltysalt", iterations=1003
    ).derive(chrome_password)


def _linux_derive_key():
    _require_cryptography()
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    # Most desktop Chrome/Chromium builds fall back to this fixed password
    # ("peanuts") for v10 cookies when there's no functioning OS keyring
    # unlocked in the session. This covers the common case; if that other
    # Chrome instance has a real Secret Service / kwallet-backed key instead,
    # this won't decrypt its cookies and you'll see a per-cookie skip message.
    return PBKDF2HMAC(
        algorithm=hashes.SHA1(), length=16, salt=b"saltysalt", iterations=1
    ).derive(b"peanuts")


def _windows_derive_key(profile_path):
    try:
        import win32crypt
    except ImportError as e:
        raise RuntimeError(
            "Reading cookies from another Chrome profile on Windows needs "
            "pywin32 (pip install pywin32)."
        ) from e

    local_state_path = _find_local_state(profile_path)
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.load(f)
    encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    encrypted_key = encrypted_key[5:]  # strip the "DPAPI" prefix
    return win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]


def _pkcs7_unpad(data):
    """Strict PKCS7 unpad. Raises instead of silently returning garbage when
    the padding is invalid -- which is what happens if we decrypted with the
    wrong key, so this doubles as a 'did we actually get the right key?'
    check rather than quietly handing back corrupted cookie values."""
    if not data:
        raise ValueError("empty decrypted payload")
    pad_len = data[-1]
    if not (1 <= pad_len <= 16) or data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("invalid PKCS7 padding (likely decrypted with the wrong key)")
    return data[:-pad_len]


# Chrome ~127+ (mid-2024 onward) prepends a 32-byte integrity/versioning
# prefix to the plaintext before AES-CBC-encrypting a cookie value on
# macOS/Linux -- so after a correct decrypt + unpad you get
# b'<32 opaque bytes>' + b'<the actual cookie value>' instead of the value
# alone. Older cookies written before a user's Chrome updated may not have
# it. We can't tell in advance which shape a given row is, so try the plain
# decode first and only fall back to stripping the prefix if that fails.
_CHROME_127_PLUS_PREFIX_LEN = 32


def _decode_unpadded_cookie_bytes(data):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if len(data) > _CHROME_127_PLUS_PREFIX_LEN:
        try:
            return data[_CHROME_127_PLUS_PREFIX_LEN:].decode("utf-8")
        except UnicodeDecodeError:
            pass
    raise ValueError(
        "decrypted bytes aren't valid UTF-8 either directly or after "
        "stripping Chrome's 32-byte post-127 prefix -- likely the wrong key"
    )


def _decrypt_cookie_value(encrypted_value, key, system):
    if not encrypted_value:
        return ""
    prefix = encrypted_value[:3]
    if prefix in (b"v10", b"v11", b"v20"):
        _require_cryptography()

    if system == "Windows":
        if prefix in (b"v10", b"v20"):
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = encrypted_value[3:15]
            ciphertext_and_tag = encrypted_value[15:]
            plaintext = AESGCM(key).decrypt(nonce, ciphertext_and_tag, None)
            return _decode_unpadded_cookie_bytes(plaintext)
        import win32crypt  # old DPAPI-only cookies, no v10/v20 prefix

        plaintext = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1]
        return _decode_unpadded_cookie_bytes(plaintext)

    # macOS / Linux: AES-128-CBC, a fixed 16-space IV, PKCS7 padding.
    if prefix not in (b"v10", b"v11"):
        return ""  # not encrypted the way we know how to handle
    if system == "Linux" and prefix == b"v11":
        # "v11" means Chrome encrypted this with a real key from the OS
        # keyring (Secret Service / KWallet), not the no-keyring "peanuts"
        # fallback this script derives -- we don't have a way to fetch that
        # keyring secret here, so surface it clearly instead of guessing.
        raise RuntimeError(
            "encrypted with a Secret Service/KWallet-backed key ('v11'), "
            "which isn't supported -- only Linux Chrome profiles using the "
            "no-keyring fallback ('v10') can be read"
        )
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    cipher = Cipher(algorithms.AES(key), modes.CBC(b" " * 16))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted_value[3:]) + decryptor.finalize()
    decrypted = _pkcs7_unpad(decrypted)
    return _decode_unpadded_cookie_bytes(decrypted)


def load_chrome_cookies_for_domain(profile_path, domain_substring):
    """Return a list of cookies (already decrypted, in Playwright's
    add_cookies() format) for every cookie in the given Chrome profile whose
    host contains domain_substring."""
    _require_cryptography()
    db_path = _find_cookie_db(profile_path)
    tmp_db = _copy_locked_db(db_path)
    system = platform.system()  # 'Darwin' / 'Linux' / 'Windows'

    if system == "Darwin":
        key = _macos_derive_key()
    elif system == "Linux":
        key = _linux_derive_key()
    elif system == "Windows":
        key = _windows_derive_key(profile_path)
    else:
        raise RuntimeError(f"Unsupported OS for cookie decryption: {system}")

    conn = sqlite3.connect(str(tmp_db))
    try:
        cur = conn.cursor()
        col = _cookie_columns(cur)
        cur.execute(
            f"SELECT {col['host']}, {col['name']}, {col['value']}, "
            f"{col['encrypted_value']}, {col['path']}, {col['expires']}, "
            f"{col['secure']}, {col['httponly']}, {col['samesite']} "
            f"FROM cookies WHERE {col['host']} LIKE ?",
            (f"%{domain_substring}%",),
        )
        rows = cur.fetchall()
    finally:
        conn.close()
        shutil.rmtree(tmp_db.parent, ignore_errors=True)

    cookies = []
    for (host, name, value, encrypted_value, path, expires,
         secure, httponly, samesite) in rows:
        if not value and encrypted_value:
            try:
                value = _decrypt_cookie_value(encrypted_value, key, system)
            except Exception as e:
                print(f"  (skipping cookie '{name}' for {host}: {e})")
                continue
        if not value:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": host,
                "path": path or "/",
                "expires": _chrome_time_to_unix(expires),
                "httpOnly": bool(httponly),
                "secure": bool(secure),
                "sameSite": {0: "None", 1: "Lax", 2: "Strict"}.get(samesite, "Lax"),
            }
        )
    return cookies

# Order / shipment status words LEGO's order pages use. If LEGO adds a new
# one (e.g. "Delayed"), add it here so it's recognized as a status line
# instead of accidentally being treated as a product name.
STATUS_WORDS = {
    "Shipped", "Delivered", "Backordered", "In Warehouse",
    "Processing", "Cancelled", "Canceled", "Returned", "Refunded", "Pending",
    "Pre-order",  # items of an "In Process" order that hasn't shipped yet
}


def dismiss_interstitials(page):
    """Click through the cookie-consent banner and the occasional
    'You are about to enter LEGO.com' splash screen, if either shows up.
    Safe to call anywhere -- does nothing if neither is present."""
    for role, name in [("button", "Continue"), ("button", "Reject All")]:
        try:
            loc = page.get_by_role(role, name=name)
            if loc.count():
                loc.first.click(timeout=2000)
                page.wait_for_timeout(300)
        except Exception:
            pass


def wait_for_login(page):
    """Make sure we're actually signed in before scraping anything."""
    print("\nOpening LEGO.com...")
    page.goto(ORDERS_URL, wait_until="domcontentloaded")
    dismiss_interstitials(page)

    if _signed_out(page):
        print(
            "You don't look signed in yet.\n"
            "  1) In the browser window that just opened, log in to your LEGO account.\n"
            "  2) Once you can see 'My Orders' with your order history, come back here.\n"
        )
        input("Press Enter once you're signed in and on the My Orders page... ")
        page.goto(ORDERS_URL, wait_until="domcontentloaded")
        dismiss_interstitials(page)


def _current_order_numbers(text):
    """Pull every 'Order Number: Txxxxx' out of already-fetched page text, in
    the order it appears on the page."""
    return re.findall(r"Order Number:\s*(T\d+)", text)


def load_all_orders_text(
    page, max_orders=None, load_more_delay=1.2, load_more_final_wait=5.0,
    since_date=None,
):
    """Repeatedly click 'Load More' until every order is on the page (or
    we've already got at least max_orders, or -- when since_date is given --
    the oldest order loaded so far is already before since_date), then
    return the order list's visible text.

    LEGO lists orders newest-first, so once the oldest order currently on
    the page is confidently before since_date, every order a further 'Load
    More' click would reveal is guaranteed to be even older -- there's no
    point paying for more clicks/page renders just to load orders whose item
    detail --since-date would skip fetching anyway. This checks that after
    every new batch (the initial one and each 'Load More' click) using the
    same _before_since_date() logic the main fetch loop uses, so the two
    stay consistent with each other.
    """
    # The order list itself is fetched client-side *after* the page shell
    # loads (it's not there in the initial HTML), so give it a moment to
    # actually appear before we start counting/clicking anything -- reading
    # too early looks exactly like "this account has 0 orders".
    try:
        page.get_by_role(
            "link", name=re.compile(r"^Order Number: T\d+$")
        ).first.wait_for(state="visible", timeout=15000)
    except PWTimeoutError:
        print(
            "  (no order rows appeared within 15s -- either this account "
            "genuinely has none, or the page didn't finish loading; "
            "continuing with whatever's currently on the page)"
        )

    # Running tally of every distinct order number seen so far, printed as
    # each new batch renders so you can watch progress during a long
    # "Load More" run instead of staring at a silent terminal.
    seen = []
    seen_set = set()
    stop_for_since_date = False

    def _report_new_orders():
        nonlocal stop_for_since_date
        text = page.locator("main").inner_text()
        for num in _current_order_numbers(text):
            if num not in seen_set:
                seen_set.add(num)
                seen.append(num)
                print(f"  [{len(seen)}] {num}")

        if since_date is not None and not stop_for_since_date:
            # The last order parse_order_list() finds is the last one that
            # appears on the page -- i.e. the oldest of everything loaded so
            # far, since new batches render below the existing ones.
            current_orders = parse_order_list(text)
            if current_orders and _before_since_date(current_orders[-1], since_date):
                stop_for_since_date = True
                print(
                    f"  (reached an order placed {current_orders[-1].order_date}, "
                    "which is before --since-date -- stopping 'Load More' "
                    "here instead of loading older orders we won't fetch "
                    "item detail for anyway)"
                )

    _report_new_orders()

    while True:
        if _interrupt.count > 0:
            break  # Ctrl+C -- stop paginating, use whatever's loaded so far
        if stop_for_since_date:
            break
        load_more = page.get_by_role("button", name="Load More")
        if load_more.count() == 0:
            # The button doesn't always reappear immediately after a click
            # -- LEGO's site can take a while to render the next batch.
            # Rather than concluding "no more orders" the instant it's
            # missing, give it one more, longer chance to show up before
            # actually giving up and moving on to fetching item detail.
            print(
                f"  (Load More isn't visible -- waiting up to "
                f"{load_more_final_wait:g}s in case it's just slow to "
                "reappear before assuming we're done...)"
            )
            try:
                load_more.first.wait_for(
                    state="visible", timeout=int(load_more_final_wait * 1000)
                )
            except PWTimeoutError:
                break  # really done, nothing more loaded in time
            _report_new_orders()  # it showed up after all -- see if a batch snuck in too
            continue  # loop back around and click it
        if max_orders:
            loaded = page.get_by_role(
                "link", name=re.compile(r"^Order Number: T\d+$")
            ).count()
            if loaded >= max_orders:
                break
        try:
            load_more.first.click()
            page.wait_for_timeout(int(load_more_delay * 1000))  # let the next page of orders render
            _report_new_orders()
        except PWTimeoutError:
            break

    return page.locator("main").inner_text()


# ---------------------------------------------------------------------------
# Data model
#
# One LegoOrder per order, holding a list of LegoOrderLine (one per item/
# piece/gift card on that order) plus the order-summary totals. These are
# what parse_order_list() / parse_order_detail() / _parse_order_summary()
# build, and what the rest of this script (merge/dedupe/resume/write) reads
# and updates -- real objects with named attributes (order.order_number,
# item.name, ...) instead of plain dicts with string keys.
#
# JSON on disk stays exactly the same shape it always was: to_dict() /
# from_dict() are the only places that translate between an object and the
# plain-dict form json.dump()/json.load() actually work with, so existing
# lego_orders.json files from earlier versions of this script still load
# fine, and anything else that reads the JSON output doesn't need to change.
# ---------------------------------------------------------------------------


@dataclass
class LegoOrderLine:
    """One line item within an order: a set/product, an individual loose
    Pick A Brick piece, a digital gift card, or a custom build like a
    Minifigure Factory. This is the object form of what parse_order_detail()
    used to hand back as a plain dict -- see its docstring for exactly what
    each field means and the page shapes each one comes from."""

    name: str
    item_number: Optional[str]
    custom_id: Optional[str]
    quantity: Optional[int]
    prices: Dict[str, Optional[str]]
    is_free_gift: bool
    is_piece: bool
    is_gift_card: bool
    status: Optional[str]
    tracking_number: Optional[str]

    def to_dict(self):
        return {
            "name": self.name,
            "item_number": self.item_number,
            "custom_id": self.custom_id,
            "quantity": self.quantity,
            "prices": dict(self.prices),
            "is_free_gift": self.is_free_gift,
            "is_piece": self.is_piece,
            "is_gift_card": self.is_gift_card,
            "status": self.status,
            "tracking_number": self.tracking_number,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            name=d["name"],
            item_number=d.get("item_number"),
            custom_id=d.get("custom_id"),
            quantity=d.get("quantity"),
            prices=dict(
                d.get("prices")
                or {"product.regularPrice": None, "product.salePrice": None}
            ),
            is_free_gift=bool(d.get("is_free_gift", False)),
            is_piece=bool(d.get("is_piece", False)),
            is_gift_card=bool(d.get("is_gift_card", False)),
            status=d.get("status"),
            tracking_number=d.get("tracking_number"),
        )


@dataclass
class LegoOrder:
    """One order from the My Orders list, plus everything fetched from its
    detail page. `items` and `summary` start out empty (a freshly-listed
    order that hasn't had its detail page fetched yet) and get filled in by
    scrape() once that happens."""

    order_number: str
    status: Optional[str]
    order_date: Optional[str]
    total: Optional[str]
    item_count_listed: Optional[int]
    url: str
    items: List[LegoOrderLine] = field(default_factory=list)
    summary: Dict[str, str] = field(default_factory=dict)
    fetch_error: Optional[str] = None
    # Not saved to disk. Set by merge_with_existing() when a saved order's
    # status changed since it was fetched (e.g. "In Process" -> "Shipped"), so
    # scrape() re-reads its detail page to pick up new item statuses/tracking.
    refresh: bool = field(default=False, compare=False, repr=False)

    def to_dict(self):
        d = {
            "order_number": self.order_number,
            "status": self.status,
            "order_date": self.order_date,
            "total": self.total,
            "item_count_listed": self.item_count_listed,
            "url": self.url,
            "items": [item.to_dict() for item in self.items],
            "summary": dict(self.summary),
        }
        if self.fetch_error is not None:
            d["fetch_error"] = self.fetch_error
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(
            order_number=d["order_number"],
            status=d.get("status"),
            order_date=d.get("order_date"),
            total=d.get("total"),
            item_count_listed=d.get("item_count_listed"),
            url=d.get("url"),
            items=[LegoOrderLine.from_dict(it) for it in (d.get("items") or [])],
            summary=dict(d.get("summary") or {}),
            fetch_error=d.get("fetch_error"),
        )


def parse_order_list(text, max_orders=None):
    """Turn the My Orders page text into a list of LegoOrder objects (with
    "items" and "summary" both still empty -- that's filled in later, once
    each order's detail page is fetched).

    Expects blocks that look like:
        Backordered
        Order Number: T514535382
        Order Date: September 7, 2026
        Total: $369.95
        6 items in this order
    (extra lines like a "+2" thumbnail overflow marker are ignored.)
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    orders = []
    for i, line in enumerate(lines):
        m = re.match(r"^Order Number:\s*(T\d+)$", line)
        if not m:
            continue
        order_number = m.group(1)
        status = lines[i - 1] if i > 0 else None
        order_date = total = None
        item_count = None
        for j in range(i + 1, min(i + 8, len(lines))):
            if re.match(r"^Order Number:\s*T\d+$", lines[j]):
                # Reached the NEXT order's block (this order's own item-count
                # line was missing or worded differently). Stop here: reading
                # on would hand this order the next order's date/total.
                break
            dm = re.match(r"^Order Date:\s*(.+)$", lines[j])
            tm = re.match(r"^Total:\s*\$([\d,.]+)$", lines[j])
            im = re.match(r"^(\d+)\s+items?\s+in this order$", lines[j])
            if dm:
                if order_date is None:  # first one wins, never overwritten
                    order_date = dm.group(1)
            elif tm:
                if total is None:
                    total = tm.group(1)
            elif im:
                item_count = int(im.group(1))
                break  # item-count line is always the last one we need
        orders.append(
            LegoOrder(
                order_number=order_number,
                status=status,
                order_date=order_date,
                total=total,
                item_count_listed=item_count,
                url=ORDER_DETAIL_URL.format(order_number=order_number),
            )
        )
        if max_orders and len(orders) >= max_orders:
            break
    return orders


def _clean_item_name(name):
    """Strip non-ASCII characters out of an item name as parsed off the
    page -- e.g. "Technic™ Hub" becomes "Technic Hub", "NINJAGO®
    City Workshops" becomes "NINJAGO City Workshops". Characters (TM/(R)
    symbols, smart quotes, accented letters, etc.) are deleted, not
    replaced, matching the same "delete, don't substitute" behavior as
    strip_non_ascii.py's whole-file cleaner. Only the item's own name is
    touched here -- item numbers, prices, tracking numbers, dates, and
    every other field are left exactly as parsed."""
    return "".join(ch for ch in name if ord(ch) <= 127)


def _build_prices_dict(raw_prices):
    """Turn the raw list of dollar amounts collected off an item's Price
    block (in the order they appear on the page -- the original price
    first, then the discounted price if there was a sale) into the
    {"product.regularPrice", "product.salePrice"} shape used in the
    output.

    - No price at all (a free gift, "Price / -"): both keys are None.
    - One price (not on sale): both keys hold that same value.
    - Two prices (on sale, either the "product.salePrice" or the "LEGO
      Insiders Price" style): the first is the regular price, the second
      is the sale price -- regardless of which label appeared on the page,
      since both mean "you paid the second, lower amount instead of the
      first."
    """
    if not raw_prices:
        return {"product.regularPrice": None, "product.salePrice": None}
    return {"product.regularPrice": raw_prices[0], "product.salePrice": raw_prices[-1]}


_SUMMARY_LABELS = {
    "Subtotal": "subtotal",
    "Delivery": "delivery",
    "Shipping": "delivery",  # alternate label seen for the same line
    "Tax": "tax",
    # Kept as its own key, separate from the generic "Discount" below --
    # a coupon/promo discount and a LEGO Insiders discount are reported as
    # separate line items and can both appear on the same order.
    "LEGO® Insiders discount": "insiders_discount",
    "Discount": "discount",
    "Total": "total",
}
_SUMMARY_AMOUNT_RE = r"(-?\$[\d,]+\.\d{2})"


def _parse_order_summary(text):
    """Parse the "Order summary" block on an order-detail page (Subtotal /
    Delivery / Tax / LEGO® Insiders discount / Discount / Total) into a
    flat dict of dollar-amount strings (e.g. {"subtotal": "754.96",
    "delivery": "0.00", "tax": "54.08", "insiders_discount": "-9.00",
    "total": "800.04"}).

    This block lives in the same `main.inner_text()` text already read for
    parse_order_detail() -- no extra click/page needed to reveal it.

    Tolerant of both layouts actually seen on real pages: label and amount
    on the same line ("Subtotal $754.96"), or on two separate lines
    ("Subtotal" / "$754.96").

    Not every order shows every line -- a "Discount" or "LEGO® Insiders
    discount" line, for instance, only appears when that kind of discount
    was actually applied to that order, and the two are tracked under
    separate keys ("discount" / "insiders_discount") since an order could
    in principle show both. Some orders may not show this block at all.
    Any field not found is simply left out of the returned dict (never
    fabricated as "0.00" or None) -- callers should use .get() rather than
    assume every key is always present.
    """
    if "Order summary" not in text:
        return {}

    tail = text[text.index("Order summary") + len("Order summary"):]
    lines = [l.strip() for l in tail.split("\n") if l.strip()]

    result = {}
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        matched_key = None
        for label, key in _SUMMARY_LABELS.items():
            if key in result:
                continue  # already found (e.g. via "Delivery" before "Shipping")
            if re.match(rf"^{re.escape(label)}\b", line):
                matched_key = key
                break
        if matched_key is None:
            i += 1
            continue

        m = re.search(_SUMMARY_AMOUNT_RE, line)
        if m:
            result[matched_key] = m.group(1).replace("$", "")
            i += 1
            continue
        if i + 1 < n:
            m2 = re.search(_SUMMARY_AMOUNT_RE, lines[i + 1])
            if m2:
                result[matched_key] = m2.group(1).replace("$", "")
                i += 2
                continue
        i += 1  # label with no amount found nearby -- skip it, don't fabricate

    return result


_PRICE_TOKEN_RE = re.compile(r"Price|product\.salePrice|LEGO® Insiders Price|\$[\d,.]+|-")
_PRICE_LABELS = {"Price", "product.salePrice", "LEGO® Insiders Price"}


def _split_glued_price_line(line):
    """Split a price line whose parts got run together back into separate lines.

    LEGO's "Price" label is a visually-hidden element. Chromium's page text puts
    it on its own line ("Price" / "$119.99"), but Safari/WebKit (used by the
    native Mac app) runs it into the amount: "Price$119.99", "Price-" (free
    gift), "product.salePrice$4.99". A line made up entirely of 2+ price pieces
    (a label, "$X.XX" amounts, "-"), at least one of them a label, is split into
    those pieces; any other line comes back unchanged.
    """
    tokens = []
    pos = 0
    while pos < len(line):
        m = _PRICE_TOKEN_RE.match(line, pos)
        if not m:
            return [line]
        tokens.append(m.group())
        pos = m.end()
        while pos < len(line) and line[pos].isspace():
            pos += 1
    if len(tokens) >= 2 and any(t in _PRICE_LABELS for t in tokens):
        return tokens
    return [line]


def parse_order_detail(text):
    """Parse an order-details page's text into a flat list of LegoOrderLine
    objects.

    Handles the shapes seen on real order pages:
      - normal item:       Name / Item: NNN / Quantity: N / Price / $X.XX
      - free gift item:    ... / Price / -
      - on-sale item:      ... / Price / $22.99 / product.salePrice / $16.09
      - Insiders-price:    ... / Price / $69.99 / $48.99 / LEGO(R) Insiders Price
      - multiple shipments per order, each with its own "Shipped" /
        "Tracking number: ..." header that applies to the items after it
      - a per-item status line (e.g. "Backordered") right before that item
      - a "Bricks and Pieces" (Pick A Brick) section: a container item with
        "Item: NNN" but NO "Quantity:" line (Name / Item: NNN / Price /
        $X.XX), followed by its individual loose pieces, each identified by
        "SKU: NNN" instead of "Item: NNN" (Name / SKU: NNN / Quantity: N /
        Price / $X.XX)
      - a "Digital Gifting" section: an e-gift card, which has no
        "Item: NNN" / "SKU: NNN" line at all -- just Name / Quantity: N /
        Price / $X.XX directly. Flagged with "is_gift_card": True and
        "item_number": None since it has no item number to report.
      - a custom/personalized item (e.g. Minifigure Factory): an extra
        "ID: XXXX" line right after "Item: NNN" -- a unique identifier for
        that specific custom build, on top of the shared item number
        (every Minifigure Factory order has the same "Item: 3850083", so
        the ID is what distinguishes one custom build from another).
        Captured as "custom_id" (None for anything else).

    Each item's price is reported as a "prices" dict with two keys,
    "product.regularPrice" and "product.salePrice" -- see
    _build_prices_dict() for exactly how those are derived.

    Every item's "name" has non-ASCII characters stripped out (TM/(R)
    symbols, etc.) -- see _clean_item_name() for exactly how.
    """
    lines = [
        part
        for l in text.split("\n") if l.strip()
        for part in _split_glued_price_line(l.strip())
    ]
    items = []
    current_status = None
    current_tracking = None

    i, n = 0, len(lines)
    while i < n:
        line = lines[i]

        tm = re.match(r"^Tracking number:\s*(\S+)$", line)
        if tm:
            current_tracking = tm.group(1)
            i += 1
            continue

        if line in STATUS_WORDS:
            current_status = line
            i += 1
            continue

        if line.lower() == "digital gifting":
            # E-gift cards are emailed, not shipped: the shipment status and
            # tracking number of the section above don't apply to them.
            current_status = None
            current_tracking = None
            i += 1
            continue

        # Item block: Name, then either "Item: NNN" (a set/product, or the
        # Pick A Brick container) or "SKU: NNN" (an individual loose piece).
        number_line = lines[i + 1] if i + 1 < n else ""
        number_match = re.match(r"^(Item|SKU):\s*(.+)$", number_line)
        if number_match:
            name = _clean_item_name(line)
            is_piece = number_match.group(1) == "SKU"
            item_number = number_match.group(2).strip()
            i += 2

            # A custom/personalized item (e.g. Minifigure Factory) has an
            # extra "ID: XXXX" line right after "Item: NNN" -- consume it
            # if present so it doesn't get mistaken for a separate item
            # (it would otherwise fall through and get misread as, say, a
            # bare-Quantity "gift card" using whatever price comes next).
            custom_id = None
            if i < n:
                id_match = re.match(r"^ID:\s*(.+)$", lines[i])
                if id_match:
                    custom_id = id_match.group(1).strip()
                    i += 1

            # "Quantity:" is present for normal items and individual pieces,
            # but NOT for the Pick A Brick container item itself -- so only
            # consume it if it's actually there.
            quantity = None
            if i < n and lines[i].startswith("Quantity:"):
                qty_match = re.search(r"\d+", lines[i])
                quantity = int(qty_match.group()) if qty_match else None
                i += 1

            if i < n and lines[i] == "Price":
                i += 1

            raw_prices = []
            while i < n:
                nxt = lines[i]
                if nxt == "-":
                    i += 1
                    continue
                if re.match(r"^\$[\d,.]+$", nxt):
                    raw_prices.append(nxt.lstrip("$"))
                    i += 1
                    continue
                if nxt in ("product.salePrice", "LEGO® Insiders Price"):
                    i += 1
                    continue
                break

            items.append(
                LegoOrderLine(
                    name=name,
                    item_number=item_number,
                    custom_id=custom_id,
                    quantity=quantity,
                    prices=_build_prices_dict(raw_prices),
                    is_free_gift=len(raw_prices) == 0,
                    is_piece=is_piece,
                    is_gift_card=False,
                    status=current_status,
                    tracking_number=current_tracking,
                )
            )
            continue

        # Digital gift card: Name, then straight into "Quantity: N" with no
        # "Item:"/"SKU:" line at all (there's no item number to report).
        qty_only_match = re.match(r"^Quantity:\s*(\d+)$", number_line)
        if qty_only_match:
            name = _clean_item_name(line)
            quantity = int(qty_only_match.group(1))
            i += 2

            if i < n and lines[i] == "Price":
                i += 1

            raw_prices = []
            while i < n:
                nxt = lines[i]
                if nxt == "-":
                    i += 1
                    continue
                if re.match(r"^\$[\d,.]+$", nxt):
                    raw_prices.append(nxt.lstrip("$"))
                    i += 1
                    continue
                if nxt in ("product.salePrice", "LEGO® Insiders Price"):
                    i += 1
                    continue
                break

            items.append(
                LegoOrderLine(
                    name=name,
                    item_number=None,
                    custom_id=None,
                    quantity=quantity,
                    prices=_build_prices_dict(raw_prices),
                    is_free_gift=len(raw_prices) == 0,
                    is_piece=False,
                    is_gift_card=True,
                    status=current_status,
                    tracking_number=current_tracking,
                )
            )
            continue

        i += 1

    return items


def _signed_out(page):
    return (page.title() or "").strip() == "Sign In" or page.get_by_role(
        "link", name="Sign In"
    ).count() > 0


def _atomic_write(path, write_fn):
    """Write to a temp file, then rename it into place. Rename is atomic on
    both POSIX and Windows, so if you Ctrl+C mid-write the real output file
    is either the old complete version or the new complete version -- never
    a half-written, corrupted one."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        write_fn(tmp)
        tmp.replace(path)
    except BaseException:
        # BaseException (not just Exception) so a Ctrl+C mid-write also
        # cleans up -- KeyboardInterrupt doesn't subclass Exception.
        tmp.unlink(missing_ok=True)
        raise


def load_existing_orders(json_path):
    """Load a previous run's output (if any) so we can skip re-fetching item
    detail for orders we already have, and never lose orders from an earlier
    run that this run's order-list scan doesn't happen to include (e.g. a
    smaller --max-orders this time). Returns LegoOrder objects, built from
    the plain-dict JSON on disk via LegoOrder.from_dict()."""
    path = Path(json_path)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        orders = [LegoOrder.from_dict(o) for o in data]
        return {o.order_number: o for o in orders if o.items}
    except Exception as e:
        print(f"  (couldn't read existing {json_path}, starting fresh: {e})")
        return {}


def _reconcile_total(order):
    """The order's own detail page is the authoritative source for its
    total: its "Order summary" block belongs to exactly that order, whereas
    the total scraped off the order LIST page can be wrong (e.g. picked up
    from a neighboring order's block). If the detail page gave a Total, use
    it. Returns True if that changed the order's total."""
    detail_total = (order.summary or {}).get("total")
    if detail_total and detail_total != order.total:
        print(
            f"  note: {order.order_number}: list-page total "
            f"{order.total!r} corrected to {detail_total!r} (from its own "
            "order-detail page)"
        )
        order.total = detail_total
        return True
    return False


def merge_with_existing(fresh_orders, existing_by_number):
    """Combine this run's freshly-scraped order list with whatever was
    already saved from a previous run.

    - An order present in both: keep its previously-fetched items, but
      refresh the list-level fields (status/date/total can change, e.g.
      Backordered -> Shipped).
    - An order only in `fresh_orders` (new since last time, or first run):
      kept as-is, items still empty, to be fetched.
    - An order only in `existing_by_number` (this run's scan didn't include
      it -- e.g. a smaller --max-orders this time): kept at the end rather
      than silently dropped from the output.

    Order of the result: fresh_orders' order first, then any leftovers.
    """
    merged = dict(existing_by_number)
    for order in fresh_orders:
        num = order.order_number
        if num in merged:
            existing_order = merged[num]
            # A saved order whose status changed since it was fetched (or whose
            # last refresh didn't finish) gets its detail page read again --
            # e.g. "Pre-order" items that have since shipped.
            if existing_order.items and order.status != existing_order.status:
                print(
                    f"  note: {num}: status changed from {existing_order.status!r} "
                    f"to {order.status!r} -- refetching its item detail"
                )
                existing_order.refresh = True
            elif existing_order.items and existing_order.fetch_error:
                print(f"  note: {num}: last refresh didn't finish -- refetching its item detail")
                existing_order.refresh = True
            existing_order.status = order.status
            existing_order.order_date = order.order_date
            existing_order.total = order.total
            existing_order.item_count_listed = order.item_count_listed
            _reconcile_total(existing_order)  # detail page beats the list page
        else:
            merged[num] = order
    seen_order = [o.order_number for o in fresh_orders]
    leftover_order = [n for n in existing_by_number if n not in seen_order]
    return [merged[n] for n in seen_order + leftover_order]


def dedupe_orders(orders):
    """Collapse any order_number that appears more than once in `orders`
    down to a single entry.

    LEGO's order-list page occasionally renders the same order twice while
    paginating through "Load More" (the same order block shows up again in
    a later batch), and parse_order_list has no way to tell that apart from
    a genuinely new order -- it just records every "Order Number: Txxx" it
    sees. Left alone, that produces two SEPARATE LegoOrder objects for the
    same order_number sitting at different positions in `orders`. Whichever one
    gets its item detail fetched first only updates ITS OWN object -- the
    other, still-empty copy stays in the list too, and depending on which
    one a downstream consumer looks at, you can end up with the item detail
    showing up in one output but not the other -- e.g. present in the CSV
    (written per-item, so it only shows rows for whichever copy has items)
    but the copy actually serialized to JSON is the empty duplicate.

    Keeps the copy that actually has item detail when there's a choice;
    otherwise keeps the first occurrence. Order-preserving.
    """
    by_number = {}
    order_of_numbers = []
    for order in orders:
        num = order.order_number
        if num not in by_number:
            by_number[num] = order
            order_of_numbers.append(num)
            continue
        existing = by_number[num]
        if not existing.items and order.items:
            print(
                f"  (note: {num} appeared more than once in the order list "
                "-- keeping the copy that has item detail)"
            )
            by_number[num] = order
    return [by_number[num] for num in order_of_numbers]


def _parse_cli_date(value):
    """argparse 'type=' converter for --since-date: expects MM/DD/YYYY, or
    "all" / "none" to turn the cutoff off (returns None = no cutoff)."""
    if str(value).strip().lower() in ("all", "none", ""):
        return None
    try:
        return datetime.datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r} -- expected MM/DD/YYYY, e.g. 01/31/2026 (or 'all')"
        )


def _parse_order_date(date_str):
    """Parse an order's 'order_date' field (e.g. 'September 7, 2026', the
    format LEGO's site renders) into a date object, for --since-date
    comparisons. Returns None if it can't be parsed, so callers treat an
    unparseable date as "fetch it anyway" rather than silently skipping an
    order we can't actually judge."""
    if not date_str:
        return None
    try:
        return datetime.datetime.strptime(date_str, "%B %d, %Y").date()
    except ValueError:
        return None


def _before_since_date(order, since_date):
    """True only when this order's order_date is confidently parseable AND
    earlier than since_date. Used to skip FETCHING item detail for orders
    older than --since-date (the order itself still shows up in the
    output, just without newly-fetched item detail)."""
    if since_date is None:
        return False
    order_date_obj = _parse_order_date(order.order_date)
    return order_date_obj is not None and order_date_obj < since_date


class _GracefulInterrupt:
    """Ctrl+C handling that's actually responsive, even though closing a
    Playwright browser (especially a persistent profile, which has to flush
    its whole profile to disk) can silently take several seconds.

    1st Ctrl+C: prints an acknowledgment IMMEDIATELY (this runs the instant
    the signal arrives, regardless of what Playwright call is in flight),
    and sets a flag the fetch loop checks between orders so it stops at the
    next safe point rather than mid-request.
    2nd Ctrl+C: gives up on a graceful shutdown entirely and exits the
    process immediately (os._exit bypasses any further Python cleanup, so
    it can't hang no matter where things are stuck).

    Since progress is already saved after every order, neither path loses
    data -- this only affects how quickly the terminal gets back to you.
    """

    def __init__(self):
        self.count = 0

    def __call__(self, signum, frame):
        self.count += 1
        if self.count == 1:
            print(
                "\nCtrl+C received -- finishing the current step, saving, "
                "and shutting down the browser (this can take a few "
                "seconds). Press Ctrl+C again to quit immediately instead."
            )
        else:
            print("\nSecond Ctrl+C -- exiting immediately without waiting for cleanup.")
            os._exit(1)


_interrupt = _GracefulInterrupt()


def _install_interrupt_handler():
    """Ctrl+C (SIGINT) -- and on Windows also Ctrl+Break (SIGBREAK), which is
    what the web UI's Stop button sends there -- go to _interrupt, so the first
    one stops gracefully (finish the current step, save) instead of killing
    the process on the spot."""
    signal.signal(signal.SIGINT, _interrupt)
    if hasattr(signal, "SIGBREAK"):  # Windows only
        signal.signal(signal.SIGBREAK, _interrupt)


def scrape(
    max_orders=None,
    headless=False,
    delay=1.5,
    load_more_delay=1.2,
    load_more_final_wait=5.0,
    cookie_source=None,
    json_path="lego_orders.json",
    csv_path=DEFAULT_CSV_PATH,
    fresh=False,
    since_date=None,
    include_tracking=True,
):
    _install_interrupt_handler()
    _interrupt.count = 0  # reset in case scrape() is called more than once in this process
    _rename_old_csv(csv_path)
    existing_by_number = {} if fresh else load_existing_orders(json_path)
    if existing_by_number:
        print(
            f"Resuming: {len(existing_by_number)} order(s) already have item "
            f"detail saved in {json_path} -- skipping those (use --fresh to "
            "refetch everything)."
        )

    with sync_playwright() as p:
        # Playwright's sync API starts its own driver subprocess/event loop
        # on entry, and that setup can silently reset Python's SIGINT
        # handler back to the default (which raises a raw KeyboardInterrupt
        # and prints a traceback) -- re-assert ours now that Playwright has
        # finished starting up, so a Ctrl+C anywhere from here on is still
        # handled gracefully instead of reverting to the default behavior.
        _install_interrupt_handler()

        browser = None  # only set (and closed) in the --cookie-source path

        if cookie_source:
            print(f"Reading lego.com cookies from {cookie_source} ...")
            cookies = load_chrome_cookies_for_domain(cookie_source, "lego.com")
            if not cookies:
                raise SystemExit(
                    "No lego.com cookies found in that profile. Make sure the "
                    "other Chrome instance is actually signed in to LEGO.com, "
                    "and that --cookie-source points at its profile folder "
                    "(the one containing a 'Cookies' file), not a random path."
                )
            print(f"  found {len(cookies)} cookie(s), importing into a new browser session")
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(viewport={"width": 1200, "height": 900})
            context.add_cookies(cookies)
            page = context.new_page()
            page.goto(ORDERS_URL, wait_until="domcontentloaded")
            dismiss_interstitials(page)
            if _signed_out(page):
                context.close()
                browser.close()
                raise SystemExit(
                    "Imported the cookies but LEGO.com still shows signed out. "
                    "Either that session has expired, or the auth cookie in that "
                    "profile lives under a domain this script isn't matching -- "
                    "sign in again in that Chrome instance and try once more."
                )
        else:
            PROFILE_DIR.mkdir(exist_ok=True)
            context = p.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                headless=headless,
                viewport={"width": 1200, "height": 900},
            )
            page = context.new_page()
            wait_for_login(page)

        orders = []  # so the except/finally blocks below always have something to report
        try:
            print("Loading order history (this may click 'Load More' a few times)...")
            list_text = load_all_orders_text(
                page,
                max_orders=max_orders,
                load_more_delay=load_more_delay,
                load_more_final_wait=load_more_final_wait,
                since_date=since_date,
            )
            orders = parse_order_list(list_text, max_orders=max_orders)
            orders = merge_with_existing(orders, existing_by_number)
            orders = dedupe_orders(orders)

            # Orders to refresh keep their saved items until the new fetch
            # succeeds. Mark them on disk too, so a run that's stopped before
            # reaching them still refreshes them next time.
            for o in orders:
                if o.refresh:
                    if _before_since_date(o, since_date):
                        o.refresh = False  # older than the cutoff: not refetched
                    else:
                        o.fetch_error = "status changed; item detail not refreshed yet"

            already_saved_count = sum(1 for o in orders if o.items and not o.refresh)
            to_fetch = [
                o for o in orders
                if (not o.items or o.refresh) and not _before_since_date(o, since_date)
            ]
            skipped_by_date_count = len(orders) - already_saved_count - len(to_fetch)
            summary = (
                f"Found {len(orders)} order(s) total "
                f"({already_saved_count} already saved"
            )
            if since_date is not None:
                summary += f", {skipped_by_date_count} before --since-date"
            summary += f", {len(to_fetch)} to fetch).\n"
            print(summary)

            for idx, order in enumerate(orders, 1):
                if _interrupt.count > 0:
                    break  # Ctrl+C -- stop between orders rather than mid-request
                if order.items and not order.refresh:
                    print(f"  [{idx}/{len(orders)}] {order.order_number} (already saved, skipping)")
                    continue
                if _before_since_date(order, since_date):
                    print(
                        f"  [{idx}/{len(orders)}] {order.order_number} "
                        f"(placed {order.order_date}, before --since-date, skipping)"
                    )
                    continue
                print(
                    f"  [{idx}/{len(orders)}] {order.order_number}"
                    + (" (status changed, refreshing)" if order.refresh else "")
                )
                try:
                    page.goto(order.url, wait_until="domcontentloaded", timeout=20000)
                    dismiss_interstitials(page)
                    # Like the order list, item content on this page can
                    # render a moment after the shell loads -- wait for at
                    # least one "Item: NNN" / "SKU: NNN" row to actually
                    # show up before reading the page, instead of a flat
                    # delay that's sometimes too short and silently yields
                    # an order with zero items. A gift-card-only order has
                    # neither "Item:" nor "SKU:" anywhere on the page (it
                    # goes straight from the item name to "Quantity:"), so
                    # that alone would time out here every single time --
                    # match "Quantity:" too so gift-card orders are waited
                    # for correctly instead of always falling through to the
                    # 15s-timeout path below.
                    try:
                        page.get_by_text(
                            re.compile(r"^(Item|SKU|Quantity):\s*\S+")
                        ).first.wait_for(state="visible", timeout=15000)
                    except PWTimeoutError:
                        print(
                            "      (no item rows appeared within 15s -- this "
                            "order may genuinely have none, or the page "
                            "didn't finish loading; parsing whatever's there)"
                        )
                    page.wait_for_timeout(int(delay * 1000))
                    detail_text = page.locator("main").inner_text()
                    new_items = parse_order_detail(detail_text)
                    if order.refresh and not new_items:
                        raise RuntimeError("no items found on the order page")
                    order.items = new_items
                    order.summary = _parse_order_summary(detail_text)
                    _reconcile_total(order)
                    order.fetch_error = None
                except Exception as e:
                    # One slow/broken order shouldn't take the whole run down
                    # -- log it, leave it for a future run, and keep going. A
                    # new order's items stay empty (so it's retried); an order
                    # being refreshed keeps the items saved earlier, and its
                    # fetch_error makes the next run try the refresh again.
                    if order.refresh:
                        print(f"      couldn't refresh this order, keeping its saved detail: {e}")
                    else:
                        print(f"      failed to fetch this order, skipping it: {e}")
                        order.items = []
                    order.fetch_error = str(e)
                order.refresh = False
                write_outputs(orders, json_path, csv_path, quiet=True,
                              include_tracking=include_tracking)
                time.sleep(delay)

        except KeyboardInterrupt:
            # Backstop for the rare case a raw KeyboardInterrupt gets raised
            # despite our signal handler (e.g. it fires during something
            # that resets signal handling) -- treat it the same as a
            # normal Ctrl+C rather than letting it crash out with a
            # traceback.
            _interrupt.count = max(_interrupt.count, 1)
        finally:
            if _interrupt.count > 0:
                done = sum(1 for o in orders if o.items)
                print(
                    f"\nStopped early. {done}/{len(orders)} order(s) are "
                    f"saved in {json_path} and {csv_path} -- re-run the "
                    "same command to pick up where this left off."
                )
            # Best-effort cleanup: if closing hangs or errors out, the
            # user's second Ctrl+C (which hard-exits immediately) is
            # always available as an escape hatch, so don't let a cleanup
            # failure here turn into an ugly crash.
            try:
                context.close()
            except Exception:
                pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    write_outputs(orders, json_path, csv_path, include_tracking=include_tracking)
    if not include_tracking:
        orders = without_tracking(orders)
    return orders


def without_tracking(orders):
    """Copies of `orders` with every item's tracking_number blanked (None).
    Used by --no-tracking: the tracking_number field/column stays in every
    output file (so the files keep the same shape and still resume/merge
    normally), it's just empty. The originals are left untouched."""
    stripped = []
    for order in orders:
        copy = LegoOrder.from_dict(order.to_dict())
        for item in copy.items:
            item.tracking_number = None
        stripped.append(copy)
    return stripped


def _rename_old_csv(csv_path):
    """One-time switch to the new default name: if csv_path is lego_orders.csv,
    doesn't exist yet, and an old lego_order_items.csv sits in the same folder,
    rename the old file. (The CSV is rebuilt from the JSON on every run anyway,
    so this only keeps the folder tidy.) Returns True if it renamed a file."""
    new = Path(csv_path)
    old = new.with_name(OLD_DEFAULT_CSV_NAME)
    if new.name != DEFAULT_CSV_PATH or new.exists() or not old.is_file():
        return False
    try:
        old.replace(new)
    except OSError as e:
        print(f"  (couldn't rename {old.name} to {new.name}: {e})")
        return False
    print(f"Renamed {old.name} to {new.name} (the CSV's new default name).")
    return True


def write_outputs(orders, json_path, csv_path, quiet=False, include_tracking=True):
    """Write the current in-memory `orders` list to disk (both formats),
    atomically. Safe to call after every single order -- that's exactly
    what `scrape()` does, so progress is never lost to an interruption.
    include_tracking=False blanks every tracking number (--no-tracking)."""
    # Defensive: dedupe here too (not just in scrape()) so JSON and CSV are
    # always built from the exact same, duplicate-free list -- whatever
    # calls this function can't accidentally hand it a list with the same
    # order_number twice and get the two output files out of sync.
    orders = dedupe_orders(orders)
    if not include_tracking:
        orders = without_tracking(orders)

    def _write_json(tmp_path):
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump([o.to_dict() for o in orders], f, indent=2, ensure_ascii=False)

    _atomic_write(json_path, _write_json)

    def _write_csv(tmp_path):
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "order_number", "order_date", "order_status", "order_total",
                    "order_subtotal", "order_delivery", "order_tax",
                    "order_insiders_discount", "order_discount",
                    "item_name", "item_number", "custom_id", "quantity",
                    "regular_price", "sale_price",
                    "is_free_gift", "is_piece", "is_gift_card", "item_status",
                    "tracking_number",
                ]
            )
            for order in orders:
                order_summary = order.summary or {}
                for item in order.items:
                    prices = item.prices or {}
                    writer.writerow(
                        [
                            order.order_number, order.order_date, order.status,
                            order.total,
                            order_summary.get("subtotal") or "",
                            order_summary.get("delivery") or "",
                            order_summary.get("tax") or "",
                            order_summary.get("insiders_discount") or "",
                            order_summary.get("discount") or "",
                            item.name, item.item_number,
                            item.custom_id,
                            item.quantity,
                            prices.get("product.regularPrice") or "",
                            prices.get("product.salePrice") or "",
                            item.is_free_gift, item.is_piece,
                            item.is_gift_card,
                            item.status, item.tracking_number,
                        ]
                    )

    _atomic_write(csv_path, _write_csv)

    if not quiet:
        with_items = sum(1 for o in orders if o.items)
        if with_items == len(orders):
            print(f"\nWrote {json_path} and {csv_path} ({len(orders)} order(s)).")
        else:
            # Some orders are listed but have no item detail yet -- e.g.
            # skipped by --since-date, or a fetch that failed and will be
            # retried next run. Say so explicitly rather than implying all
            # of them got full item-level detail written out, since the
            # CSV in particular only has rows for the ones that did.
            print(
                f"\nWrote {json_path} and {csv_path}: {len(orders)} order(s) "
                f"listed, {with_items} of them with item detail (the other "
                f"{len(orders) - with_items} have no items yet -- skipped by "
                "--since-date, or a fetch that failed and will be retried "
                "next run)."
            )


# ---------------------------------------------------------------------------
# HTML report
#
# A self-contained HTML file (no external CSS/JS/fonts/images -- everything
# needed to view it is inline) with every order and its full line-item
# detail, meant to be opened directly in a browser (double-click, or
# file://) or shared/emailed as a single file. Two ways to get one:
#   1. `lego_orders_scraper.py --html PATH` -- fetches from LEGO.com as
#      normal, then writes the report from the same run's results.
#   2. `lego_orders_to_html.py` -- builds it from an EXISTING
#      lego_orders.json, no browser/network/LEGO.com involved at all.
# Both paths end up calling write_html_report() below on a list of
# LegoOrder objects, so the two stay in sync automatically.
# ---------------------------------------------------------------------------

_HTML_STYLE = """
<style>
  :root {
    color-scheme: light dark;
    --bg: #f7f7f5; --panel: #ffffff; --text: #1d1d1f; --muted: #6b6b70;
    --border: #e3e3e0; --accent: #d01012; --accent-soft: #fdeceb;
    --bar: #2a78d6;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #17171a; --panel: #212125; --text: #ededf0; --muted: #9a9aa2;
      --border: #313136; --accent: #ff5a5c; --accent-soft: #3a1e1f;
      --bar: #3987e5;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 16px 64px; background: var(--bg); color: var(--text);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }
  .wrap { max-width: 980px; margin: 0 auto; }
  h1 { font-size: 1.6em; margin: 0 0 4px; }
  .generated { color: var(--muted); font-size: 0.9em; margin: 0 0 24px; }
  .stats { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 28px; }
  .stat {
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 18px; min-width: 140px; flex: 1 1 140px;
  }
  .stat .n { font-size: 1.5em; font-weight: 600; }
  .stat .l { color: var(--muted); font-size: 0.85em; }
  table { width: 100%; border-collapse: collapse; }
  .index-table { background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    overflow: hidden; margin-bottom: 36px; }
  .index-table th, .index-table td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); font-size: 0.92em; }
  .index-table tr:last-child td { border-bottom: none; }
  .index-table th { color: var(--muted); font-weight: 600; background: var(--bg); }
  .index-table a { color: var(--text); text-decoration: none; }
  .index-table a:hover { color: var(--accent); }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .order {
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 18px 20px; margin-bottom: 18px; scroll-margin-top: 16px;
  }
  .order-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; margin-bottom: 4px; }
  .order-head h2 { font-size: 1.1em; margin: 0; }
  .order-head .date, .order-head .total { color: var(--muted); font-size: 0.92em; }
  .order-head .total { margin-left: auto; font-weight: 600; color: var(--text); }
  .badge {
    display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 0.78em;
    font-weight: 600; background: var(--bg); border: 1px solid var(--border); color: var(--muted);
  }
  .badge-warn { background: var(--accent-soft); color: var(--accent); border-color: transparent; }
  .order-link { font-size: 0.85em; margin: 2px 0 14px; }
  .order-link a { color: var(--accent); text-decoration: none; }
  .order-link a:hover { text-decoration: underline; }
  .summary-table { margin: 4px 0 16px; max-width: 320px; }
  .summary-table td { padding: 2px 10px 2px 0; font-size: 0.9em; }
  .summary-table td.num { padding-right: 0; }
  .summary-table tr.total td { font-weight: 600; border-top: 1px solid var(--border); padding-top: 5px; }
  .items-table th, .items-table td { padding: 7px 10px; border-bottom: 1px solid var(--border); font-size: 0.9em; vertical-align: top; }
  .items-table th { text-align: left; color: var(--muted); font-weight: 600; }
  .items-table tr:last-child td { border-bottom: none; }
  .item-name .tag { margin-left: 6px; }
  .tag {
    display: inline-block; padding: 1px 7px; border-radius: 6px; font-size: 0.74em;
    background: var(--bg); border: 1px solid var(--border); color: var(--muted);
  }
  .strike { text-decoration: line-through; color: var(--muted); margin-right: 4px; }
  .no-detail { color: var(--muted); font-style: italic; font-size: 0.92em; margin: 4px 0 0; }
  .item-number { color: var(--muted); font-size: 0.85em; }
  .section-title { font-size: 1.05em; margin: 0 0 10px; }
  .monthly-wrap { background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    overflow-x: auto; margin-bottom: 8px; }
  .monthly-table th, .monthly-table td { padding: 7px 12px; border-bottom: 1px solid var(--border);
    font-size: 0.9em; text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .monthly-table th { color: var(--muted); font-weight: 600; background: var(--bg); }
  .monthly-table th:first-child, .monthly-table td:first-child { text-align: left; }
  .monthly-table td.zero { color: var(--muted); }
  .monthly-table tr.totals td { font-weight: 700; border-top: 2px solid var(--border); border-bottom: none;
    background: var(--bg); }
  .monthly-note { color: var(--muted); font-size: 0.8em; margin: 0 0 32px; }
  .year-charts { display: grid; gap: 12px; margin-bottom: 8px; }
  .year-chart { margin: 0; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px 6px; }
  .year-chart figcaption { display: flex; align-items: baseline; gap: 10px; margin-bottom: 4px; }
  .year-chart .year { font-weight: 600; }
  .year-chart .year-total { color: var(--muted); font-size: 0.9em; font-variant-numeric: tabular-nums; }
  .year-chart svg { display: block; width: 100%; height: auto; overflow: visible; }
  .year-chart .grid { stroke: var(--border); stroke-width: 1; }
  .year-chart .tick, .year-chart .month { fill: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
  .year-chart .peak { fill: var(--text); font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .year-chart .empty { fill: var(--muted); font-size: 13px; font-style: italic; }
  .year-chart .bar { fill: var(--bar); }
  .year-chart .bar:hover { opacity: 0.75; }
</style>
"""


def _esc(value):
    """html.escape(), tolerating None (renders as empty string)."""
    return html.escape(str(value)) if value is not None else ""


def _fmt_money(value):
    """Format a raw price string like '1234.5' as '$1,234.50'. Falls back
    to the raw value (prefixed with $) if it doesn't parse as a plain
    number, and to an em dash for None/empty (a free gift's price, or a
    summary line this order didn't have)."""
    if value is None or value == "":
        return "—"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return f"${_esc(value)}"
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def _render_order_summary_table(summary):
    """The small Subtotal/Delivery/Tax/Discount/Total breakdown under an
    order's header, if this order actually has one (see
    _parse_order_summary()) -- only the lines that are actually present."""
    if not summary:
        return ""
    rows = []
    for key, label in (
        ("subtotal", "Subtotal"),
        ("delivery", "Delivery"),
        ("tax", "Tax"),
        ("insiders_discount", "LEGO Insiders discount"),
        ("discount", "Discount"),
    ):
        if key in summary:
            rows.append(
                f"<tr><td>{_esc(label)}</td><td class=\"num\">{_fmt_money(summary[key])}</td></tr>"
            )
    if "total" in summary:
        rows.append(
            f"<tr class=\"total\"><td>Total</td><td class=\"num\">{_fmt_money(summary['total'])}</td></tr>"
        )
    if not rows:
        return ""
    return f'<table class="summary-table">{"".join(rows)}</table>'


def _render_item_row(item):
    tags = []
    if item.is_piece:
        tags.append("piece")
    if item.is_gift_card:
        tags.append("gift card")
    if item.is_free_gift:
        tags.append("free gift")
    tags_html = "".join(f'<span class="tag">{_esc(t)}</span>' for t in tags)

    number_bits = []
    if item.item_number:
        number_bits.append(_esc(item.item_number))
    if item.custom_id:
        number_bits.append(f"ID: {_esc(item.custom_id)}")
    item_number_html = " &middot; ".join(number_bits) if number_bits else "—"

    prices = item.prices or {}
    regular = prices.get("product.regularPrice")
    sale = prices.get("product.salePrice")
    if regular is not None and sale is not None and regular != sale:
        price_html = f'<span class="strike">{_fmt_money(regular)}</span>{_fmt_money(sale)}'
    else:
        price_html = _fmt_money(sale if sale is not None else regular)

    return (
        "<tr>"
        f'<td class="item-name">{_esc(item.name)}{tags_html}</td>'
        f'<td class="item-number">{item_number_html}</td>'
        f'<td class="num">{item.quantity if item.quantity is not None else "—"}</td>'
        f'<td class="num">{price_html}</td>'
        f"<td>{_esc(item.status)}</td>"
        f"<td>{_esc(item.tracking_number)}</td>"
        "</tr>"
    )


def _render_order_section(order, anchor):
    if order.items:
        items_html = (
            '<table class="items-table"><thead><tr>'
            "<th>Item</th><th>Item #</th><th>Qty</th><th>Price</th>"
            "<th>Status</th><th>Tracking #</th>"
            "</tr></thead><tbody>"
            + "".join(_render_item_row(item) for item in order.items)
            + "</tbody></table>"
        )
    else:
        items_html = '<p class="no-detail">No item detail fetched for this order yet.</p>'

    return (
        f'<section class="order" id="{_esc(anchor)}">'
        '<div class="order-head">'
        f"<h2>{_esc(order.order_number)}</h2>"
        f'<span class="badge">{_esc(order.status)}</span>'
        f'<span class="date">{_esc(order.order_date)}</span>'
        f'<span class="total">{_fmt_money(order.total)}</span>'
        "</div>"
        f'<p class="order-link"><a href="{_esc(order.url)}" target="_blank" rel="noopener">View on LEGO.com &rarr;</a></p>'
        + _render_order_summary_table(order.summary)
        + items_html
        + "</section>"
    )


_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]


def _render_monthly_spending_table(orders):
    """A years-by-months grid of money spent: one column per year (from the
    earliest to the latest year that has an order, so a year with no orders
    still shows up as a column of dashes rather than silently vanishing),
    one row per month January..December, and a final TOTALS row with each
    year's total. Each cell is the sum of the order totals for orders placed
    in that month of that year.

    An order whose date can't be parsed or that has no usable total can't be
    placed in the grid; if any were left out a note under the table says how
    many, so the grid never silently disagrees with the "Total spent" card.
    """
    amounts = {}  # (year, month) -> dollars
    skipped = 0
    for o in orders:
        d = _parse_order_date(o.order_date)
        try:
            amount = float(str(o.total).replace(",", ""))
        except (TypeError, ValueError):
            amount = None
        if d is None or amount is None:
            skipped += 1
            continue
        amounts[(d.year, d.month)] = amounts.get((d.year, d.month), 0.0) + amount

    if not amounts:
        return ""

    years = list(range(min(y for y, _ in amounts), max(y for y, _ in amounts) + 1))
    head = "<th>Month</th>" + "".join(f"<th>{y}</th>" for y in years)

    rows = []
    for m, name in enumerate(_MONTH_NAMES, start=1):
        cells = []
        for y in years:
            if (y, m) in amounts:
                cells.append(f"<td>{_fmt_money(f'{amounts[(y, m)]:.2f}')}</td>")
            else:
                cells.append('<td class="zero">—</td>')
        rows.append(f"<tr><td>{name}</td>{''.join(cells)}</tr>")

    totals = "".join(
        "<td>"
        + _fmt_money(f"{sum(v for (yy, _), v in amounts.items() if yy == y):.2f}")
        + "</td>"
        for y in years
    )
    rows.append(f'<tr class="totals"><td>Total</td>{totals}</tr>')

    note = ""
    if skipped:
        note = (
            f'<p class="monthly-note">{skipped} order(s) with no readable date or '
            "total are not included in this table.</p>"
        )
    else:
        note = '<p class="monthly-note">Based on each order\'s total, by the month it was placed.</p>'

    return (
        '<h2 class="section-title">Spending by month</h2>\n'
        '<div class="monthly-wrap"><table class="monthly-table">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>\n"
        + note
        + _render_monthly_charts(amounts, years)
    )


_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Chart geometry (SVG viewBox units; the SVG scales to the page width).
_CH_W, _CH_H = 920.0, 230.0
_CH_LEFT, _CH_RIGHT, _CH_TOP, _CH_BOTTOM = 64.0, 8.0, 22.0, 28.0
_CH_BAR = 24.0  # bar thickness; the rest of each month's slot is air


def _nice_scale(max_value):
    """A round axis maximum and tick step for max_value (whole dollars, at
    most 4 intervals): step is 1, 2 or 5 x a power of ten."""
    if max_value <= 0:
        return 1, 1
    raw = max_value / 4
    mag = 1
    while mag * 10 <= raw:
        mag *= 10
    step = 10 * mag
    for m in (1, 2, 5):
        if m * mag >= raw:
            step = m * mag
            break
    return step * math.ceil(max_value / step), step


def _f1(x):
    return f"{x:.1f}"


def _render_year_chart(year, months, total, nice_max, step):
    """One year's bar chart as inline SVG: a bar per month (heights on the
    shared scale), recessive gridlines with dollar ticks, month labels, the
    year's busiest month labeled, and a hover tooltip on every bar."""
    plot_w = _CH_W - _CH_LEFT - _CH_RIGHT
    plot_h = _CH_H - _CH_TOP - _CH_BOTTOM
    base = _CH_TOP + plot_h
    slot = plot_w / 12

    parts = []
    tick = 0
    while tick <= nice_max:
        y = base - tick / nice_max * plot_h
        parts.append(
            f'<line class="grid" x1="{_f1(_CH_LEFT)}" x2="{_f1(_CH_W - _CH_RIGHT)}" '
            f'y1="{_f1(y)}" y2="{_f1(y)}"/>'
            f'<text class="tick" x="{_f1(_CH_LEFT - 8)}" y="{_f1(y)}" dy="0.32em" '
            f'text-anchor="end">${tick:,}</text>'
        )
        tick += step

    peak_month = None
    peak_value = 0.0
    for m in range(1, 13):
        v = months.get(m)
        if v is not None and v > peak_value:
            peak_month, peak_value = m, v

    for m in range(1, 13):
        cx = _CH_LEFT + (m - 1) * slot + slot / 2
        parts.append(
            f'<text class="month" x="{_f1(cx)}" y="{_f1(_CH_H - 8)}" '
            f'text-anchor="middle">{_MONTH_ABBR[m - 1]}</text>'
        )
        v = months.get(m)
        if v is None:
            continue
        h = max(v, 0.0) / nice_max * plot_h
        if v > 0 and h < 1:
            h = 1.0  # keep a tiny month visible
        if h <= 0:
            continue
        x = cx - _CH_BAR / 2
        y = base - h
        r = min(4.0, h / 2, _CH_BAR / 2)
        label = f"{_MONTH_NAMES[m - 1]} {year}: {_fmt_money(f'{v:.2f}')}"
        parts.append(
            f'<path class="bar" d="M{_f1(x)},{_f1(base)} V{_f1(y + r)} '
            f'Q{_f1(x)},{_f1(y)} {_f1(x + r)},{_f1(y)} H{_f1(x + _CH_BAR - r)} '
            f'Q{_f1(x + _CH_BAR)},{_f1(y)} {_f1(x + _CH_BAR)},{_f1(y + r)} V{_f1(base)} Z">'
            f"<title>{_esc(label)}</title></path>"
        )
        if m == peak_month:
            parts.append(
                f'<text class="peak" x="{_f1(cx)}" y="{_f1(y - 6)}" '
                f'text-anchor="middle">{_fmt_money(f"{v:.2f}")}</text>'
            )

    if not any(v > 0 for v in months.values()):
        parts.append(
            f'<text class="empty" x="{_f1(_CH_LEFT + plot_w / 2)}" y="{_f1(_CH_TOP + plot_h / 2)}" '
            'text-anchor="middle">No spending this year</text>'
        )

    return (
        '<figure class="year-chart">'
        f'<figcaption><span class="year">{year}</span>'
        f'<span class="year-total">{_fmt_money(total)}</span></figcaption>'
        f'<svg viewBox="0 0 {_CH_W:g} {_CH_H:g}" role="img" '
        f'aria-label="Spending by month in {year}">{"".join(parts)}</svg>'
        "</figure>"
    )


def _render_monthly_charts(amounts, years):
    """One bar chart per year (same scale for all, so years can be compared by
    bar height), placed after the "Spending by month" table. `amounts` is the
    table's {(year, month): dollars} dict; years with no orders get an empty
    chart, just as they get a column of dashes in the table."""
    if not amounts:
        return ""
    nice_max, step = _nice_scale(max(amounts.values()))
    charts = []
    for y in years:
        months = {m: v for (yy, m), v in amounts.items() if yy == y}
        total = f"{sum(v for (yy, _), v in amounts.items() if yy == y):.2f}"
        charts.append(_render_year_chart(y, months, total, nice_max, step))
    return (
        '<h2 class="section-title">Spending by month, by year</h2>\n'
        f'<div class="year-charts">{"".join(charts)}</div>\n'
        '<p class="monthly-note">All charts use the same scale, so bar heights can be '
        "compared across years. Hover a bar for its exact amount.</p>\n"
    )


def render_orders_html(orders, title="LEGO Order History"):
    """Render a complete, self-contained HTML document (inline CSS, no
    external resources) listing every order and its full line-item detail.
    Orders with no item detail yet (skipped by --since-date, or a failed
    fetch awaiting retry) are still listed, with a short note instead of an
    item table -- nothing is hidden or silently dropped."""
    generated_at = datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p")
    total_orders = len(orders)
    with_items = sum(1 for o in orders if o.items)
    total_items = sum(len(o.items) for o in orders)

    total_spent = 0.0
    for o in orders:
        try:
            total_spent += float(o.total)
        except (TypeError, ValueError):
            pass  # an order with no/garbled total just doesn't count toward this sum

    index_rows = []
    order_sections = []
    for order in orders:
        anchor = f"order-{order.order_number}"
        detail_note = "" if order.items else ' <span class="badge badge-warn">no detail</span>'
        index_rows.append(
            "<tr>"
            f'<td><a href="#{_esc(anchor)}">{_esc(order.order_number)}</a></td>'
            f"<td>{_esc(order.order_date)}</td>"
            f"<td>{_esc(order.status)}</td>"
            f'<td class="num">{_fmt_money(order.total)}</td>'
            f"<td>{len(order.items)} item(s){detail_note}</td>"
            "</tr>"
        )
        order_sections.append(_render_order_section(order, anchor))

    stats_html = "".join(
        f'<div class="stat"><div class="n">{_esc(n)}</div><div class="l">{_esc(label)}</div></div>'
        for n, label in (
            (total_orders, "Orders"),
            (with_items, "With item detail"),
            (total_items, "Total items"),
            (f"${total_spent:,.2f}", "Total spent"),
        )
    )

    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n" + _HTML_STYLE + "</head>\n<body>\n"
        '<div class="wrap">\n'
        f"<h1>{_esc(title)}</h1>\n"
        f'<p class="generated">Generated {_esc(generated_at)}</p>\n'
        f'<div class="stats">{stats_html}</div>\n'
        + _render_monthly_spending_table(orders)
        + '\n<table class="index-table"><thead><tr>'
        "<th>Order</th><th>Date</th><th>Status</th><th>Total</th><th>Items</th>"
        f"</tr></thead><tbody>{''.join(index_rows)}</tbody></table>\n"
        + "\n".join(order_sections)
        + "\n</div>\n</body>\n</html>\n"
    )


def write_html_report(orders, html_path, include_tracking=True):
    """Write render_orders_html()'s output to html_path, atomically (same
    _atomic_write() used for the JSON/CSV outputs). Doesn't print anything
    itself -- callers report what they wrote. include_tracking=False blanks
    every tracking number (--no-tracking)."""
    orders = dedupe_orders(orders)
    if not include_tracking:
        orders = without_tracking(orders)

    def _write_html(tmp_path):
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(render_orders_html(orders))

    _atomic_write(html_path, _write_html)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape your LEGO.com order history with item-level detail."
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--max-orders", type=int, default=None,
        help="Only fetch the N most recent orders (default: all of them).",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run without a visible browser window. Only works once you're "
        "already logged in via the saved profile folder.",
    )
    parser.add_argument(
        "--delay", type=float, default=1.5,
        help="Seconds to wait between order-detail page loads (default 1.5). "
        "Please keep this reasonable -- it's real traffic to LEGO's site.",
    )
    parser.add_argument(
        "--load-more-delay", type=float, default=1.2,
        help="Seconds to wait after each 'Load More' click on the order list "
        "page, before checking for the next batch (default 1.2). Separate "
        "from --delay, which only applies to order-detail pages.",
    )
    parser.add_argument(
        "--load-more-final-wait", type=float, default=5.0,
        help="Seconds to wait for the 'Load More' button to reappear when "
        "it's not immediately visible, before concluding there are no more "
        "orders to load and moving on to fetching item detail (default "
        "5.0). Bump this up if orders sometimes get cut off early because "
        "the next batch was just slow to render.",
    )
    parser.add_argument(
        "--output-dir", default=None, metavar="FOLDER",
        help="Folder to save the JSON, CSV and HTML files in (created if needed). "
        "Default: the data folder -- ~/Library/Application Support/LEGO Order Scraper "
        "on a Mac, %%LOCALAPPDATA%%\\LEGO Order Scraper on Windows. Use "
        "'--output-dir browse' to choose it in your system's folder dialog. Saved "
        "progress lives with the files, so a new folder starts fresh.",
    )
    parser.add_argument(
        "--output", default="lego_orders.json",
        help="Output JSON file (default: lego_orders.json). A relative path goes in "
        "--output-dir, or else the data folder."
    )
    parser.add_argument(
        "--csv", default=DEFAULT_CSV_PATH,
        help="Output CSV file, one row per item (default: lego_orders.csv, in the "
        "same folder as --output).",
    )
    parser.add_argument(
        "--cookie-source", default=None,
        help="Path to another Chrome instance's PROFILE folder that's already "
        "signed in to LEGO.com (e.g. '.../User Data/Default'). Its lego.com "
        "cookies are decrypted and imported instead of logging in fresh. "
        "See the module docstring for typical paths per OS.",
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Ignore any existing --output file and refetch every order's "
        "item detail from scratch, instead of the default behavior of "
        "resuming (skipping orders whose detail is already saved).",
    )
    parser.add_argument(
        "--since-date", type=_parse_cli_date, default=DEFAULT_SINCE_DATE,
        metavar="MM/DD/YYYY|all",
        help=f"Only fetch item detail for orders placed on or after this "
        f"date (format MM/DD/YYYY, e.g. 01/31/2026). DEFAULT: "
        f"{DEFAULT_SINCE_DATE} when this option isn't given; pass "
        "'--since-date all' to fetch your entire order history. "
        "Since LEGO lists orders "
        "newest-first, this also stops clicking 'Load More' on the order "
        "list as soon as the oldest order loaded so far is already before "
        "this date, instead of paging through your entire order history "
        "just to then skip fetching detail for most of it. An order from "
        "a PREVIOUS run (saved in --output already) that falls before this "
        "date is still kept in the output as-is; an order older than this "
        "date that's never been saved before won't appear in this run's "
        "output at all, since the order list stops paging before reaching "
        "it -- rerun with '--since-date all' (or an earlier date) if you "
        "need those. Handy for quickly picking up your newest orders "
        "without re-checking your whole history.",
    )
    parser.add_argument(
        "--html", default=DEFAULT_HTML_PATH, metavar="PATH",
        help="Where to write the self-contained HTML report (every order and "
        "its full line-item detail, viewable by just opening it in a "
        f"browser), built from this same run's results. Default: "
        f"{DEFAULT_HTML_PATH}. Use --no-html to skip it. To build an HTML "
        "report from an EXISTING --output file without fetching anything, "
        "use the separate lego_orders_to_html.py script instead.",
    )
    parser.add_argument(
        "--no-html", action="store_true",
        help="Don't write the HTML report.",
    )
    parser.add_argument(
        "--no-tracking", action="store_true",
        help="Leave tracking numbers out of the output files (JSON, CSV and "
        "HTML). The tracking_number field/column is still there, just empty, "
        "so the files keep the same shape. Note: orders saved while this is "
        "on are saved without tracking numbers -- to get them back later, run "
        "again without --no-tracking and with --fresh.",
    )
    args = parser.parse_args()

    # Output files go in --output-dir, else the data folder (relative paths are resolved there).
    out_base = choose_output_dir(args.output_dir)
    args.output = str(resolve_output_path(args.output, out_base))
    args.csv = str(resolve_output_path(args.csv, out_base))
    if args.html:
        args.html = str(resolve_output_path(args.html, out_base))
    log_path = _start_log()

    print(f"lego_orders_scraper.py v{__version__}")
    for f in (args.output, args.csv, args.html):
        if f:
            Path(f).parent.mkdir(parents=True, exist_ok=True)
    print(f"Output folder: {Path(args.output).parent}")
    if log_path:
        print(f"Log file: {log_path}")
    if args.since_date is None:
        print("Since date: none (fetching all orders)")
    else:
        print(
            f"Since date: {args.since_date.strftime('%m/%d/%Y')} "
            "(use --since-date all for every order, or another date)"
        )

    orders = scrape(
        max_orders=args.max_orders,
        headless=args.headless,
        delay=args.delay,
        load_more_delay=args.load_more_delay,
        load_more_final_wait=args.load_more_final_wait,
        cookie_source=args.cookie_source,
        json_path=args.output,
        csv_path=args.csv,
        fresh=args.fresh,
        since_date=args.since_date,
        include_tracking=not args.no_tracking,
    )

    if args.html and not args.no_html:
        write_html_report(orders, args.html, include_tracking=not args.no_tracking)
        print(f"Wrote {args.html}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Last-resort safety net: the SIGINT handler installed in scrape()
        # handles Ctrl+C gracefully in the normal case, but if something
        # outside its control (e.g. Playwright's own driver startup)
        # resets Python's signal handling back to the default at just the
        # wrong moment, a raw KeyboardInterrupt can still slip through.
        # Catch it here so that always ends in a clean message instead of
        # a traceback, no matter where the interrupt actually landed.
        print("\nInterrupted -- exiting.")
        sys.exit(1)
