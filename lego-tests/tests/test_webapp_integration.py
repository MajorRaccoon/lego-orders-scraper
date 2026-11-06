"""
End-to-end test of lego_orders_webapp.py's job lifecycle through Flask's
test client, using fake_scraper.py (a tiny stand-in for
lego_orders_scraper.py) in place of the real scraper -- so this runs no
browser/network, but exercises the exact same subprocess/streaming/
input/interrupt plumbing the webapp uses for the real thing:
  - /start spawns the subprocess with the right argv and streams its output
  - /status returns accumulating log lines and correct status transitions
  - /input unblocks the subprocess's input() (the login-wait step)
  - /stop sends a graceful SIGINT the subprocess's own handler catches
  - /kill force-terminates a subprocess that isn't responding
  - only one job can run at a time
  - a prompt with no trailing newline (like input()'s own) shows up as
    "partial" output immediately, not only after it's answered
"""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, SRC)
import lego_orders_webapp as webapp

FAKE_SCRAPER = Path(__file__).resolve().parent / "fake_scraper.py"
assert FAKE_SCRAPER.is_file(), FAKE_SCRAPER

# Point the webapp at the fake scraper instead of the real one for this
# whole test run -- the module-level SCRAPER_PATH is read at call time by
# ScrapeJob.start(), so this substitution is picked up transparently.
webapp.SCRAPER_PATH = FAKE_SCRAPER

app = webapp.app
app.testing = True


def _poll_until(client, predicate, timeout=5.0, since=0):
    """Poll /status until predicate(snapshot) is true or timeout. Returns
    the final snapshot either way (the caller's own assert reports the
    failure with a useful message rather than this helper guessing one)."""
    deadline = time.time() + timeout
    snap = None
    while time.time() < deadline:
        res = client.get(f"/status?since={since}")
        snap = res.get_json()
        if predicate(snap):
            return snap
        time.sleep(0.05)
    return snap


client = app.test_client()

# --- Scenario 1: start -> login prompt -> send Enter -> runs to
# completion -> status "finished", return_code 0, output lines accumulate,
# and the argv we asked for actually reached the subprocess. ---------------
res = client.post(
    "/start", json={"max_orders": "3", "since_date": "01/31/2026", "headless": True},
)
assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
print("POST /start: accepted and spawned the (fake) scraper: OK")

snap = _poll_until(client, lambda s: "Press Enter" in s["partial"])
assert snap is not None and "Press Enter" in snap["partial"], snap
assert any("ARGV:--max-orders 3 --headless --since-date 01/31/2026" in l for l in snap["lines"]), snap["lines"]
print("Login prompt (no trailing newline) streamed through as 'partial' output immediately, before being answered: OK")
print("Subprocess received the exact argv build_argv() produced: OK")

res = client.post("/input", json={"text": ""})
assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
print("POST /input: sent Enter to unblock the subprocess's login prompt: OK")

snap = _poll_until(client, lambda s: s["status"] in ("finished", "error", "stopped"), timeout=10)
assert snap["status"] == "finished", snap
assert snap["return_code"] == 0, snap
full = client.get("/status?since=0").get_json()
assert any("got input:" in l for l in full["lines"]), full["lines"]
assert any(l.strip() == "done" for l in full["lines"]), full["lines"]
print("Ran to completion after Enter was sent: status=finished, return_code=0: OK")

# --- A second /start after the first finished is allowed (only ONE
# CONCURRENT job is disallowed, not a second job after the first ends). ----
res = client.post("/start", json={"max_orders": "abc"})
assert res.status_code == 400, res.get_json()
print("Invalid config (non-numeric max_orders) is rejected with 400 before ever spawning a process: OK")

# --- Scenario 2: Stop sends a graceful SIGINT the subprocess's own
# handler catches (mirrors lego_orders_scraper.py's real Ctrl+C handling).
res = client.post("/start", json={})  # no --skip-login arg, but we answer immediately below
assert res.get_json()["ok"]
_poll_until(client, lambda s: "Press Enter" in s["partial"])
client.post("/input", json={"text": ""})
_poll_until(client, lambda s: any("processing item" in l for l in s["lines"]))

res = client.post("/stop")
assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
snap = _poll_until(client, lambda s: s["status"] in ("finished", "error", "stopped"), timeout=10)
assert snap["status"] == "stopped", snap
full = client.get("/status?since=0").get_json()
assert any("SIGINT #1 received" in l for l in full["lines"]), full["lines"]
assert any("stopping gracefully after Ctrl+C" in l for l in full["lines"]), full["lines"]
print("Stop sends a graceful SIGINT; the subprocess's own 1st-Ctrl+C handling runs, status becomes 'stopped': OK")

# --- Stop / Enter / Kill on an idle (non-running) job are rejected with a
# clear 409, not a crash. ---------------------------------------------------
res = client.post("/stop")
assert res.status_code == 409, res.get_json()
res = client.post("/input", json={"text": ""})
assert res.status_code == 409, res.get_json()
res = client.post("/kill")
assert res.status_code == 409, res.get_json()
print("Stop/Input/Kill on a non-running job are all rejected with 409, not a crash: OK")

# --- Scenario 3: two /start calls while one is already running -- the
# second must be rejected (409), and the first must be left completely
# undisturbed by the attempt. ------------------------------------------------
res = client.post("/start", json={})
assert res.get_json()["ok"]
_poll_until(client, lambda s: "Press Enter" in s["partial"])

res2 = client.post("/start", json={})
assert res2.status_code == 409, res2.get_json()
print("A second /start while one is already running is rejected with 409: OK")

# Clean up this still-running job so it doesn't linger past the test.
client.post("/input", json={"text": ""})
_poll_until(client, lambda s: s["status"] in ("finished", "error", "stopped"), timeout=10)

# --- Scenario 4: Force-quit actually terminates a running subprocess. ------
res = client.post("/start", json={})
assert res.get_json()["ok"]
_poll_until(client, lambda s: any("processing item" in l for l in s["lines"]) or "Press Enter" in s["partial"])
client.post("/input", json={"text": ""})
_poll_until(client, lambda s: any("processing item" in l for l in s["lines"]))

res = client.post("/kill")
assert res.status_code == 200 and res.get_json()["ok"], res.get_json()
snap = _poll_until(client, lambda s: s["status"] in ("finished", "error", "stopped"), timeout=10)
assert snap["status"] == "stopped", snap  # force_kill sets stop_requested too
full = client.get("/status?since=0").get_json()
assert any("Force-killed" in l for l in full["lines"]), full["lines"]
print("Force-quit actually terminates the subprocess (status -> stopped, log notes the kill): OK")

print("\nALL WEBAPP INTEGRATION TESTS PASSED")
