# LEGO Order Scraper

A personal tool that downloads **your own** LEGO.com order history, with item-level detail, and saves it as JSON, CSV and an HTML report.

For every order it records the order number, date, status and total. For every item it records the name, item number or SKU, quantity, regular and sale price, free-gift / backorder / gift-card / loose-piece flags, custom build IDs (Minifigure Factory) and tracking number. The HTML report also has a **monthly spending table** and a **bar chart of monthly spending for each year**.

It reads LEGO.com through a real web browser. **You log in to LEGO.com yourself** in that browser (so CAPTCHA and 2FA work normally). The tool never asks for or stores your password. Which browser depends on how you run it:

- **Command line, web UI, Docker and the Windows app** drive a Chromium browser with [Playwright](https://playwright.dev/python/), which is written in Python.
- **The macOS app** is written in Swift and uses Apple's built-in **WebKit**, the engine behind Safari, inside its own window. It needs no Python, no Playwright and no Chromium download.

Both read the same pages and produce identical files. The tests check this.

There are five ways to run it:

| Option | Best for | Browser | Section |
|---|---|---|---|
| Command line | Full control, scripting | Chromium (Playwright) | [Command line](#1-command-line) |
| Web UI | Point-and-click, on your own machine | Chromium (Playwright) | [Web UI](#2-web-ui) |
| Docker | Nothing to install except Docker | Chromium (Playwright), inside the container | [Docker](#3-docker) |
| macOS app | Native Mac app, log in inside the window | WebKit (built into macOS) | [macOS app](#4-macos-app) |
| Windows app | Double-click on Windows, no Python needed | Chromium (Playwright) | [Windows app](#5-windows-app) |

---

## Requirements (command line and web UI)

Docker and the macOS app don't need any of this.

- Python **3.10+** (on a Mac: `brew install python`)
- Python packages: `playwright`, `cryptography`, `flask` (Flask is only needed for the web UI)
- Windows only, and only for `--cookie-source`: `pywin32`

Install them (one time):

```bash
python3 -m pip install playwright cryptography flask
python3 -m playwright install chromium
```

---

## 1. Command line

```bash
python3 lego_orders_scraper.py
```

**First run:**
1. A Chromium window opens on LEGO.com.
2. Log in by hand in that window, then go to **My Orders**.
3. Return to the terminal and press **Enter**.

Your login is saved in a `lego_browser_profile/` folder next to the scraper script, so later runs skip the login (until LEGO expires the session).

**Where files go:** on a Mac, the output files are saved in `~/Library/Application Support/LEGO Order Scraper/`, the same folder the Mac app uses, so every version shares and resumes the same data. Each run is also recorded in `~/Library/Logs/LEGO Order Scraper.log`. The start of each run prints both locations. On other systems, files go in the current folder and there's no log file. To save them elsewhere, use `--output-dir FOLDER`, or `--output-dir browse` to pick the folder in a dialog. Saved progress lives with the files, so a new folder starts fresh. A relative `--output`, `--csv` or `--html` name goes inside that folder.

### Common examples

```bash
python3 lego_orders_scraper.py --since-date all          # entire order history (no date cutoff)
python3 lego_orders_scraper.py --output-dir ~/Documents/LEGO   # save the files in another folder
python3 lego_orders_scraper.py --output-dir browse       # pick the folder in a dialog
python3 lego_orders_scraper.py --since-date 01/31/2026   # only orders on/after this date
python3 lego_orders_scraper.py --max-orders 5            # only the 5 most recent orders
python3 lego_orders_scraper.py --html report.html        # HTML report to another file (default lego_orders.html)
python3 lego_orders_scraper.py --no-html                 # skip the HTML report
python3 lego_orders_scraper.py --headless                # no browser window (only once logged in)
python3 lego_orders_scraper.py --fresh                   # ignore saved progress, refetch everything
python3 lego_orders_scraper.py --no-tracking             # leave tracking numbers out of the files
python3 lego_orders_scraper.py --version
```

### All options

| Option | Default | What it does |
|---|---|---|
| `--output-dir FOLDER` | the data folder | Folder to save the JSON, CSV and HTML files in. Use `--output-dir browse` to pick it in your system's folder dialog. |
| `--since-date MM/DD/YYYY` | `02/01/2024` | Only fetch orders placed on/after this date. Use `all` for no cutoff. Paging stops early once it passes the date. |
| `--max-orders N` | all | Only fetch the N most recent orders. |
| `--output PATH` | `lego_orders.json` | JSON output file. |
| `--csv PATH` | `lego_orders.csv` | CSV output file (one row per item). |
| `--html PATH` | `lego_orders.html` | Where to write the self-contained HTML report. |
| `--no-html` | off | Skip the HTML report. |
| `--headless` | off | Run with no visible browser. Only works after you've logged in once. |
| `--fresh` | off | Refetch every order instead of resuming. |
| `--no-tracking` | off | Leave tracking numbers out of the JSON, CSV and HTML. The column stays, just empty. |
| `--delay SEC` | `1.5` | Wait between order-detail pages. Please keep it polite. |
| `--load-more-delay SEC` | `1.2` | Wait after each "Load More" click on the order list. |
| `--load-more-final-wait SEC` | `5.0` | How long to wait for "Load More" to reappear before assuming the list is done. Raise it if orders get cut off. |
| `--cookie-source PATH` | — | Reuse the LEGO login from another signed-in Chrome profile instead of logging in. See below. |

### Resuming and interruptions

The JSON and CSV files are saved after **every** order. If you press Ctrl+C or the run stops, run the same command again: it skips orders it already has and fetches only what's missing. A single order that fails to load is skipped and retried next run.

If a saved order's status changes on LEGO's My Orders list (for example **In Process** → **Shipped**), the next run re-reads that order's detail page, so item statuses and tracking numbers stay current. Its saved details are kept if that re-read fails, and it's retried next run. Orders older than the since date aren't re-read, but their status is still updated.

### Reusing your Chrome login (`--cookie-source`)

If you're already signed in to LEGO.com in Chrome, the tool can copy that session instead of asking you to log in:

```bash
python3 lego_orders_scraper.py --cookie-source "$HOME/Library/Application Support/Google/Chrome/Default"
```

Typical profile paths:
- macOS: `~/Library/Application Support/Google/Chrome/Default`
- Linux: `~/.config/google-chrome/Default`
- Windows: `%LOCALAPPDATA%/Google/Chrome/User Data/Default`

On a Mac you may be asked to allow Keychain access ("Chrome Safe Storage"). If it doesn't work, run `python3 lego_cookie_diagnose.py "<profile path>"` to see which step fails. It prints counts only, never cookie values.

---

## 2. Web UI

A local web page where you fill in the same options, click **Start**, and watch progress live.

```bash
python3 lego_orders_webapp.py                 # opens http://127.0.0.1:8765
python3 lego_orders_webapp.py --port 9000      # use another port
python3 lego_orders_webapp.py --no-browser     # don't auto-open a browser tab
```

- On first run a Chromium window opens. Log in there, then click **"I've logged in, continue"** on the web page.
- **Save files to** starts with the data folder. Click **Browse…** to pick another folder in your system's folder dialog, or **Use default** to go back. The page remembers your choice. (Hidden in Docker, where files stay in the data volume.)
- The **HTML report file name** box starts as `lego_orders.html`. Clear it to skip the report.
- The **Leave out tracking numbers** checkbox is the same as `--no-tracking`.
- **Stop** asks the scraper to finish gracefully. Clicking it a second time stops it immediately.
- Result files appear as download links when the run finishes. They're saved in `~/Library/Application Support/LEGO Order Scraper/` on a Mac, the same folder as the command line and Mac app, and each run is recorded in `~/Library/Logs/LEGO Order Scraper.log`.
- The web page keeps running after a scrape finishes, so you can start another one, and Terminal doesn't return to its prompt. When a scrape ends, Terminal shows a reminder. Press **Ctrl+C** in Terminal to quit.
- It listens only on `127.0.0.1` (your machine). It has no password, so don't expose it to a network.

---

## 3. Docker

Runs the web UI in a container with its own Chromium. Nothing else to install. Files are in [`docker/`](docker/).

### Build and run

```bash
cd docker
docker compose up --build      # first time: builds the image, then starts it
```

Afterwards, just `docker compose up` (add `-d` to run in the background; `docker compose down` to stop).

Then open **http://localhost:8765**, choose your options, and click **Start**.

### First-time LEGO login in Docker

The login browser runs on a virtual screen inside the container. Open
**http://localhost:6080/vnc.html?autoconnect=1&resize=scale** (the web UI shows this link while waiting). Log in to LEGO.com there, then click **"I've logged in, continue"** in the web UI. The login is saved, so later runs skip this step and can use Headless.

### Ports and settings

| What | Your machine | Change with |
|---|---|---|
| Web UI | `8765` | `LEGO_WEB_PORT=9000 docker compose up` |
| Login browser view (noVNC) | `6080` | edit `docker-compose.yml` |
| Timezone for order dates | `America/New_York` | `LEGO_TZ=America/Los_Angeles docker compose up --build` |

> Port **5000 is avoided on purpose**: on macOS, AirPlay Receiver uses it and answers every request with "403 Forbidden".

### Where's my data?

Everything (saved login, JSON, CSV, HTML) is in the `lego-data` Docker volume, not in the image. Download results from the web UI, or copy them out:

```bash
docker compose cp lego-scraper:/data/lego_orders.json .
```

To reset everything, including the saved login, run `docker compose down -v`.

### Without Compose

```bash
docker build -t lego-orders-scraper docker/
docker run --rm -p 127.0.0.1:8765:5000 -p 127.0.0.1:6080:6080 \
  --shm-size=1g -v lego-data:/data lego-orders-scraper
```

Keep the `127.0.0.1:` prefixes so only your machine can reach the UI. Keep `--shm-size` too: Chromium crashes with Docker's small default shared memory.

More details: [`docker/README-docker.md`](docker/README-docker.md).

---

## 4. macOS app

A native Mac app written in Swift. It uses macOS's built-in **WebKit** (Safari's engine) instead of Playwright and Chromium. LEGO.com appears inside the app window, so you log in right there. It needs no Python and downloads no extra browser. Files are in [`mac-swift/`](mac-swift/).

### Build it (once)

Needs macOS 13+ and Xcode (or the command-line tools: `xcode-select --install`).

```bash
cd mac-swift
./build_app.sh
```

The result is `mac-swift/dist/LEGO Order Scraper.app` (Apple Silicon and Intel). Drag **the `.app` itself** to Applications.

### Use it

1. Double-click **LEGO Order Scraper**, choose your options, and click **Start**.
2. First time only: log in to LEGO.com in the browser on the right side of the window. The app continues by itself once your orders appear.
3. When it's done, click **Open HTML report** or **Show files in Finder**.

To save the files somewhere else, use **Save files to → Browse…** at the top of the window. The app remembers your choice; **Use default** goes back.

- Data: `~/Library/Application Support/LEGO Order Scraper/` (same files and format as the command line, so runs resume across versions)
- Log: `~/Library/Logs/LEGO Order Scraper.log`

**Sharing it:** the `.app` is all anyone needs. Send the zip, `mac-swift/dist/LEGO-Order-Scraper-native-mac.zip`. It needs macOS 13 or newer, on Apple Silicon or Intel.

**First open:** the app isn't notarized by Apple, so macOS blocks it the first time. Double-click it and click **Done**. Then open **System Settings → Privacy & Security** and click **Open Anyway** next to "LEGO Order Scraper". On macOS 13 and 14, right-click the app → **Open** also works. Full steps: [Giving it to someone else](mac-swift/README-swift.md#giving-it-to-someone-else).

More details and troubleshooting: [`mac-swift/README-swift.md`](mac-swift/README-swift.md). The older Python-based Mac app is still in [`mac-app/`](mac-app/README-mac.md).

---

## 5. Windows app

A double-clickable Windows app (Windows 10 or 11), built for both x64 PCs and ARM (arm64) PCs. It's the web UI packaged with its own Python, so there's nothing to install. It opens in your default browser, and a small console window shows progress. Files are in [`windows-app/`](windows-app/).

- **Get it:** from the repo's **Releases** page, or from the latest run of the **Windows app** workflow on the **Actions** tab. Choose **x64** for most PCs (Intel or AMD), or **arm64** for Windows on ARM (for example Snapdragon laptops).
- **Use it:** unzip it, keep the folder together, and double-click **LEGO Order Scraper.exe**. If SmartScreen warns, click **More info → Run anyway**.
- Data and log: `%LOCALAPPDATA%\LEGO Order Scraper\`. To save the files elsewhere, use **Save files to → Browse…** on the page. Quit with **Quit app** on the page, or by closing the console window.

Full details: [`windows-app/README-windows.md`](windows-app/README-windows.md).

---

## Output files

On a Mac, every version saves these in `~/Library/Application Support/LEGO Order Scraper/` and records runs in `~/Library/Logs/LEGO Order Scraper.log`. On Windows they go in `%LOCALAPPDATA%\LEGO Order Scraper\` (log included). Docker uses its `lego-data` volume.

| File | Contents |
|---|---|
| `lego_orders.json` | One object per order, with a nested `items` list. |
| `lego_orders.csv` | One row per item. Opens in Excel / Numbers / Google Sheets. (Before scraper v36 it was called `lego_order_items.csv`; an old file of that name is renamed automatically.) |
| `lego_orders.html` | Self-contained report (all orders, items, a monthly spending table and per-year bar charts). Just open it in a browser. Written every run unless you use `--no-html`. |

Prices: each item has `regular_price` and `sale_price`. They're equal when the item wasn't on sale, and both are empty for free gifts.

---

## Helper scripts

| Script | What it does |
|---|---|
| `lego_orders_to_html.py` | Rebuild the HTML report from an existing JSON file, without going to LEGO.com. `python3 lego_orders_to_html.py --json lego_orders.json --html lego_orders.html` (add `--no-tracking` to leave tracking numbers out) |
| `lego_repair_json_from_csv.py` | Fill in missing item detail in the JSON using the CSV. Makes a `.bak` backup first. |
| `strip_non_ascii.py` | Remove non-ASCII characters (™, smart quotes, dashes) from a JSON or CSV file. Add `--in-place` to overwrite (makes a `.bak` backup). |
| `lego_cookie_diagnose.py` | Step-by-step check of why `--cookie-source` isn't working. |

---

## For developers

- `lego_folder_picker.py` shows the system folder dialog for `--output-dir browse` and the web UI's **Browse…** button.
- **The scripts in the repo root are the source of truth.** `docker/`, `mac-app/` and `windows-app/` hold copies (the app launcher's source is `mac-app/lego_orders_app.py`). After editing, run:
  ```bash
  ./sync_copies.sh
  ```
- Bump `__version__` in a script whenever you change it.
- Run the test suite (needs `playwright`, `cryptography` and `flask` installed):
  ```bash
  python3 lego-tests/run_tests.py
  ```
  On a Mac with Xcode, this suite also checks that the Swift app's parsers and writers match the Python ones byte for byte.
- The Swift app's own unit tests:
  ```bash
  cd mac-swift && swift test
  ```
- The Swift app re-implements the parsers in `mac-swift/Sources/LegoCore/Parsing.swift`. If LEGO changes its pages, fix both versions.

### Environment variables

None of these are needed for normal use. They're for customizing a setup or for development.

| Variable | Applies to | Used for |
|---|---|---|
| `LEGO_WORK_DIR` | Command line, Web UI, Docker (the image sets it to `/data`), Windows app, older Python Mac app | Data folder for output files (default on a Mac: `~/Library/Application Support/LEGO Order Scraper`; on Windows: `%LOCALAPPDATA%\LEGO Order Scraper`; on Linux: the current folder) |
| `LEGO_LOG_FILE` | Command line, Web UI | Log file each run is recorded in (default on a Mac: `~/Library/Logs/LEGO Order Scraper.log`; on Windows: `%LOCALAPPDATA%\LEGO Order Scraper\LEGO Order Scraper.log`; on Linux: none). Set it to an empty value to turn the log off. |
| `LEGO_PROFILE_DIR` | Command line, Web UI, Windows app, older Python Mac app | Folder for the saved Chromium login (default: `lego_browser_profile` next to the scraper). Docker doesn't use it; it keeps the login in its data volume. |
| `PLAYWRIGHT_BROWSERS_PATH` | Command line, Web UI, Windows app, older Python Mac app | Where Playwright's Chromium is installed (a Playwright setting). Docker's image already sets it. |
| `LEGO_WEB_PORT` | Docker | Web UI port on your machine (default `8765`). Set it when running `docker compose up`. |
| `LEGO_TZ` | Docker | Timezone of the container's browser (default `America/New_York`). Set it when running `docker compose up --build`. |
| `LEGO_NOVNC_PORT` | Docker (the image sets it) | Port of the noVNC login view that the web UI links to. Outside Docker it's unset, and no link is shown. |
| `LEGO_APP_MODE` | Older Python Mac app (`mac-app/`), Windows app | Set by the launcher: `window` (Mac) or `browser` (Windows; adds a **Quit app** button) |
| `LEGO_APP_DATA_DIR` | Older Python Mac app, Windows app | Override the app's data folder |
| `LEGO_SKIP_BROWSER_INSTALL` | Older Python Mac app, Windows app | Skip the first-run Chromium download |
| `LEGO_SELFCHECK` | Mac Swift app | Self-check mode for developers (see [`mac-swift/README-swift.md`](mac-swift/README-swift.md)) |
| `LEGO_SELFCHECK_URL` | Mac Swift app | Page the self-check loads (default: My Orders) |
| `LEGO_SRC` | Test suite | Folder holding the scripts to test (default: this repository) |

---

## Privacy and good manners

- This tool only reads **your own** account, using a login you enter yourself.
- Your saved browser profile and the Docker `lego-data` volume hold a logged-in LEGO session. Treat them like a password.
- Output files and browser profiles are in `.gitignore`. Never commit them.
- Keep the delays reasonable: every page load is real traffic to LEGO.com.
- Not affiliated with or endorsed by the LEGO Group.
