# LEGO Order Scraper — macOS app

A double-clickable Mac app: a native window with the same options screen as the web
version, live progress, and the same scraper underneath.

## Build it (once, on your Mac)

Needs Python 3.10+ (`brew install python`) and Xcode command-line tools (`xcode-select --install`).

    cd mac-app
    ./build_mac.sh

Result: `dist/LEGO Order Scraper.app` (plus `dist/LEGO-Order-Scraper-mac.zip`). Drag the app to
**Applications**. It's built for *your* Mac's chip (Apple Silicon or Intel); build on each type
if you need both.

## Use it

1. Double-click **LEGO Order Scraper**.
2. First **Start** downloads the browser the scraper uses (~150 MB, once) — progress shows in the window.
3. First time only: a Chromium window opens — log in to LEGO.com there, then click
   **"I've logged in, continue"** in the app. The login is saved for next time.
4. Results (JSON / CSV / HTML) appear as download links, or click **Open data folder**.

Everything lives in `~/Library/Application Support/LEGO Order Scraper/`
(orders, saved login, downloaded browser). Delete that folder to reset. Log:
`~/Library/Logs/LEGO Order Scraper.log`.

## Giving it to someone else

The app is **not notarized** (that needs a paid Apple developer account), so a copy that was
downloaded/AirDropped is blocked once by Gatekeeper. The recipient either:
- System Settings → Privacy & Security → **Open Anyway** (after trying to open it once), or
- right-click the app → **Open** → **Open** (macOS 13 and 14 only; removed in macOS 15), or
- Terminal: `xattr -dr com.apple.quarantine "/Applications/LEGO Order Scraper.app"`

Each person logs in with their own LEGO account; nothing of yours is inside the app.

## If something's off

- **Window doesn't appear / opens in your browser instead:** the native-window component couldn't
  start; the app falls back to your default browser and shows a **Quit app** button. Check the log.
- **Debug from Terminal:** `"/Applications/LEGO Order Scraper.app/Contents/MacOS/LEGO Order Scraper" --serve-only`
  prints a local URL you can open in any browser; add `--run-scraper --help` to use the scraper's
  command line directly.
- **Browser download fails:** check your connection and click Start again (it retries).

## Error: "Failed to load Python shared library '/Applications/_internal/Python'"

You copied the bare program file (not the app) into Applications. Delete it and the stray
`_internal` folder from /Applications, then drag **`LEGO Order Scraper.app`** itself from
`mac-app/dist/` (re-run `./build_mac.sh` first; it now leaves only the .app in `dist/`).
