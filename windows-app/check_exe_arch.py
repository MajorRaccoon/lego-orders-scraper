#!/usr/bin/env python3
"""Check that the built Windows app's executables are for the expected CPU.

    python check_exe_arch.py x64|arm64 "dist/LEGO Order Scraper"

Reads the CPU type straight from each .exe/.dll file header (the "machine" field
of the PE header) for the app, its Python, and Playwright's bundled Node.js driver.
Exits 1 if any of them is for a different CPU. Used by the GitHub Actions build.
"""
import struct
import sys
from pathlib import Path

MACHINES = {0x8664: "x64", 0xAA64: "arm64", 0x014C: "x86"}


def machine_of(path):
    data = Path(path).read_bytes()[:4096]
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"{path} is not a Windows executable")
    return MACHINES.get(struct.unpack_from("<H", data, pe + 4)[0], "unknown")


def main(expected, app_dir):
    app_dir = Path(app_dir)
    files = [app_dir / "LEGO Order Scraper.exe"]
    files += sorted((app_dir / "_internal").glob("python3*.dll"))
    files += sorted((app_dir / "_internal").rglob("node.exe"))
    bad = 0
    for f in files:
        got = machine_of(f)
        ok = got == expected
        bad += not ok
        print(f"{'OK  ' if ok else 'BAD '} {got:6} {f.relative_to(app_dir)}")
    if len(files) < 3:
        print("BAD: expected the app .exe, a python3*.dll and node.exe")
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
