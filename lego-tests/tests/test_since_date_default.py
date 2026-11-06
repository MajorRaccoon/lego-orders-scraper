"""--since-date now defaults to 02/01/2024 (CLI + web form); 'all' turns it off."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import argparse, datetime, re, sys
sys.path.insert(0, SRC)
import lego_orders_scraper as sc
import lego_orders_webapp as wa
import unittest.mock as mock
import os, tempfile
os.chdir(tempfile.mkdtemp(prefix="lego_sdd_"))  # main() writes lego_orders.html by default; keep it out of the repo

assert sc.DEFAULT_SINCE_DATE == "02/01/2024" == wa.DEFAULT_SINCE_DATE
print("CLI and web default constants agree on 02/01/2024: OK")

assert sc._parse_cli_date("02/01/2024") == datetime.date(2024, 2, 1)
for v in ("all", "ALL", "none", ""):
    assert sc._parse_cli_date(v) is None, v
try:
    sc._parse_cli_date("2024-02-01"); assert False
except argparse.ArgumentTypeError:
    pass
print("_parse_cli_date: real dates parse, 'all'/'none'/blank -> None, garbage rejected: OK")

def run_main(argv):
    seen = {}
    with mock.patch.object(sc, "scrape", lambda **kw: seen.update(kw) or []), \
         mock.patch.object(sys, "argv", ["x"] + argv):
        sc.main()
    return seen["since_date"]
assert run_main([]) == datetime.date(2024, 2, 1)
assert run_main(["--since-date", "all"]) is None
assert run_main(["--since-date", "06/15/2025"]) == datetime.date(2025, 6, 15)
print("CLI: omitted -> 2024-02-01; 'all' -> None; explicit date honored: OK")

m = re.search(r'id="since_date"[^>]*value="([^"]*)"', wa.INDEX_HTML)
assert m and m.group(1) == "02/01/2024", m
print("Web form 'Since date' box is pre-filled with 02/01/2024: OK")
print("\nALL SINCE-DATE-DEFAULT TESTS PASSED")
