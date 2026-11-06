"""When a scrape ends, the web UI prints a reminder in Terminal that the server is still running
and Ctrl+C quits it -- but only when it was started by hand in a Terminal (not in Docker or the
Mac app, where there's no terminal to press Ctrl+C in)."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import contextlib, io, sys, time
from pathlib import Path
import unittest.mock as mock
sys.path.insert(0, SRC)
import lego_orders_webapp as webapp

# Wording for each way a scrape can end.
m = webapp.finish_reminder("finished", 0, "http://127.0.0.1:8765/")
assert m.startswith("Scrape finished.") and "still running at http://127.0.0.1:8765/" in m and "Ctrl+C" in m, m
assert webapp.finish_reminder("stopped", 1).startswith("Scrape stopped.")
e = webapp.finish_reminder("error", 2)
assert "error (exit code 2)" in e and "Ctrl+C" in e and " at " not in e
print("Reminder says how the scrape ended, where the UI is, and that Ctrl+C quits: OK")

# Captured output (as in Docker, the Mac app, or this test run) is not an interactive terminal.
assert webapp._interactive_terminal() is False
print("Not an interactive terminal when output is captured (Docker / Mac app): OK")

# End to end with the fake scraper: printed to Terminal only when interactive.
webapp.SCRAPER_PATH = Path(__file__).resolve().parent / "fake_scraper.py"
webapp.SERVE_URL = "http://127.0.0.1:9999/"

def run_scrape(interactive):
    job = webapp.ScrapeJob()
    out = io.StringIO()
    with mock.patch.object(webapp, "_interactive_terminal", return_value=interactive), contextlib.redirect_stdout(out):
        job.start({})
        # The fake scraper waits for Enter (its "login" step); answer it like the web page's button.
        for _ in range(100):
            if job.snapshot()["status"] != "running":
                break
            try:
                job.send_enter()
            except RuntimeError:
                pass
            time.sleep(0.1)
        job.reader_thread.join(timeout=30)
    return job, out.getvalue()

job, printed = run_scrape(True)
assert job.status == "finished", job.status
assert "Scrape finished. The web UI is still running at http://127.0.0.1:9999/ -- press Ctrl+C here" in printed, printed
assert any("[process exited with code 0]" in l for l in job.snapshot()["lines"])   # web page log unchanged
print("Interactive Terminal: reminder printed when the scrape finishes; page log unchanged: OK")

job, printed = run_scrape(False)
assert job.status == "finished" and "Ctrl+C" not in printed, printed
print("Docker / Mac app (not interactive): nothing extra printed: OK")
print("\nALL FINISH-REMINDER TESTS PASSED")
