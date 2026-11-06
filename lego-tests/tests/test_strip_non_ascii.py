"""strip_non_ascii.py: strip_non_ascii() and process_file()."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import contextlib, io, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, SRC)
from strip_non_ascii import strip_non_ascii, process_file

assert strip_non_ascii("Technic™ Hub é") == ("Technic Hub ", sorted({"™", "é"}))
assert strip_non_ascii("plain") == ("plain", [])
print("strip_non_ascii: removes, reports distinct chars: OK")

tmp = Path(tempfile.mkdtemp())
src = tmp / "a.json"; src.write_text(json.dumps({"n": "Technic™ Hub"}, ensure_ascii=False), encoding="utf-8")
with contextlib.redirect_stdout(io.StringIO()):
    out = process_file(src)
assert out == tmp / "a.ascii.json" and json.loads(out.read_text()) == {"n": "Technic Hub"}
assert "™" in src.read_text(encoding="utf-8")                     # original untouched by default
with contextlib.redirect_stdout(io.StringIO()):
    process_file(src, in_place=True)
assert "™" not in src.read_text(encoding="utf-8") and (tmp / "a.json.bak").exists()
assert "™" in (tmp / "a.json.bak").read_text(encoding="utf-8")
print("process_file: default writes .ascii copy; --in-place edits with .bak backup: OK")

crlf = tmp / "b.csv"; crlf.write_bytes("a,b\r\nx™,y\r\n".encode("utf-8"))
with contextlib.redirect_stdout(io.StringIO()):
    o = process_file(crlf)
assert o.read_bytes() == b"a,b\r\nx,y\r\n"
print("line endings preserved exactly: OK")
print("\nALL STRIP-NON-ASCII TESTS PASSED")
