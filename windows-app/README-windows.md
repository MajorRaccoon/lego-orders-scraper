# LEGO Order Scraper — Windows app

A double-clickable Windows app. It runs the same web UI as the other versions in your default browser, so there's no Python to install. A small console window shows what it's doing.

It's the Python version packaged with [PyInstaller](https://pyinstaller.org/). It uses Chromium through Playwright, like the command line and web UI, and writes the same `lego_orders.json`, `lego_orders.csv` and `lego_orders.html`.

## Get it

The app is built automatically on GitHub's Windows build server whenever its files change:

1. On GitHub, open the repo's **Actions** tab, then the **Windows app** workflow.
2. Click the latest successful run (green check).
3. Under **Artifacts**, download **LEGO-Order-Scraper-windows**. You get a zip that contains `LEGO-Order-Scraper-windows.zip`.

To build a new one on demand, click **Run workflow** on that page. Artifacts are kept for 30 days.

## Use it

1. Unzip it anywhere, for example in `Documents`. Keep the whole **LEGO Order Scraper** folder together: the `.exe` needs the `_internal` folder next to it.
2. Double-click **LEGO Order Scraper.exe**.
3. The first time, Windows SmartScreen may say "Windows protected your PC", because the app isn't code-signed. Click **More info**, then **Run anyway**.
4. A console window opens and the web page opens in your default browser.
5. Click **Start**. The first run downloads the browser the scraper uses (about 150 MB, once).
6. A Chromium window opens. Log in to LEGO.com there, then click **"I've logged in, continue"** on the web page. Your login is saved for next time.
7. Results appear as download links on the page.

**To quit:** click **Quit app** on the page, or close the console window. Progress is saved after every order, so quitting mid-run loses nothing already fetched.

| What | Where |
|---|---|
| Your orders (JSON, CSV, HTML), saved login, downloaded browser | `%LOCALAPPDATA%\LEGO Order Scraper\` |
| Log | `%LOCALAPPDATA%\LEGO Order Scraper\LEGO Order Scraper.log` |

To open that folder, paste `%LOCALAPPDATA%\LEGO Order Scraper` into File Explorer's address bar. Delete the folder to reset everything.

## Giving it to someone else

Share the zip. It contains none of your data or login: those stay in your own `%LOCALAPPDATA%` folder. The other person needs Windows 10 or 11 (64-bit), and logs in with their own LEGO account.

## For developers

- **Build on a Windows PC** (Python 3.10+ from python.org), in PowerShell:
  ```powershell
  cd windows-app
  powershell -ExecutionPolicy Bypass -File build_windows.ps1
  ```
  The result is `windows-app\dist\LEGO-Order-Scraper-windows.zip`. It can't be built on a Mac: PyInstaller only builds for the system it runs on.
- The scripts in this folder are copies. The repo root is the source of truth, and `lego_orders_app.py` comes from `mac-app/`. Run `./sync_copies.sh` after editing; a test fails if a copy is out of date.
- Debug options:
  - `"LEGO Order Scraper.exe" --serve-only` runs just the server.
  - `--run-scraper --help` shows the scraper's own options.
  - `--self-test` downloads Chromium if needed, opens a page with it, and prints `SELF-TEST OK`.
- The GitHub Actions workflow (`.github/workflows/windows-app.yml`) builds the app, then checks it: `--version`, `--self-test`, and the web server answering. Only then does it attach the zip.
