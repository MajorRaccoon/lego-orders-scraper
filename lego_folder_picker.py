#!/usr/bin/env python3
"""
lego_folder_picker.py

Opens the operating system's own "choose a folder" dialog and returns the
folder the user picked. Used by:
  - lego_orders_scraper.py --output-dir browse   (command line)
  - lego_orders_webapp.py's "Browse..." button   (web UI, and the Mac/Windows apps
                                                  built on it -- the web server runs
                                                  on your own computer, so the dialog
                                                  appears on your screen)

Standard library only (no Playwright/Flask needed). How it shows the dialog:
  - macOS:   AppleScript "choose folder" (via osascript)
  - Windows: the standard folder dialog (System.Windows.Forms, via PowerShell)
  - Linux:   zenity, if installed
Anything else (e.g. inside Docker): no dialog available -- folder_dialog_command()
returns None and choose_folder() returns None.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_PROMPT = "Choose where to save the LEGO order files"


def _applescript_quote(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _powershell_quote(s):
    return "'" + str(s).replace("'", "''") + "'"


# Windows won't let a background process (our web server) put its window in front
# of the browser. Front() gets around that: holding Alt down (a synthetic key press
# lifts Windows' "foreground lock") and briefly joining the foreground window's input
# thread, it makes the window always-on-top and gives it the focus. FindDialog() finds
# the folder dialog once it's open, so Front() can be applied to the dialog itself.
_WIN_FRONT_CS = (
    '[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); '
    '[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p); '
    '[DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId(); '
    '[DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach); '
    '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); '
    '[DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h); '
    '[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags); '
    '[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra); '
    '[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h); '
    '[DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n); '
    "public delegate bool EnumProc(IntPtr h, IntPtr l); "
    '[DllImport("user32.dll")] public static extern bool EnumThreadWindows(uint thread, EnumProc cb, IntPtr l); '
    "public static IntPtr FindDialog() { "
    "IntPtr found = IntPtr.Zero; "
    "EnumThreadWindows(GetCurrentThreadId(), delegate(IntPtr h, IntPtr l) { "
    "System.Text.StringBuilder c = new System.Text.StringBuilder(64); GetClassName(h, c, 64); "
    'if (c.ToString() == "#32770" && IsWindowVisible(h)) { found = h; return false; } '
    "return true; }, IntPtr.Zero); "
    "return found; } "
    "public static bool Front(IntPtr h) { "
    "keybd_event(0x12, 0, 0, UIntPtr.Zero); "  # Alt down
    "uint fg = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero); "
    "uint me = GetCurrentThreadId(); "
    "bool joined = fg != 0 && fg != me && AttachThreadInput(me, fg, true); "
    "SetWindowPos(h, new IntPtr(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040); "  # HWND_TOPMOST, no move/size, show
    "BringWindowToTop(h); "
    "bool ok = SetForegroundWindow(h); "
    "if (joined) { AttachThreadInput(me, fg, false); } "
    "keybd_event(0x12, 0, 2, UIntPtr.Zero); "  # Alt up (lands on our window, so the browser never sees an Alt press)
    "return ok || GetForegroundWindow() == h; }"
)


def folder_dialog_command(start=None, prompt=DEFAULT_PROMPT, system=None):
    """The command that shows a folder dialog on this OS (opening at `start`
    if it's an existing folder), or None when no dialog is available."""
    system = system or platform.system()
    start = str(start) if start and Path(start).is_dir() else None
    if system == "Darwin":
        script = f"POSIX path of (choose folder with prompt {_applescript_quote(prompt)}"
        if start:
            script += f" default location (POSIX file {_applescript_quote(start)})"
        return ["osascript", "-e", script + ")"]
    if system == "Windows":
        ps = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$d.Description = {_powershell_quote(prompt)}; "
            "$d.ShowNewFolderButton = $true; "
            + (f"$d.SelectedPath = {_powershell_quote(start)}; " if start else "")
            # A tiny invisible always-on-top window, shown and pushed to the front, owns the
            # dialog (so the dialog opens centered on screen). Once the dialog itself is open,
            # a timer finds it and pushes it to the front too. "front:..." goes to stderr so
            # choose_folder() can log it if Windows refused.
            + "$o = New-Object System.Windows.Forms.Form -Property @{TopMost = $true; "
            "ShowInTaskbar = $false; FormBorderStyle = 'None'; Opacity = 0; "
            "StartPosition = 'CenterScreen'; Size = New-Object System.Drawing.Size(1, 1)}; "
            "$o.Show(); "
            "$t = New-Object System.Windows.Forms.Timer -Property @{Interval = 100}; "
            f"try {{ Add-Type -Namespace LegoPick -Name Win -MemberDefinition {_powershell_quote(_WIN_FRONT_CS)}; "
            "[void][LegoPick.Win]::Front($o.Handle); "
            "$t.add_Tick({ $h = [LegoPick.Win]::FindDialog(); "
            "if ($h -ne [IntPtr]::Zero) { $t.Stop(); [Console]::Error.Write('front:' + [LegoPick.Win]::Front($h)) } }); "
            "$t.Start() } catch { [Console]::Error.Write('front:error ' + $_) }; "
            "$o.Activate(); "
            "$ok = $d.ShowDialog($o) -eq [System.Windows.Forms.DialogResult]::OK; "
            "$t.Stop(); $o.Close(); "
            "if ($ok) { [Console]::Out.Write($d.SelectedPath) }"
        )
        return ["powershell", "-NoProfile", "-STA", "-Command", ps]
    if shutil.which("zenity"):
        cmd = ["zenity", "--file-selection", "--directory", "--title", prompt]
        if start:
            cmd.append(f"--filename={start.rstrip('/')}/")
        return cmd
    return None


def dialog_available():
    """True when this computer can show a folder dialog (not inside Docker)."""
    if os.path.exists("/.dockerenv"):
        return False
    return folder_dialog_command() is not None


def choose_folder(start=None, prompt=DEFAULT_PROMPT):
    """Show the dialog; return the chosen folder as a Path, or None if the user
    cancelled or no dialog is available. Blocks until the dialog closes."""
    cmd = folder_dialog_command(start, prompt)
    if cmd is None:
        return None
    kwargs = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    if platform.system() == "Windows":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW: no flashing console
    try:
        result = subprocess.run(cmd, **kwargs)
    except (OSError, subprocess.TimeoutExpired):
        return None
    note = (result.stderr or "").strip()
    if note and note != "front:True":
        # e.g. Windows refused to bring the dialog in front of the browser
        print(f"Folder dialog note: {note[:300]}", file=sys.stderr, flush=True)
    path = (result.stdout or "").strip()
    if result.returncode != 0 or not path:
        return None  # cancelled
    return Path(path)


if __name__ == "__main__":
    print(choose_folder() or "(cancelled)")
