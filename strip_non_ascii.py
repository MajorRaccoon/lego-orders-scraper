#!/usr/bin/env python3
"""
strip_non_ascii.py

Removes every non-ASCII character (anything with a code point above 127 --
smart quotes, em/en dashes, (TM)/(R) symbols, accented letters, etc.) from
a JSON or CSV text file, leaving everything else untouched.

This works purely at the TEXT level: it does NOT parse and re-serialize
the JSON/CSV, so key order, indentation, quoting style, and line endings
are all preserved exactly as they were -- only the non-ASCII characters
themselves are deleted. After cleaning, it double-checks (for files ending
in .json or .csv) that the result still parses correctly, and warns you if
it doesn't (this would only happen if a non-ASCII character were somehow
load-bearing to the file's syntax, which normal JSON/CSV content never is).

Note: characters are simply deleted, not replaced with anything -- e.g.
"Technic™ Hub" becomes "Technic Hub", and "word – word" (an
en dash with spaces around it) becomes "word  word" (two spaces, since
only the dash itself is removed). Nothing is auto-collapsed or re-spaced.

USAGE
-----
    python strip_non_ascii.py lego_orders.json
        # writes lego_orders.ascii.json alongside the original (which is
        # left untouched)

    python strip_non_ascii.py lego_orders.json --in-place
        # overwrites lego_orders.json directly (a .bak backup of the
        # original is made first)

    python strip_non_ascii.py lego_orders.json -o clean.json
        # writes to a specific output path instead

    python strip_non_ascii.py lego_orders.json lego_orders.csv --in-place
        # clean multiple files in one run
"""

import argparse
import csv
import io
import json
import shutil
from pathlib import Path


def strip_non_ascii(text):
    """Return (cleaned_text, sorted list of the distinct non-ASCII
    characters that were found and removed)."""
    removed = set()
    kept_chars = []
    for ch in text:
        if ord(ch) > 127:
            removed.add(ch)
        else:
            kept_chars.append(ch)
    return "".join(kept_chars), sorted(removed)


def _validate_result(ext, cleaned_text):
    """Best-effort sanity check that the cleaned text is still well-formed
    for its apparent format. Never blocks the write -- only warns, since a
    warning here would mean a non-ASCII character was somehow load-bearing
    to the file's syntax, which shouldn't happen for ordinary JSON/CSV."""
    if ext == ".json":
        try:
            json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            print(f"  WARNING: the cleaned file no longer parses as valid JSON ({e}) -- please check it carefully.")
    elif ext == ".csv":
        try:
            list(csv.reader(io.StringIO(cleaned_text)))
        except csv.Error as e:
            print(f"  WARNING: the cleaned file couldn't be read back as CSV ({e}) -- please check it carefully.")


def process_file(input_path, output_path=None, in_place=False):
    """Clean one file. Returns the path actually written to."""
    input_path = Path(input_path)
    try:
        # newline="" avoids Python translating line endings on read/write,
        # so whatever line endings the original file used are preserved
        # exactly in the output.
        with open(input_path, "r", encoding="utf-8", newline="") as f:
            original_text = f.read()
    except UnicodeDecodeError as e:
        print(f"{input_path}: couldn't read this as UTF-8 text ({e}) -- skipping.")
        return None

    cleaned_text, removed_chars = strip_non_ascii(original_text)
    ext = input_path.suffix.lower()

    if in_place:
        backup_path = input_path.with_suffix(input_path.suffix + ".bak")
        shutil.copy2(input_path, backup_path)
        target_path = input_path
    elif output_path:
        target_path = Path(output_path)
    else:
        target_path = input_path.with_name(f"{input_path.stem}.ascii{input_path.suffix}")

    with open(target_path, "w", encoding="utf-8", newline="") as f:
        f.write(cleaned_text)

    _validate_result(ext, cleaned_text)

    if not removed_chars:
        print(f"{input_path}: no non-ASCII characters found -- wrote an unchanged copy to {target_path}")
        return target_path

    total_removed = len(original_text) - len(cleaned_text)
    preview = " ".join(repr(c) for c in removed_chars[:20])
    more = f", plus {len(removed_chars) - 20} more distinct character(s)" if len(removed_chars) > 20 else ""
    if in_place:
        print(f"{input_path}: removed {total_removed} character(s) ({preview}{more}) -- backup saved to {backup_path}")
    else:
        print(f"{input_path}: removed {total_removed} character(s) ({preview}{more}) -- wrote {target_path}")
    return target_path


def main():
    parser = argparse.ArgumentParser(
        description="Remove all non-ASCII characters from a JSON or CSV file, "
        "leaving everything else (structure, formatting, remaining characters) unchanged."
    )
    parser.add_argument("inputs", nargs="+", help="One or more JSON/CSV (or any text) files to clean.")
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output file path. Only valid with a single input file; default is "
        "'<name>.ascii<ext>' written next to the original.",
    )
    parser.add_argument(
        "--in-place", action="store_true",
        help="Overwrite each input file directly instead of writing a new file "
        "(a .bak backup of the original is made first).",
    )
    args = parser.parse_args()

    if args.output and len(args.inputs) > 1:
        parser.error("-o/--output can only be used with a single input file.")
    if args.output and args.in_place:
        parser.error("-o/--output and --in-place are mutually exclusive.")

    for path in args.inputs:
        process_file(path, output_path=args.output, in_place=args.in_place)


if __name__ == "__main__":
    main()
