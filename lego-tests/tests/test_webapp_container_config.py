"""Container settings: LEGO_WORK_DIR / LEGO_NOVNC_PORT env vars, /config route, --host flag.
Run in fresh interpreters because these are read at import time."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import json, os, subprocess, sys, tempfile

work = tempfile.mkdtemp(prefix="lego_work_")
code = """
import json, sys
sys.path.insert(0, %r)
import lego_orders_webapp as w
c = w.app.test_client()
print(json.dumps({"cfg": c.get("/config").get_json(), "work": str(w.WORK_DIR)}))
""" % SRC
def run(env_extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("LEGO_")}
    env.update(env_extra)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])

r = run({"LEGO_WORK_DIR": work, "LEGO_NOVNC_PORT": "6080"})
assert r["work"] == os.path.realpath(work), r
cfg = r["cfg"]
assert (cfg["novnc_port"], cfg["work_dir"], cfg["app_mode"]) == ("6080", os.path.realpath(work), None), r
assert cfg["folder_option"] is False and cfg["can_browse"] is False, r   # Docker: files stay in the volume
print("env vars set -> WORK_DIR and noVNC port honored by /config; folder choice hidden in Docker: OK")

r = run({})
import platform
if platform.system() == "Darwin":
    expected = os.path.expanduser("~/Library/Application Support/LEGO Order Scraper")
elif platform.system() == "Windows":
    expected = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local"), "LEGO Order Scraper")
else:
    expected = SRC
assert r["cfg"]["novnc_port"] is None and r["work"] == os.path.realpath(expected), r
print("env vars unset -> Mac: Application Support folder; Windows: %LOCALAPPDATA%; Linux: script folder; no noVNC link: OK")

h = subprocess.run([sys.executable, SRC + "/lego_orders_webapp.py", "--help"], capture_output=True, text=True)
assert "--host" in h.stdout and "127.0.0.1" in h.stdout and "8765" in h.stdout, h.stdout
print("--host flag exists (default 127.0.0.1) and default port is 8765: OK")
print("\nALL WEBAPP CONTAINER CONFIG TESTS PASSED")
