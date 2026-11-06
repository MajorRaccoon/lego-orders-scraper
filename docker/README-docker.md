# LEGO Order Scraper — Docker

Runs the web UI (`lego_orders_webapp.py`) in a container with its own
Chromium, so there's nothing to install except Docker.

## Run it

    docker compose up --build        # first time (builds the image)
    docker compose up                # afterwards

Then open **http://localhost:8765**, choose your options, click **Start**.

If 8765 is taken, pick another: `LEGO_WEB_PORT=9000 docker compose up`.
(Port 5000 is deliberately avoided: on macOS, AirPlay Receiver uses it and
answers every request with "403 Forbidden".)

### Ports

| What | On your machine | Inside the container |
|------|-----------------|----------------------|
| Web UI | **8765** (change with `LEGO_WEB_PORT`) | 5000 (internal only; you never use it) |
| Browser view for login (noVNC) | **6080** | 6080 |

### Timezone

The container's browser defaults to US Eastern (`America/New_York`) so order
dates match LEGO.com. Use another zone with
`LEGO_TZ=America/Los_Angeles docker compose up`, or edit `docker-compose.yml`.
(After this change, run `docker compose up --build` once.)

## First-time LEGO login

The scraper opens a real browser window for you to log in. In the container
that window lives on a virtual screen — view it at
**http://localhost:6080/vnc.html?autoconnect=1&resize=scale** (the web UI
shows a link to it while waiting). Log in to LEGO.com there, then click
**"I've logged in, continue"** in the web UI. Your login is saved in the
`lego-data` volume, so later runs skip this step (and can use Headless).

## Where's my data?

Everything (saved login, `lego_orders.json`, CSV, HTML report) is in the
`lego-data` Docker volume, not inside the image. Download results with the
links on the web UI, or copy them out:

    docker compose cp lego-scraper:/data/lego_orders.json .

Reset everything (including the saved login): `docker compose down -v`

## Sharing the image

    docker build -t YOURNAME/lego-orders-scraper .
    docker push YOURNAME/lego-orders-scraper

Others run it with `docker run` — note the `127.0.0.1:` prefixes and
`--shm-size`:

    docker run --rm -p 127.0.0.1:8765:5000 -p 127.0.0.1:6080:6080 \
      --shm-size=1g -v lego-data:/data YOURNAME/lego-orders-scraper

## Security notes

- The web UI and browser view have **no password**. Keep the `127.0.0.1:`
  prefix on the published ports so only your own machine can reach them.
- The `lego-data` volume holds your logged-in LEGO session — treat it like
  a password, and don't push an image built with data baked in (the
  `.dockerignore` keeps profile/output files out of the build).
- Every person running this logs in with their own LEGO account; nothing
  of yours is in the image.
