"""Choosing where the files are saved: the system folder dialog (lego_folder_picker.py), the CLI's
--output-dir (path or 'browse'), and the web UI's "Save files to" box with its Browse button (also
used by the Python Mac app and the Windows app). Dialogs themselves are mocked here."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import contextlib, io, json, os, subprocess, sys, tempfile
from pathlib import Path
import unittest.mock as mock
sandbox = Path(tempfile.mkdtemp(prefix="lego_outdir_"))
os.environ["LEGO_WORK_DIR"] = str(sandbox / "data")
os.environ["LEGO_LOG_FILE"] = str(sandbox / "test.log")
sys.path.insert(0, SRC)
import lego_folder_picker as fp
import lego_orders_scraper as sc

# --- folder dialog commands per OS ------------------------------------------
start = sandbox  # an existing folder
mac = fp.folder_dialog_command(start, 'Pick "it"', system="Darwin")
assert mac[:2] == ["osascript", "-e"] and "choose folder" in mac[2]
assert f"POSIX file {fp._applescript_quote(start)}" in mac[2]      # backslashes/quotes escaped (Windows-style paths too)
assert 'Pick \\"it\\"' in mac[2]                                  # quotes escaped for AppleScript
win = fp.folder_dialog_command(start, "Pick 'it'", system="Windows")
assert win[0] == "powershell" and "-STA" in win and "FolderBrowserDialog" in win[-1]
assert "'Pick ''it'''" in win[-1] and f"$d.SelectedPath = '{start}'" in win[-1]   # PowerShell quoting
assert "$d.SelectedPath = " not in fp.folder_dialog_command(sandbox / "missing", system="Windows")[-1]  # bad start ignored
with mock.patch.object(fp.shutil, "which", return_value=None):
    assert fp.folder_dialog_command(start, system="Linux") is None             # no zenity -> no dialog
with mock.patch.object(fp.shutil, "which", return_value="/usr/bin/zenity"):
    assert fp.folder_dialog_command(start, system="Linux")[:3] == ["zenity", "--file-selection", "--directory"]
print("Folder dialog: osascript (Mac), PowerShell (Windows), zenity (Linux), none otherwise; paths quoted safely: OK")

# Windows: the dialog is owned by a shown, always-on-top window pushed to the front,
# so it opens on top of the browser (not behind it); the owner is closed afterwards.
assert "TopMost = $true" in win[-1] and "$o.Show();" in win[-1] and "[LegoPick.Win]::Front($o.Handle)" in win[-1]
assert win[-1].index("$o.Show();") < win[-1].index("::Front(") < win[-1].index("ShowDialog($o)") < win[-1].index("$o.Close()")
assert "try { Add-Type" in win[-1]   # if the helper can't load, the dialog still opens
assert "[LegoPick.Win]::FindDialog()" in win[-1] and "$t.Start()" in win[-1]   # the dialog itself is pushed forward too
assert len(subprocess.list2cmdline(win)) < 30000   # fits a Windows command line
print("Windows: folder dialog is brought in front of the browser: OK")

# On a real system, check the dialog script is valid WITHOUT showing it.
import platform, shutil as _sh
if platform.system() == "Windows":
    ps = fp.folder_dialog_command(start, "Pick 'it'")[-1]
    check = ("$e = $null; [void][System.Management.Automation.Language.Parser]::ParseInput("
             + "'" + ps.replace("'", "''") + "', [ref]$null, [ref]$e); if ($e.Count) { $e; exit 1 }")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", check], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    print("Windows: the folder dialog's PowerShell script parses cleanly: OK")
    # The bring-to-front helper compiles and runs (passed the same way the real command is).
    front = ("Add-Type -AssemblyName System.Windows.Forms; "
             f"Add-Type -Namespace LegoPick -Name Win -MemberDefinition {fp._powershell_quote(fp._WIN_FRONT_CS)}; "
             "$o = New-Object System.Windows.Forms.Form -Property @{Opacity = 0; ShowInTaskbar = $false}; "
             "$o.Show(); [LegoPick.Win]::Front($o.Handle); $o.Close(); [Console]::Out.Write('front-ok')")
    r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", front], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "front-ok" in r.stdout, r.stdout + r.stderr
    print("Windows: the bring-to-front helper compiles and runs: OK")

    # On the GitHub Windows build machine only (it would pop up a dialog on your PC):
    # put another app (Notepad) in front, open the real folder dialog, and check the
    # dialog ends up as the window in front.
    if os.environ.get("GITHUB_ACTIONS"):
        import time
        watch = (
            "Add-Type -Namespace T -Name U -MemberDefinition '"
            '[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); '
            '[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid); '
            '[DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);'
            "'; $want = [uint32]$args[0]; $end = (Get-Date).AddSeconds(25); $last = ''; "
            "while ((Get-Date) -lt $end) { $h = [T.U]::GetForegroundWindow(); $p = [uint32]0; "
            "[void][T.U]::GetWindowThreadProcessId($h, [ref]$p); $c = New-Object System.Text.StringBuilder 64; "
            "[void][T.U]::GetClassName($h, $c, 64); $last = $c.ToString() + ' pid=' + $p; "
            "if ($p -eq $want -and $c.ToString() -eq '#32770') { 'FRONT ' + $last; exit 0 }; Start-Sleep -Milliseconds 200 }; "
            "'NOT-FRONT ' + $last; exit 1"
        )
        def front_check(pid):
            r = subprocess.run(["powershell", "-NoProfile", "-Command", "& {" + watch + "}", str(pid)],
                               capture_output=True, text=True, timeout=120)
            return r.returncode == 0, (r.stdout + r.stderr).strip()
        notepad = subprocess.Popen(["notepad.exe"])
        time.sleep(3)
        dialog = subprocess.Popen(fp.folder_dialog_command(start, "Pick a folder"),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ok, seen = front_check(dialog.pid)
        finally:
            dialog.kill(); notepad.kill()
        note = dialog.communicate(timeout=30)[1]
        print(f"Windows (GitHub): foreground check: {seen}; dialog note: {note.strip()!r}")
        assert ok, f"the folder dialog didn't come in front of Notepad: {seen}; {note}"
        print("Windows: the real folder dialog opens in front of another app: OK")
elif platform.system() == "Darwin" and _sh.which("osacompile"):
    script = fp.folder_dialog_command(start, 'Pick "it"')[2]
    r = subprocess.run(["osacompile", "-e", script, "-o", str(sandbox / "pick.scpt")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    print("macOS: the folder dialog's AppleScript compiles cleanly: OK")

def fake_run(stdout, code=0):
    return mock.patch.object(fp.subprocess, "run", return_value=subprocess.CompletedProcess([], code, stdout, ""))
with mock.patch.object(fp, "folder_dialog_command", return_value=["dialog"]):
    with fake_run("/Users/me/Orders/\n"):
        assert fp.choose_folder() == Path("/Users/me/Orders")
    with fake_run("", 1):
        assert fp.choose_folder() is None                                     # cancelled
with mock.patch.object(fp, "folder_dialog_command", return_value=None):
    assert fp.choose_folder() is None and fp.dialog_available() is False
real_exists = os.path.exists
with mock.patch.object(fp.os.path, "exists", side_effect=lambda p: p == "/.dockerenv" or real_exists(p)):
    assert fp.dialog_available() is False                                     # never inside Docker
print("choose_folder: chosen folder returned, cancel -> None, no dialog in Docker: OK")

# --- CLI --output-dir --------------------------------------------------------------
assert sc.choose_output_dir(None) is None
os.chdir(sandbox)
assert sc.choose_output_dir("rel/out") == (sandbox / "rel" / "out").resolve()  # relative = from the current folder
with mock.patch("lego_folder_picker.choose_folder", return_value=sandbox / "picked"):
    assert sc.choose_output_dir("browse") == sandbox / "picked"
with mock.patch("lego_folder_picker.choose_folder", return_value=None):
    try:
        sc.choose_output_dir("Browse"); assert False
    except SystemExit as e:
        assert "No folder chosen" in str(e)
assert sc.resolve_output_path("a.json", sandbox / "x") == sandbox / "x" / "a.json"
assert sc.resolve_output_path(str(sandbox / "abs.json"), sandbox / "x") == sandbox / "abs.json"
print("--output-dir: path (relative from current folder) or 'browse' (dialog; cancel stops); file names go inside it: OK")

order = sc.LegoOrder(order_number="T1", status="Shipped", order_date="June 1, 2026", total="5.00",
                     item_count_listed=0, url="u")
seen = {}
target = (sandbox / "My Orders").resolve()   # macOS temp: /var -> /private/var
real_out, real_err = sys.stdout, sys.stderr
try:
    with mock.patch.object(sc, "scrape", lambda **kw: seen.update(kw) or [order]), \
         mock.patch.object(sys, "argv", ["x", "--output-dir", str(target)]), contextlib.redirect_stdout(io.StringIO()):
        sc.main()
finally:
    sys.stdout, sys.stderr = real_out, real_err
assert seen["json_path"] == str(target / "lego_orders.json") and seen["csv_path"] == str(target / "lego_orders.csv")
assert (target / "lego_orders.html").is_file()
print("CLI run with --output-dir: JSON/CSV/HTML all saved in that folder (created if needed): OK")

# --- web UI ---------------------------------------------------------------------------
try:
    import lego_orders_webapp as wa
except ImportError:
    print("SKIPPED web UI part: flask not installed"); sys.exit(0)

assert wa.build_argv({"output_dir": "/Users/me/Orders"})[:2] == ["--output-dir", "/Users/me/Orders"]
assert "--output-dir" not in wa.build_argv({"output_dir": "  "}) and "--output-dir" not in wa.build_argv({})
with mock.patch.object(wa, "IN_CONTAINER", True):
    assert "--output-dir" not in wa.build_argv({"output_dir": "/x"})        # Docker: files stay in the volume
print("Web UI: 'Save files to' -> --output-dir (ignored in Docker): OK")

c = wa.app.test_client()
with mock.patch.object(wa, "IN_CONTAINER", False), mock.patch.object(wa.lego_folder_picker, "dialog_available", return_value=True):
    cfg = c.get("/config").get_json()
    assert cfg["folder_option"] and cfg["can_browse"] and cfg["default_output_dir"] == str(wa.WORK_DIR)
    assert cfg["output_dir"] == str(wa.WORK_DIR)                               # nothing remembered yet -> default
    with mock.patch.object(wa.lego_folder_picker, "choose_folder", return_value=sandbox / "chosen") as cf:
        r = c.post("/browse", json={"start": str(sandbox)}).get_json()
        assert r == {"ok": True, "path": str(sandbox / "chosen")} and cf.call_args.kwargs["start"] == str(sandbox)
    with mock.patch.object(wa.lego_folder_picker, "choose_folder", return_value=None):
        assert c.post("/browse", json={}).get_json() == {"ok": False, "cancelled": True}
with mock.patch.object(wa, "IN_CONTAINER", True):
    cfg = c.get("/config").get_json()
    assert not cfg["folder_option"] and not cfg["can_browse"]
    assert c.post("/browse", json={}).status_code == 404
page = c.get("/").get_data(as_text=True)
assert 'id="output_dir"' in page and 'id="btnBrowse"' in page and 'id="btnDefaultDir"' in page
print("Web UI: /config offers the folder + Browse (not in Docker); Browse returns the chosen folder or 'cancelled': OK")

# The chosen folder is remembered (saved when a scrape starts) and used for the download links.
wa.SCRAPER_PATH = Path(__file__).resolve().parent / "fake_scraper.py"
chosen = sandbox / "web out"
with mock.patch.object(wa, "IN_CONTAINER", False):
    assert c.post("/start", json={"output_dir": str(chosen)}).get_json() == {"ok": True}
    for _ in range(100):
        if wa.job.snapshot()["status"] != "running":
            break
        try:
            wa.job.send_enter()
        except RuntimeError:
            pass
        import time; time.sleep(0.1)
    assert json.loads(wa.SETTINGS_PATH.read_text())["output_dir"] == str(chosen)
    assert c.get("/config").get_json()["output_dir"] == str(chosen)
    assert any(f"--output-dir {chosen}" in l for l in wa.job.snapshot()["lines"])
chosen.mkdir(parents=True, exist_ok=True)
(chosen / "lego_orders.csv").write_text("x")
assert wa.job.available_downloads() == {"csv": str(chosen / "lego_orders.csv")}
assert wa.output_base({}) == wa.WORK_DIR and wa.output_base({"output_dir": "sub"}) == wa.WORK_DIR / "sub"
print("Web UI: chosen folder remembered for next time, passed to the scrape, and used for downloads: OK")
print("\nALL OUTPUT-FOLDER TESTS PASSED")
