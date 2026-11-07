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
    '[DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i); '
    "[StructLayout(LayoutKind.Sequential)] public struct FLASHWINFO "
    "{ public uint cbSize; public IntPtr hwnd; public uint dwFlags; public uint uCount; public uint dwTimeout; } "
    '[DllImport("user32.dll")] public static extern bool FlashWindowEx(ref FLASHWINFO f); '
    # Flash a window's taskbar button until it's clicked (FLASHW_ALL | FLASHW_TIMERNOFG).
    "public static void Flash(IntPtr h) { FLASHWINFO f = new FLASHWINFO(); "
    "f.cbSize = (uint)Marshal.SizeOf(f); f.hwnd = h; f.dwFlags = 3 | 12; FlashWindowEx(ref f); } "
    "static string Name(IntPtr h) { System.Text.StringBuilder c = new System.Text.StringBuilder(64); "
    "GetClassName(h, c, 64); return c.ToString(); } "
    # Returns "focused", "on-top-not-focused (focus: <class>)" or "not-on-top (...)".
    "public static string Front(IntPtr h) { "
    "SetWindowPos(h, new IntPtr(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040); "  # HWND_TOPMOST, no move/size, show
    "if (GetForegroundWindow() != h) { "
    "keybd_event(0x12, 0, 0, UIntPtr.Zero); "  # Alt down: lifts Windows' foreground lock
    "System.Threading.Thread.Sleep(30); "
    "uint fg = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero); "
    "uint me = GetCurrentThreadId(); "
    "bool joined = fg != 0 && fg != me && AttachThreadInput(me, fg, true); "
    "BringWindowToTop(h); SetForegroundWindow(h); "
    "if (joined) { AttachThreadInput(me, fg, false); } "
    "keybd_event(0x12, 0, 2, UIntPtr.Zero); "  # Alt up
    "System.Threading.Thread.Sleep(50); } "
    "IntPtr now = GetForegroundWindow(); "
    'if (now == h) { return "focused"; } '
    'string where = " (focus: " + Name(now) + ")"; '
    'return ((GetWindowLong(h, -20) & 8) != 0 ? "on-top-not-focused" : "not-on-top") + where; }'
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
            "Add-Type -AssemblyName System.Windows.Forms, System.Drawing; "
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
            f"$d.Description = {_powershell_quote(prompt)}; "
            "$d.ShowNewFolderButton = $true; "
            + (f"$d.SelectedPath = {_powershell_quote(start)}; " if start else "")
            # A tiny invisible always-on-top window owns the dialog (so the dialog opens
            # centered on screen) and gives it a taskbar button. Once the dialog is open, a
            # timer pushes it to the front, retrying a few times; if Windows still won't give
            # it the focus, the taskbar button flashes. The result ("front:...") goes to
            # stderr, and choose_folder() logs it.
            + "$o = New-Object System.Windows.Forms.Form -Property @{TopMost = $true; "
            f"Text = {_powershell_quote(prompt)}; ShowInTaskbar = $true; FormBorderStyle = 'None'; Opacity = 0; "
            "StartPosition = 'CenterScreen'; Size = New-Object System.Drawing.Size(1, 1)}; "
            "$o.Show(); "
            "$t = New-Object System.Windows.Forms.Timer -Property @{Interval = 150}; "
            "$script:tries = 0; "
            f"try {{ Add-Type -Namespace LegoPick -Name Win -MemberDefinition {_powershell_quote(_WIN_FRONT_CS)}; "
            "[void][LegoPick.Win]::Front($o.Handle); "
            "$t.add_Tick({ $h = [LegoPick.Win]::FindDialog(); "
            "if ($h -ne [IntPtr]::Zero) { $script:tries++; $r = [LegoPick.Win]::Front($h); "
            "if ($r -eq 'focused' -or $script:tries -ge 6) { $t.Stop(); "
            "if ($r -ne 'focused') { [LegoPick.Win]::Flash($o.Handle) }; "
            "[Console]::Error.Write('front:' + $r + ' after ' + $script:tries + ' tries') } } }); "
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
    if note:
        # Windows: whether the dialog came to the front ("front:focused after 1 tries",
        # or why not) -- shows in the app's console window and log, for troubleshooting.
        print(f"Folder dialog: {note[:300]}", file=sys.stderr, flush=True)
    path = (result.stdout or "").strip()
    if result.returncode != 0 or not path:
        return None  # cancelled
    return Path(path)


if __name__ == "__main__":
    print(choose_folder() or "(cancelled)")
