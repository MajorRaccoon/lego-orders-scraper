#!/usr/bin/env python3
"""Writes made-up LEGO Shop emails into sample-mail/ for the LegoMail tests and the CI check.

The emails are invented (no real order, address or person) and cover the layouts and
encodings the Mail reader must handle:
  Mail/V10/.../Messages/*.emlx   Apple Mail's own format (byte count + message + plist)
  exported/LEGO.mbox/mbox        a mailbox exported from Mail (several messages in one file)
  exported/forwarded.eml         a single email saved from Mail (here: a forwarded copy)

Run it again after changing an email:  python3 sample-mail/make_sample_mail.py
"""
import base64
import quopri
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORE = HERE / "Mail" / "V10" / "00000000-SAMPLE-ACCOUNT" / "INBOX.mbox" / "11111111-SAMPLE" / "Data" / "Messages"
ALL_MAIL = HERE / "Mail" / "V10" / "00000000-SAMPLE-ACCOUNT" / "All Mail.mbox" / "22222222-SAMPLE" / "Data" / "Messages"
EXPORTED = HERE / "exported"

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>flags</key>
\t<integer>8590195713</integer>
</dict>
</plist>
"""


def qp(text: str) -> str:
    return quopri.encodestring(text.encode("utf-8")).decode("ascii")


def b64(text: str) -> str:
    raw = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return "\n".join(raw[i:i + 76] for i in range(0, len(raw), 76))


def write_emlx(path: Path, message: str) -> None:
    data = message.replace("\n", "\r\n").encode("utf-8")  # Mail stores CRLF line ends
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(str(len(data)).encode() + b"\n" + data + PLIST.encode())


CONFIRMATION_HTML = """<html><head><style>.hide{display:none}</style><title>Your order</title></head>
<body><table width="600">
<tr><td><h1>Thank you for your order!</h1></td></tr>
<tr><td>Order Number: T100000001</td></tr>
<tr><td>Order Date: September 7, 2026</td></tr>
</table>
<table>
<tr><td><img src="https://example.invalid/titanic.png" alt="Titanic"></td><td>LEGO&reg; Icons Titanic</td></tr>
<tr><td>Item: 10294</td><td>Qty: 1</td><td>$679.99</td></tr>
<tr><td>LEGO&reg; Technic&trade; Hub</td></tr>
<tr><td>Item: 88012</td><td>Qty: 2</td><td><s>$59.99</s> $49.99</td><td>$99.98</td></tr>
<tr><td>Brick Calendar</td></tr>
<tr><td>Item: 5008000</td><td>Qty: 1</td><td>FREE</td></tr>
</table>
<table>
<tr><td>Subtotal</td><td>$779.97</td></tr>
<tr><td>Shipping</td><td>FREE</td></tr>
<tr><td>Tax</td><td>$48.75</td></tr>
<tr><td>LEGO&reg; Insiders discount</td><td>-$20.00</td></tr>
<tr><td>Order Total</td><td>$808.72</td></tr>
</table>
<p>Questions? Visit LEGO.com/service &amp; we'll help.</p>
</body></html>
"""

CONFIRMATION_TEXT = """Thank you for your order!
Order Number: T100000001
(View this email in a browser to see your items.)
"""

CONFIRMATION = f"""Return-Path: <bounce@e.lego.com>
From: "LEGO Shop" <noreply@e.lego.com>
To: Sample Customer <customer@example.invalid>
Subject: =?UTF-8?Q?Your_LEGO=C2=AE_Shop_order_confirmation_T100000001?=
Date: Mon, 7 Sep 2026 14:05:00 +0000
Message-ID: <confirm-T100000001@e.lego.com>
MIME-Version: 1.0
Content-Type: multipart/related; boundary="REL"

--REL
Content-Type: multipart/alternative;
 boundary="ALT"

--ALT
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

{CONFIRMATION_TEXT}
--ALT
Content-Type: text/html; charset="utf-8"
Content-Transfer-Encoding: quoted-printable

{qp(CONFIRMATION_HTML)}
--ALT--

--REL
Content-Type: image/png; name="logo.png"
Content-Transfer-Encoding: base64
Content-Disposition: inline; filename="logo.png"

iVBORw0KGgo=
--REL--
"""

SHIPPED_HTML = """<html><body>
<p>Good news! Your order is on its way.</p>
<p>Order Number: T100000001</p>
<table><tr><td>Tracking number:</td><td>1Z999AA10123456784</td></tr></table>
<table><tr><td>Items in this shipment</td></tr>
<tr><td>LEGO&reg; Icons Titanic</td></tr><tr><td>Item: 10294</td><td>Qty: 1</td></tr></table>
</body></html>
"""

SHIPPED = f"""From: LEGO Shop <noreply@e.lego.com>
To: customer@example.invalid
Subject: Your LEGO order T100000001 is on its way!
Date: Thu, 10 Sep 2026 09:30:00 -0400 (EDT)
Message-ID: <ship-T100000001@e.lego.com>
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8
Content-Transfer-Encoding: base64

