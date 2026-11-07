# LEGO Order Scraper — native Mac app (Swift)

A native macOS app written in Swift/SwiftUI. It replaces the Python-based Mac app in `mac-app/`.

- **No Python, no Chromium download.** The built-in browser uses WebKit, the same engine as Safari.
- **Log in inside the app.** LEGO.com appears on the right side of the window. Your login is remembered between runs.
- **Same results as the command line.** It writes the same `lego_orders.json`, `lego_orders.csv` and `lego_orders.html`, byte for byte. You can switch between versions, and a run in one picks up where the other left off.

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

**Save files to** (top of the window) shows where the JSON, CSV and HTML files go. Click **Browse…** to choose another folder, or **Use default** to go back. Saved progress lives with the files, so a new folder starts fresh.

**Stop** finishes the current order, saves and stops. Clicking it again stops right away. Progress is saved after every order, so **Start** picks up where it left off.

| What | Where |
|---|---|
| Your orders (JSON, CSV, HTML) | `~/Library/Application Support/LEGO Order Scraper/`, or the folder you chose under **Save files to** |
| Log | `~/Library/Logs/LEGO Order Scraper.log` |
| Saved LEGO login | WebKit's storage for this app. Remove it with **Forget saved LEGO login**. |

Options that match the command line: the since-date box is `--since-date`, **Max orders** is `--max-orders`, **Refetch everything** is `--fresh`, **Save files to** is `--output-dir`, **Leave out tracking numbers** is `--no-tracking`, and **Advanced** has the three wait times (`--delay`, `--load-more-delay`, `--load-more-final-wait`). `--cookie-source` isn't needed because you log in inside the app.

## If orders come out wrong

The app reads the same page text as the Python scraper, but through Safari's engine instead of Chrome's, so a page could occasionally read slightly differently. To help fix it:

1. Turn on **Advanced → Save page text for troubleshooting**.
2. Run again.
3. Send the files from the `page-text` folder inside the data folder. They contain your order details, so share them only with someone you trust.

## Giving it to someone else

**The `.app` is all they need.** It contains only the program, its icon and its settings file, and uses only libraries built into macOS. There's no Python and no Chromium, and none of your data or login is inside it.

- **Send the zip**, `mac-swift/dist/LEGO-Order-Scraper-native-mac.zip` (under 1 MB), rather than the bare `.app`. A `.app` is really a folder, and email or cloud drives can break it. AirDrop handles the `.app` fine.
- **They need** macOS 13 (Ventura) or newer, on any Mac (Apple Silicon or Intel).
- **Each person logs in** with their own LEGO account. Their orders are saved in their own `~/Library/Application Support/LEGO Order Scraper/`.

### The first time they open it

The app isn't notarized by Apple (that needs a paid Apple developer account), so macOS blocks it the first time:

1. Unzip it and drag **LEGO Order Scraper.app** to Applications.
2. Double-click it. When macOS says it can't verify the app, click **Done** (don't click Move to Trash).
3. Open **System Settings → Privacy & Security**, scroll down to **Security**, and click **Open Anyway** next to "LEGO Order Scraper was blocked…".
4. Confirm with your password or Touch ID, then click **Open Anyway** again.

After that it opens normally. The old shortcut (right-click → **Open**) no longer works on macOS 15 (Sequoia) and later; it still works on macOS 13 and 14.

Or, in Terminal, remove the download "quarantine" flag that macOS uses to block the app:

```bash
xattr -dr com.apple.quarantine "/Applications/LEGO Order Scraper.app"
```

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
