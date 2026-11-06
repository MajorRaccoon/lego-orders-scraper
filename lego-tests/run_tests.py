#!/usr/bin/env python3
"""Run every tests/test_*.py against the scripts in this folder's PARENT directory
(or LEGO_SRC=/path/to/scripts). Usage:  python run_tests.py
Needs: playwright, cryptography, flask (same as the scripts)."""
import glob, os, subprocess, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__))
# Never touch the real data folder or log: every test gets a throwaway one.
_sandbox = tempfile.mkdtemp(prefix="lego_tests_")
os.environ["LEGO_WORK_DIR"] = os.path.join(_sandbox, "data")
os.environ["LEGO_LOG_FILE"] = os.path.join(_sandbox, "test.log")
failed = []
for t in sorted(glob.glob(os.path.join(here, "tests", "test_*.py"))):
    r = subprocess.run([sys.executable, t], capture_output=True, text=True, timeout=180)
    ok = r.returncode == 0
    print(("PASS  " if ok else "FAIL  ") + os.path.basename(t))
    if not ok:
        failed.append(t); print((r.stdout + r.stderr)[-1500:])
print(f"\n{len(glob.glob(os.path.join(here, 'tests', 'test_*.py'))) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
