"""
Verifies build_argv() -- the pure function that translates the web form's
config dict into the exact argv lego_orders_scraper.py's own CLI expects.
This is the piece that keeps the web UI and the CLI in lockstep, so it's
tested in isolation from Flask/subprocess entirely.
"""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys
sys.path.insert(0, SRC)
from lego_orders_webapp import build_argv

# --- Empty/default config -- no flags at all, scraper uses its own
# defaults for everything (visible browser, default paths, etc). ----------
assert build_argv({}) == []
print("Empty config -> no flags (scraper falls back to its own defaults): OK")

# --- Blank-string fields (what a form sends for an untouched optional
# input) must be treated as "not provided", not crash or emit "--flag ''".
blank = {
    "max_orders": "", "delay": "", "load_more_delay": "", "load_more_final_wait": "",
    "output": "", "csv": "", "html": "", "cookie_source": "",
    "headless": False, "fresh": False,
}
assert build_argv(blank) == []
print("Blank-string fields are treated as absent, not crashed on or emitted empty: OK")

# since_date is special: key ABSENT -> scraper's own default applies (flag
# omitted); key present but BLANK -> user cleared the box -> no cutoff.
assert build_argv({"since_date": ""}) == ["--since-date", "all"]
assert build_argv({"since_date": "  "}) == ["--since-date", "all"]
assert build_argv({"since_date": "ALL"}) == ["--since-date", "all"]
print("Blank/'all' since_date -> '--since-date all' (explicit no-cutoff): OK")

# --- Every option populated -- all flags present, correctly spelled and
# formatted, matching lego_orders_scraper.py's argparse definitions exactly.
full = {
    "max_orders": "25",
    "headless": True,
    "delay": "2.5",
    "load_more_delay": "3",
    "load_more_final_wait": "10",
    "output": "my.json",
    "csv": "my.csv",
    "html": "my.html",
    "cookie_source": "/path/to/chrome/profile",
    "fresh": True,
    "since_date": "01/31/2026",
}
argv = build_argv(full)
for pair in [
    ("--max-orders", "25"), ("--delay", "2.5"), ("--load-more-delay", "3.0"),
    ("--load-more-final-wait", "10.0"), ("--output", "my.json"), ("--csv", "my.csv"),
    ("--html", "my.html"), ("--cookie-source", "/path/to/chrome/profile"),
    ("--since-date", "01/31/2026"),
]:
    i = argv.index(pair[0])
    assert argv[i + 1] == pair[1], (pair, argv)
assert "--headless" in argv
assert "--fresh" in argv
print("Every option populated -> all flags present and correctly formatted: OK ->", argv)

# --- Checkboxes false -> their flags must be entirely absent (these are
# store_true flags on the CLI side; there's no "--headless false"). --------
argv2 = build_argv({"headless": False, "fresh": False})
assert "--headless" not in argv2 and "--fresh" not in argv2
print("headless=False / fresh=False -> no store_true flags emitted: OK")

# --- max_orders tolerates a form sending "5.0" for a number input (some
# browsers/JS serialize whole numbers with a trailing .0). -----------------
argv3 = build_argv({"max_orders": "5.0"})
i = argv3.index("--max-orders")
assert argv3[i + 1] == "5", argv3
print("max_orders='5.0' from a form is still parsed as an integer: OK")

# --- Garbage numeric input raises a clear, user-facing ValueError instead
# of silently passing garbage through to the subprocess's argparse. --------
try:
    build_argv({"delay": "not-a-number"})
    assert False, "expected ValueError"
except ValueError as e:
    assert "--delay" in str(e), e
    print("Garbage numeric input raises a clear ValueError naming the flag: OK ->", str(e))

# --- since_date validation: must be MM/DD/YYYY, matching
# lego_orders_scraper.py's own --since-date format exactly. ----------------
for bad in ["2026-01-31", "1/31/26", "not a date", "01/2026"]:
    try:
        build_argv({"since_date": bad})
        assert False, f"expected ValueError for {bad!r}"
    except ValueError as e:
        assert "--since-date" in str(e), e
print("Invalid --since-date formats are rejected with a clear error: OK")

# Valid single-digit month/day is accepted (e.g. 1/5/2026).
argv4 = build_argv({"since_date": "1/5/2026"})
assert argv4 == ["--since-date", "1/5/2026"], argv4
print("Valid single-digit MM/DD/YYYY since_date is accepted as-is: OK")

print("\nALL WEBAPP BUILD_ARGV TESTS PASSED")
