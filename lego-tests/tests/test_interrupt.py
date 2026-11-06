"""_GracefulInterrupt: 1st Ctrl+C is acknowledged and counted; 2nd exits immediately."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import contextlib, io, sys
import unittest.mock as mock
sys.path.insert(0, SRC)
import lego_orders_scraper as sc

gi = sc._GracefulInterrupt()
buf = io.StringIO()
with contextlib.redirect_stdout(buf), mock.patch.object(sc.os, "_exit") as ex:
    gi(2, None)
    assert gi.count == 1 and not ex.called and "Ctrl+C received" in buf.getvalue()
    gi(2, None)
    assert gi.count == 2 and ex.call_args == mock.call(1)
print("1st Ctrl+C: acknowledged, flag set, no exit; 2nd: os._exit(1): OK")

# scrape() installs the handler and resets the counter
import signal
sc._interrupt.count = 5
with mock.patch.object(sc, "load_existing_orders", side_effect=RuntimeError("stop here")):
    try: sc.scrape(json_path="x.json", csv_path="x.csv")
    except RuntimeError: pass
assert sc._interrupt.count == 0 and signal.getsignal(signal.SIGINT) is sc._interrupt
print("scrape() installs the SIGINT handler and resets its counter: OK")
print("\nALL INTERRUPT TESTS PASSED")