{b64(SHIPPED_HTML)}
"""

DELIVERED = """From: LEGO Shop <noreply@e.lego.com>
To: customer@example.invalid
Subject: Your LEGO order has been delivered
Date: Mon, 14 Sep 2026 16:00:00 -0400
Message-ID: <delivered-T100000001@e.lego.com>
MIME-Version: 1.0
Content-Type: text/plain; charset=us-ascii

Your package was delivered today.
Order number: T100000001
"""

NEWSLETTER = """From: LEGO <news@e.lego.com>
To: customer@example.invalid
Subject: Pre-order the newest LEGO Icons set today
Date: Tue, 1 Sep 2026 12:00:00 +0000
Message-ID: <news-2026-09@e.lego.com>
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

Be the first to build it. Shop now at LEGO.com.
"""

OTHER = """From: Someone Else <friend@example.invalid>
To: customer@example.invalid
Subject: Dinner on Friday?
Date: Wed, 2 Sep 2026 18:00:00 +0000
Message-ID: <dinner@example.invalid>

Are you free?
"""

MBOX_CONFIRMATION = """From: LEGO Shop <shop@e.lego.com>
To: customer@example.invalid
Subject: Thank you for your LEGO order
Date: Fri, 2 Oct 2026 20:15:00 +0000
Message-ID: <confirm-T100000002@e.lego.com>
MIME-Version: 1.0
Content-Type: text/plain; charset=iso-8859-1
Content-Transfer-Encoding: quoted-printable

Thanks for shopping with LEGO=AE!

Order number: T100000002
Order placed: 10/02/2026

ITEM                         QTY   PRICE
LEGO Botanicals Orchid
Item #10311
Quantity: 1
Price: $49.99

Pick a Brick 2x4 Brick Red
Element ID: 300121
Quantity: 10
Price: $0.25
Total: $2.50

Subtotal: $52.49
Shipping & Handling: $5.95
Sales Tax: $3.68
Total: $62.12
"""

MBOX_PARTIAL_CANCEL = """From: LEGO Shop <shop@e.lego.com>
To: customer@example.invalid
Subject: Part of your order T100000002 has been cancelled
Date: Sat, 3 Oct 2026 10:00:00 +0000
Message-ID: <cancel-T100000002@e.lego.com>
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

We're sorry: this item is out of stock and was cancelled.
>From now on you can check stock on LEGO.com.

Pick a Brick 2x4 Brick Red
Element ID: 300121
Quantity: 10
"""

MBOX_OLD = """From: LEGO Shop <shop@e.lego.com>
To: customer@example.invalid
Subject: Your LEGO Shop order confirmation T099999999
Date: Sun, 5 Mar 2023 10:00:00 +0000
Message-ID: <confirm-T099999999@e.lego.com>
Content-Type: text/plain; charset=utf-8

Order Number: T099999999
Order Date: March 5, 2023
LEGO Creator Corner Garage
Item: 10264
Qty: 1
$199.99
Total: $213.99
"""

FORWARDED_TEXT = """Look what's coming!

---------- Forwarded message ---------
From: LEGO Shop <noreply@e.lego.com>
Subject: Your LEGO order has shipped

Order Number: T100000003
Tracking #: 9400111899223344556677
LEGO Ideas Tree House
Item: 21318
Qty: 1
"""

FORWARDED = f"""From: Sample Customer <customer@example.invalid>
To: family@example.invalid
Subject: =?utf-8?B?{base64.b64encode("Fwd: Your LEGO® order has shipped".encode()).decode()}?=
Date: Mon, 26 Oct 2026 08:00:00 +0000
Message-ID: <fwd-T100000003@example.invalid>
MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: base64

{b64(FORWARDED_TEXT)}
"""


def main() -> None:
    write_emlx(STORE / "1001.emlx", CONFIRMATION)
    write_emlx(STORE / "1002.emlx", SHIPPED)
    write_emlx(STORE / "1003.emlx", DELIVERED)
    write_emlx(STORE / "1004.emlx", NEWSLETTER)
    write_emlx(STORE / "1005.emlx", OTHER)
    # The same confirmation again, as Gmail's "All Mail" copy: must be read only once.
    write_emlx(ALL_MAIL / "2001.partial.emlx", CONFIRMATION)

    EXPORTED.joinpath("LEGO.mbox").mkdir(parents=True, exist_ok=True)
    mbox = ""
    for msg, stamp in [(MBOX_OLD, "Sun Mar  5 10:00:00 2023"), (MBOX_CONFIRMATION, "Fri Oct  2 20:15:00 2026"),
                       (MBOX_PARTIAL_CANCEL, "Sat Oct  3 10:00:00 2026")]:
        mbox += f"From shop@e.lego.com {stamp}\n{msg}\n"
    (EXPORTED / "LEGO.mbox" / "mbox").write_text(mbox, encoding="utf-8")
    (EXPORTED / "forwarded.eml").write_text(FORWARDED, encoding="utf-8")
    print(f"Wrote sample emails in {HERE}")


if __name__ == "__main__":
    main()
