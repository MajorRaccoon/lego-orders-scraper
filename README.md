# LEGO Order Scraper

A personal tool that downloads **your own** LEGO.com order history, with item-level detail, and saves it as JSON, CSV and an HTML report.

For every order it records the order number, date, status and total. For every item it records the name, item number or SKU, quantity, regular and sale price, free-gift / backorder / gift-card / loose-piece flags, custom build IDs (Minifigure Factory) and tracking number. The HTML report also has a **monthly spending table**.

It drives a real Chromium browser with [Playwright](https://playwright.dev/python/). **You log in to LEGO.com yourself** in that browser window (so CAPTCHA and 2FA work normally). The tool never asks for or stores your password.

There are four ways to run it:

| Option | Best for | Section |
|---|---|---|
| Command line | Full control, scripting | [Command line](#1-command-line) |
| Web UI | Point-and-click, on your own machine | [Web UI](#2-web-ui) |
| Docker | Nothing to install except Docker | [Docker](#3-docker) |
| macOS app | Double-click Mac app | [macOS app](#4-macos-app) |

---

## Requirements

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

Your login is saved in `./lego_browser_profile/`, so later runs skip the login (until LEGO expires the session).

### Common examples

```bash
python3 lego_orders_scraper.py --since-date all          # entire order history (no date cutoff)
python3 lego_orders_scraper.py --since-date 01/31/2026   # only orders on/after this date
python3 lego_orders_scraper.py --max-orders 5            # only the 5 most recent orders
python3 lego_orders_scraper.py --html lego_orders.html   # also write the HTML report
python3 lego_orders_scraper.py --headless                # no browser window (only once logged in)
python3 lego_orders_scraper.py --fresh                   # ignore saved progress, refetch everything
python3 lego_orders_scraper.py --version
```

### All options

| Option | Default | What it does |
|---|---|---|
| `--since-date MM/DD/YYYY` | `02/01/2024` | Only fetch orders placed on/after this date. Use `all` for no cutoff. Paging stops early once it passes the date. |
| `--max-orders N` | all | Only fetch the N most recent orders. |
| `--output PATH` | `lego_orders.json` | JSON output file. |
| `--csv PATH` | `lego_order_items.csv` | CSV output file (one row per item). |
| `--html PATH` | not written | Also write a self-contained HTML report. |
| `--headless` | off | Run with no visible browser. Only works after you've logged in once. |
| `--fresh` | off | Refetch every order instead of resuming. |
| `--delay SEC` | `1.5` | Wait between order-detail pages. Please keep it polite. |
| `--load-more-delay SEC` | `1.2` | Wait after each "Load More" click on the order list. |
| `--load-more-final-wait SEC` | `5.0` | How long to wait for "Load More" to reappear before assuming the list is done. Raise it if orders get cut off. |
| `--cookie-source PATH` | — | Reuse the LEGO login from another signed-in Chrome profile instead of logging in. See below. |

### Resuming and interruptions

The JSON and CSV files are saved after **every** order. If you press Ctrl+C or the run stops, run the same command again: it skips orders it already has and fetches only what's missing. A single order that fails to load is skipped and retried next run.

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
- **Stop** asks the scraper to finish gracefully. Clicking it a second time stops it immediately.
- Result files appear as download links when the run finishes.
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

A double-clickable Mac app with a native window, the same options screen and the same scraper. Files are in [`mac-app/`](mac-app/).

### Build it (once)

Needs Python 3.10+ and the Xcode command-line tools (`xcode-select --install`).

```bash
cd mac-app
./build_mac.sh
```

The result is `mac-app/dist/LEGO Order Scraper.app`. Drag **the `.app` itself** to Applications. Don't drag the program file from inside it.

### Use it

1. Double-click **LEGO Order Scraper**.
2. The first **Start** downloads Chromium (~150 MB, once).
3. Log in to LEGO.com in the window that opens, then click **"I've logged in, continue"**.
4. Results appear as download links, or click **Open data folder**.

- Data: `~/Library/Application Support/LEGO Order Scraper/` (delete it to reset)
- Log: `~/Library/Logs/LEGO Order Scraper.log`

The app isn't notarized. If macOS blocks it, right-click the app, choose **Open**, then **Open** again.

More details and troubleshooting: [`mac-app/README-mac.md`](mac-app/README-mac.md).

---

## Output files

| File | Contents |
|---|---|
| `lego_orders.json` | One object per order, with a nested `items` list. |
| `lego_order_items.csv` | One row per item. Opens in Excel / Numbers / Google Sheets. |
| `lego_orders.html` | Self-contained report (all orders, items, monthly spending). Just open it in a browser. |

Prices: each item has `regular_price` and `sale_price`. They're equal when the item wasn't on sale, and both are empty for free gifts.

---

## Helper scripts

| Script | What it does |
|---|---|
| `lego_orders_to_html.py` | Rebuild the HTML report from an existing JSON file, without going to LEGO.com. `python3 lego_orders_to_html.py --json lego_orders.json --html lego_orders.html` |
| `lego_repair_json_from_csv.py` | Fill in missing item detail in the JSON using the CSV. Makes a `.bak` backup first. |
| `strip_non_ascii.py` | Remove non-ASCII characters (™, smart quotes, dashes) from a JSON or CSV file. Add `--in-place` to overwrite (makes a `.bak` backup). |
| `lego_cookie_diagnose.py` | Step-by-step check of why `--cookie-source` isn't working. |

---

## For developers

- **The scripts in the repo root are the source of truth.** `docker/` and `mac-app/` hold copies. After editing a root script, run:
  ```bash
  ./sync_copies.sh
  ```
- Bump `__version__` in a script whenever you change it.
- Run the test suite (needs `playwright`, `cryptography` and `flask` installed):
  ```bash
  python3 lego-tests/run_tests.py
  ```

### Environment variables

| Variable | Used for |
|---|---|
| `LEGO_WORK_DIR` | Folder for output files (web UI / app) |
| `LEGO_PROFILE_DIR` | Browser profile (saved login) folder |
| `PLAYWRIGHT_BROWSERS_PATH` | Where Playwright's Chromium is installed |
| `LEGO_WEB_PORT` | Docker: web UI port on your machine (default 8765) |
| `LEGO_TZ` | Docker: browser timezone (default America/New_York) |
| `LEGO_NOVNC_PORT` | Port shown for the noVNC login view |
| `LEGO_APP_MODE` | Mac app: `window` or `browser` |
| `LEGO_APP_DATA_DIR` | Mac app: data folder |
| `LEGO_SKIP_BROWSER_INSTALL` | Mac app: skip the first-run Chromium download |

---

## Privacy and good manners

- This tool only reads **your own** account, using a login you enter yourself.
- Your saved browser profile and the Docker `lego-data` volume hold a logged-in LEGO session. Treat them like a password.
- Output files and browser profiles are in `.gitignore`. Never commit them.
- Keep the delays reasonable: every page load is real traffic to LEGO.com.
- Not affiliated with or endorsed by the LEGO Group.
