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
from pathlib import Path

DEFAULT_PROMPT = "Choose where to save the LEGO order files"


def _applescript_quote(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _powershell_quote(s):
    return "'" + str(s).replace("'", "''") + "'"


# Windows won't let a background process (our web server) put its window in front
# of the browser. Joining the foreground window's input thread for a moment lifts that
# restriction, so the folder dialog opens on top instead of behind the browser.
_WIN_FRONT_CS = (
    '[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); '
    '[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p); '
    '[DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId(); '
    '[DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach); '
    '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); '
    '[DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h); '
    "public static void Front(IntPtr h) { "
    "uint fg = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero); "
    "uint me = GetCurrentThreadId(); "
    "bool joined = fg != 0 && fg != me && AttachThreadInput(me, fg, true); "
    "BringWindowToTop(h); SetForegroundWindow(h); "
    "if (joined) { AttachThreadInput(me, fg, false); } }"
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
            # dialog so the dialog opens on top of the browser (and centered on screen).
            + "$o = New-Object System.Windows.Forms.Form -Property @{TopMost = $true; "
            "ShowInTaskbar = $false; FormBorderStyle = 'None'; Opacity = 0; "
            "StartPosition = 'CenterScreen'; Size = New-Object System.Drawing.Size(1, 1)}; "
            "$o.Show(); "
            f"try {{ Add-Type -Namespace LegoPick -Name Win -MemberDefinition {_powershell_quote(_WIN_FRONT_CS)}; "
            "[LegoPick.Win]::Front($o.Handle) } catch { }; "
            "$o.Activate(); "
            "$ok = $d.ShowDialog($o) -eq [System.Windows.Forms.DialogResult]::OK; "
            "$o.Close(); "
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
    path = (result.stdout or "").strip()
    if result.returncode != 0 or not path:
        return None  # cancelled
    return Path(path)


if __name__ == "__main__":
    print(choose_folder() or "(cancelled)")
