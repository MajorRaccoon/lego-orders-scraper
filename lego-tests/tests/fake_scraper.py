#!/usr/bin/env python3
"""
A tiny stand-in for lego_orders_scraper.py, used only by
test_webapp_integration.py. Mimics the two real-world behaviors the webapp
has to handle correctly without needing a real browser/network:
  1. Blocking on input() once (like the "Press Enter once you're signed
     in..." login step).
  2. A SIGINT handler with the same 1st-graceful / 2nd-immediate shape as
     lego_orders_scraper.py's own _GracefulInterrupt, so Stop/Force-quit
     can be tested against realistic behavior.
It also echoes its argv back, so tests can confirm the webapp is actually
passing the flags it's supposed to.
"""
import signal
import sys
import time

_interrupt_count = 0


def _handler(signum, frame):
    global _interrupt_count
    _interrupt_count += 1
    print(f"SIGINT #{_interrupt_count} received", flush=True)
    if _interrupt_count >= 2:
        sys.exit(1)


signal.signal(signal.SIGINT, _handler)

print("fake scraper starting", flush=True)
print("ARGV:" + " ".join(sys.argv[1:]), flush=True)

if "--skip-login" not in sys.argv:
    answer = input("Press Enter once you're signed in and on the My Orders page... ")
    print(f"got input: {answer!r}", flush=True)

iterations = 5 if "--short" in sys.argv else 20
for i in range(iterations):
    if _interrupt_count >= 1:
        print("stopping gracefully after Ctrl+C", flush=True)
        break
    print(f"processing item {i}", flush=True)
    time.sleep(0.05)
else:
    print("done", flush=True)

print("exiting", flush=True)
