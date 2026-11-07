# LEGO Mail Orders — read your LEGO orders from Apple Mail

A native Mac app (Swift/SwiftUI) that finds your LEGO Shop emails in **Apple Mail** and turns them into an order history. It reads order confirmations, shipping and delivery notices, cancellations and refunds, and saves the same kind of files as the LEGO.com scraper.

- **No login, no browser.** It reads the emails already on your Mac. Nothing is sent anywhere.
- **Read-only.** It never changes, moves or marks your emails.
- **Works offline,** and with Mail closed.

It lives in the same Swift package as the LEGO.com app ([README-swift.md](README-swift.md)) and shares its code for the order records and the JSON, CSV and HTML files.

## Build it (once)

Needs a Mac with Xcode (or the command-line tools: `xcode-select --install`) and macOS 13 or newer.

```bash
cd mac-swift
./build_mail_app.sh
```

This runs the tests, then builds `mac-swift/dist/LEGO Mail Orders.app` (Apple Silicon and Intel) and a zip of it. Drag **the `.app`** to Applications.

## Give it Full Disk Access (once)

macOS protects Mail's folder (`~/Library/Mail`). Apps can read it only with **Full Disk Access**:

1. Open the app. It shows **Full Disk Access needed**. Click **Open Privacy Settings**.
2. Turn on **LEGO Mail Orders** in the list. If it isn't listed, click **+** and choose it in Applications.
3. Quit the app and open it again.

**After rebuilding the app**, macOS may treat it as a new app. If the warning comes back, remove it from the list with **−**, add it again, and reopen it.

Don't want to grant that? Export the emails instead: in Mail, select your LEGO emails, then **File → Save As…** (or drag them into a Finder folder) to get `.eml` files, or select a mailbox and use **Mailbox → Export Mailbox…** to get an `.mbox`. Then click **Read emails from → Browse…** and choose that folder. Exported files need no special permission.

## Use it

1. Click **Start**.
2. The log shows how many emails were checked and lists each order found.
3. Click **Open HTML report** or **Show files in Finder**.

| Option | What it does |
|---|---|
| **Read emails from** | Apple Mail's folder (default), or a folder of exported `.eml` / `.mbox` files. |
| **Save files to** | Where the files go. Default: `~/Library/Application Support/LEGO Order Scraper/`. |
| **Only orders placed on or after** | Skip older orders (and older emails, which makes it faster). |
| **Also make an HTML report** | Writes `lego_mail_orders.html`. |
| **Leave out tracking numbers** | Tracking numbers are left blank in every file. |
| **Start fresh** | Normally, orders found by an earlier run are kept even if their emails have since been deleted. This forgets them. |
| **Save matched emails for troubleshooting** | Saves every LEGO order email as a text file, with what the app read from it. See below. |

Each run reads all the mail again, so there's nothing to resume. A mailbox with tens of thousands of emails takes a few seconds to a minute, because the app looks at each email's sender and subject first and reads only the LEGO ones in full.

## What it saves

| File | Contents |
|---|---|
| `lego_mail_orders.json` | One object per order, with an `items` list. Same format as `lego_orders.json`. |
| `lego_mail_orders.csv` | One row per item. Same columns as `lego_orders.csv`. |
| `lego_mail_orders.html` | Report with every order and monthly spending charts. |
| `~/Library/Logs/LEGO Mail Orders.log` | A record of every run. |

These names differ from the LEGO.com scraper's (`lego_orders.*`), so the two apps never overwrite each other, even in the same folder.

How one order is built from its emails:

- **Items, prices, subtotal, delivery, tax, discounts and total** come from the order confirmation.
- **Status** comes from the latest email: Processing (confirmation only), Shipped, Delivered, Cancelled, Refunded, Returned or Backordered.
- **Item status and tracking number:** a shipping email that lists items updates just those items, so split shipments come out right. One that lists no items updates them all. A cancellation that lists only some items cancels only those items, not the order.
- **Order date:** printed in the email, or else the day the confirmation arrived.
- The same email in two mailboxes (for example Gmail's Inbox and All Mail) is counted once.
- A forwarded copy of a LEGO email is read too.

## If orders come out wrong

LEGO doesn't publish the layout of its emails, and it changes from time to time. The app looks for labels such as "Order Number", "Item:", "Qty", "Subtotal" and "Tracking number" anywhere in an email, so it handles many layouts. It can still miss an item or a price in a layout it hasn't seen. To help fix it:

1. Turn on **Save matched emails for troubleshooting** and click **Start**.
2. Click **Show saved email text**. Each file is named `date_order-number_kind_N.txt`. It starts with **What the app read** (items, prices, status), followed by the email's text.
3. Send the files for the emails that came out wrong. **They contain your name, address and order details**, so blank those out or share only with someone you trust.

The rules are in `Sources/LegoMail/LegoEmailParser.swift`. Each one has unit tests in `Tests/LegoMailTests/`.

## Command line

The same import without the window. Handy for scripting or testing:

```bash
cd mac-swift
swift run lego-mail --help
swift run lego-mail                                   # read ~/Library/Mail
swift run lego-mail --mail-dir ~/Desktop/lego-emails  # read exported .eml / .mbox files
swift run lego-mail --mail-dir sample-mail --output-dir /tmp/lego-test   # the made-up sample mailbox
```

To read `~/Library/Mail` from Terminal, give **Terminal** Full Disk Access (same steps as above).

## For developers

```
mac-swift/
  Sources/LegoMail/            no UI: reads the mail files and builds the orders
    MailMessage.swift          .emlx / .eml / .mbox files, headers, MIME parts, encodings
    HTMLText.swift             HTML email -> one line per table cell / paragraph
    LegoEmailParser.swift      is it a LEGO order email? order number, kind, items, summary, tracking
    MailOrders.swift           combines an order's emails into one LegoOrder
    MailScanner.swift          walks the mail folder, skips non-LEGO mail by its headers, de-duplicates
    MailRun.swift              one full run: scan, build, write JSON / CSV / HTML
  Sources/LegoMailOrdersApp/   the SwiftUI window
  Sources/lego-mail/           command-line version
  Tests/LegoMailTests/         unit tests + an end-to-end run on sample-mail/
  sample-mail/                 made-up LEGO emails in Mail's formats (make_sample_mail.py writes them)
  build_mail_app.sh            builds dist/LEGO Mail Orders.app
```

- Run the tests: `cd mac-swift && swift test`
- Bump `legoMailVersion` in `Sources/LegoMail/Version.swift` with every change.
- The GitHub Actions workflow **macOS app** also builds this app, checks `lego-mail` against `sample-mail/`, and attaches the zip as **LEGO-Mail-Orders-macOS**.
