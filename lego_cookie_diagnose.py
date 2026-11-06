#!/usr/bin/env python3
"""
lego_cookie_diagnose.py

Run this NEXT TO lego_orders_scraper.py (same folder) to figure out exactly
which step of --cookie-source is failing, without ever printing a decrypted
cookie value (those are session tokens -- treat them like a password, so
this script only ever prints lengths/counts/booleans, never the value).

USAGE
-----
    python lego_cookie_diagnose.py "$HOME/Library/Application Support/Google/Chrome/Default"

It walks through, stopping at (and clearly reporting) the first failure:
  1. Can we find a 'Cookies' file under the given path?
  2. Can we open it as SQLite and read the 'cookies' table's schema?
  3. How many rows match host LIKE '%lego.com%', and what are their names/hosts
     (no values)?
  4. (macOS) Can we pull the 'Chrome Safe Storage' password from Keychain?
  5. Can we actually decrypt ONE of those lego.com cookies?

Paste the full output back and that'll usually pin down the fix.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    import lego_orders_scraper as scraper
except ImportError:
    print(
        "Couldn't import lego_orders_scraper.py -- put this diagnose script "
        "in the SAME FOLDER as lego_orders_scraper.py and run it from there."
    )
    sys.exit(1)


def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <chrome-profile-folder>")
        sys.exit(1)

    profile_path = sys.argv[1]
    print(f"Checking Chrome profile folder:\n  {profile_path}\n")

    # --- Step 1: find the Cookies file -------------------------------------
    print("[1/5] Locating the Cookies database...")
    try:
        db_path = scraper._find_cookie_db(profile_path)
        print(f"   OK: found {db_path} ({db_path.stat().st_size} bytes)\n")
    except Exception as e:
        print(f"   FAILED: {e}\n")
        return

    # --- Step 2: open it, read schema ---------------------------------------
    print("[2/5] Copying it (in case Chrome has it open) and reading its schema...")
    try:
        tmp_db = scraper._copy_locked_db(db_path)
        conn = sqlite3.connect(str(tmp_db))
        cur = conn.cursor()
        col = scraper._cookie_columns(cur)
        print(f"   OK: resolved columns -> {col}\n")
    except Exception as e:
        print(f"   FAILED: {e}\n")
        return

    # --- Step 3: count lego.com rows ----------------------------------------
    print("[3/5] Counting cookies whose host contains 'lego.com'...")
    try:
        cur.execute(
            f"SELECT {col['host']}, {col['name']}, "
            f"length({col['value']}) as value_len, "
            f"length({col['encrypted_value']}) as enc_len "
            f"FROM cookies WHERE {col['host']} LIKE ?",
            ("%lego.com%",),
        )
        rows = cur.fetchall()
        if not rows:
            print(
                "   FOUND 0 cookies for lego.com in this profile.\n"
                "   -> This is almost certainly the actual problem: either this\n"
                "      Chrome profile isn't the one signed in to LEGO.com (check\n"
                "      chrome://version in that exact window), or you're not\n"
                "      currently signed in there. Sign in to LEGO.com in THIS\n"
                "      Chrome profile/window and re-run.\n"
            )
            conn.close()
            return
        print(f"   OK: found {len(rows)} cookie(s):")
        for host, name, value_len, enc_len in rows:
            state = "plaintext" if value_len else ("encrypted" if enc_len else "EMPTY")
            print(f"     - {name} @ {host}  [{state}]")
        print()
    except Exception as e:
        print(f"   FAILED: {e}\n")
        conn.close()
        return

    # --- Step 4: derive the OS decryption key --------------------------------
    print("[4/5] Deriving the OS-level decryption key (macOS Keychain)...")
    try:
        key = scraper._macos_derive_key()
        print(f"   OK: got a {len(key)}-byte key from Keychain\n")
    except Exception as e:
        print(f"   FAILED: {e}\n")
        print(
            "   -> If macOS showed a Keychain prompt for 'Chrome Safe Storage' and\n"
            "      you clicked Deny (or it timed out), re-run this and click Allow\n"
            "      (or 'Always Allow') when it appears.\n"
        )
        conn.close()
        return

    # --- Step 5: decrypt exactly one cookie -----------------------------------
    print("[5/5] Attempting to decrypt one lego.com cookie (value will NOT be printed)...")
    encrypted_rows = [r for r in rows if r[3]]  # has encrypted_value
    if not encrypted_rows:
        print("   Nothing encrypted to test (all matching cookies were already plaintext/empty).\n")
        conn.close()
        return

    test_name, test_host = encrypted_rows[0][1], encrypted_rows[0][0]
    cur.execute(
        f"SELECT {col['encrypted_value']} FROM cookies "
        f"WHERE {col['name']} = ? AND {col['host']} = ?",
        (test_name, test_host),
    )
    encrypted_value = cur.fetchone()[0]
    try:
        value = scraper._decrypt_cookie_value(encrypted_value, key, "Darwin")
        print(f"   OK: decrypted '{test_name}' successfully ({len(value)} characters).\n")
        print("Everything checks out -- --cookie-source should work. If the main")
        print("script still fails after this, the failure is likely later, in the")
        print("Playwright browser step (e.g. `playwright install chromium` not run).")
    except Exception as e:
        print(f"   FAILED: {e}\n")

    conn.close()


if __name__ == "__main__":
    main()
