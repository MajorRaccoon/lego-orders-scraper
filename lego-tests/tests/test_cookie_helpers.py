"""Chrome cookie decryption helpers (macOS/Linux AES-CBC path), PKCS7, 127+ prefix, time conversion."""
import os as _os
SRC = _os.environ.get("LEGO_SRC") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import sys
sys.path.insert(0, SRC)
import lego_orders_scraper as sc

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:  # e.g. the Windows on ARM build, which can't install cryptography
    for call in (lambda: sc._linux_derive_key(), lambda: sc.load_chrome_cookies_for_domain(".", "lego.com"),
                 lambda: sc._decrypt_cookie_value(b"v10" + b"x" * 16, b"k" * 16, "Linux")):
        try:
            call(); assert False
        except RuntimeError as e:
            assert "needs the 'cryptography' package" in str(e), e
    assert sc._decrypt_cookie_value(b"", b"k", "Linux") == "" and sc._decrypt_cookie_value(b"xyzabc", b"k", "Linux") == ""
    assert sc._pkcs7_unpad(b"abc" + b"\x05" * 5) == b"abc" and sc._chrome_time_to_unix(0) == -1
    print("cryptography not installed: --cookie-source fails with a clear message; other helpers still work: OK")
    print("\nALL COOKIE HELPER TESTS PASSED (without cryptography)")
    sys.exit(0)

key = sc._linux_derive_key()
assert len(key) == 16 and key == sc._linux_derive_key()

def encrypt(plain: bytes, prefix=b"v10", k=key):
    pad = 16 - len(plain) % 16
    enc = Cipher(algorithms.AES(k), modes.CBC(b" " * 16)).encryptor()
    return prefix + enc.update(plain + bytes([pad]) * pad) + enc.finalize()

assert sc._decrypt_cookie_value(encrypt(b"secretvalue"), key, "Linux") == "secretvalue"
print("v10 cookie decrypts: OK")
# the real prefix is an opaque hash (not valid UTF-8), which is what makes the fallback detectable
assert sc._decrypt_cookie_value(encrypt(b"\xff" * 32 + b"newvalue"), key, "Linux") == "newvalue"
print("Chrome 127+ 32-byte prefix stripped: OK")
assert sc._decrypt_cookie_value(b"", key, "Linux") == ""
assert sc._decrypt_cookie_value(b"xyzabc", key, "Linux") == ""
print("empty / unencrypted -> '': OK")
try: sc._decrypt_cookie_value(encrypt(b"x", prefix=b"v11"), key, "Linux"); assert False
except RuntimeError: pass
print("Linux v11 (keyring) raises a clear error: OK")
try: sc._decrypt_cookie_value(encrypt(b"secretvalue"), b"W" * 16, "Linux"); assert False
except ValueError: pass
print("wrong key -> ValueError, never silent garbage: OK")

assert sc._pkcs7_unpad(b"abc" + b"\x05" * 5) == b"abc"
for bad in (b"", b"abc\x00", b"abc\x04\x04\x04\x05", b"a" * 15 + b"\x11"):
    try: sc._pkcs7_unpad(bad); assert False, bad
    except ValueError: pass
print("PKCS7 unpad: valid ok, invalid padding rejected: OK")

assert sc._chrome_time_to_unix(0) == -1 and sc._chrome_time_to_unix(None) == -1
assert sc._chrome_time_to_unix((11644473600 + 1000) * 1_000_000) == 1000
print("Chrome timestamp -> unix; 0 = session cookie: OK")
print("\nALL COOKIE HELPER TESTS PASSED")
