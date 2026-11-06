# LEGO Order Scraper — native Mac app (Swift)

A native macOS app written in Swift/SwiftUI. It replaces the Python-based Mac app in `mac-app/`.

- **No Python, no Chromium download.** The built-in browser uses WebKit, the same engine as Safari.
- **Log in inside the app.** LEGO.com appears on the right side of the window. Your login is remembered between runs.
- **Same results as the command line.** It writes the same `lego_orders.json`, `lego_order_items.csv` and `lego_orders.html`, byte for byte. You can switch between versions, and a run in one picks up where the other left off.

## Build it (once)

Needs a Mac with Xcode (or the Xcode command-line tools: `xcode-select --install`) and macOS 13 or newer.

```bash
cd mac-swift
./build_app.sh
```

This runs the tests, then builds `mac-swift/dist/LEGO Order Scraper.app` (works on Apple Silicon and Intel) and a zip of it. Drag **the `.app`** to Applications.

## Use it

1. Double-click **LEGO Order Scraper**.
2. Pick your options on the left. The defaults are orders since 02/01/2024, with an HTML report.
3. Click **Start**.
4. **First time only:** log in to LEGO.com in the browser on the right. The app continues by itself once your order list appears, or you can click **"I've logged in, continue"**.
5. Watch progress in the log at the bottom. When it's done, click **Open HTML report** or **Show files in Finder**.

**Stop** finishes the current order, saves and stops. Clicking it again stops right away. Progress is saved after every order, so **Start** picks up where it left off.

| What | Where |
|---|---|
| Your orders (JSON, CSV, HTML) | `~/Library/Application Support/LEGO Order Scraper/` |
| Log | `~/Library/Logs/LEGO Order Scraper.log` |
| Saved LEGO login | WebKit's storage for this app. Remove it with **Forget saved LEGO login**. |

Options that match the command line: the since-date box is `--since-date`, **Max orders** is `--max-orders`, **Refetch everything** is `--fresh`, **Leave out tracking numbers** is `--no-tracking`, and **Advanced** has the three wait times (`--delay`, `--load-more-delay`, `--load-more-final-wait`). `--cookie-source` isn't needed because you log in inside the app.

## If orders come out wrong

The app reads the same page text as the Python scraper, but through Safari's engine instead of Chrome's, so a page could occasionally read slightly differently. To help fix it:

1. Turn on **Advanced → Save page text for troubleshooting**.
2. Run again.
3. Send the files from the `page-text` folder inside the data folder. They contain your order details, so share them only with someone you trust.

## Giving it to someone else

The app isn't notarized (that needs a paid Apple developer account). The first time, the other person needs to right-click the app, choose **Open**, then **Open** again. Each person logs in with their own LEGO account.

## For developers

```
mac-swift/
  Package.swift
  Sources/LegoCore/            parsing, merge/dedupe, JSON/CSV/HTML writers, scraping flow (no UI)
  Sources/LegoOrderScraperApp/ SwiftUI window + WebKitPage (drives WKWebView for the scraper)
  Sources/lego-parity/         small CLI used by lego-tests to compare Swift output with Python's
  Tests/LegoCoreTests/         unit tests (ports of the Python tests + full runs against a fake LEGO.com)
  build_app.sh                 tests, universal release build, .app bundle, icon, ad-hoc signing, zip
```

- Run the unit tests: `cd mac-swift && swift test`
- Check that Swift and Python agree byte for byte: `python3 lego-tests/tests/test_swift_parity.py` (also part of `lego-tests/run_tests.py`).
- Run from source without bundling: `swift run LegoOrderScraperApp`
- Self-check without clicking anything: `LEGO_SELFCHECK=/tmp/check "dist/LEGO Order Scraper.app/Contents/MacOS/LEGO Order Scraper"`. It loads LEGO.com, saves `window.png`, `page.png`, `state.txt`, `main-text.txt` and `main.html` into that folder, then quits. Add `LEGO_SELFCHECK_URL=<url>` to load a specific page, such as one order's detail page, instead of My Orders.
- If LEGO changes its pages, fix the parser in **both** `lego_orders_scraper.py` and `Sources/LegoCore/Parsing.swift`. The parity test catches any mismatch.
- Bump `legoSwiftVersion` in `Sources/LegoCore/Models.swift` on every change.
