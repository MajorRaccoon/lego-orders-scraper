# Image tag must match the playwright version pinned in requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.56.0-jammy

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    LEGO_WORK_DIR=/data \
    LEGO_NOVNC_PORT=6080

# Virtual display + VNC + a web VNC client, so the browser window used for
# the one-time LEGO.com login is viewable from your own browser.
RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb x11vnc fluxbox novnc websockify tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lego_orders_scraper.py lego_orders_webapp.py lego_orders_to_html.py \
     lego_repair_json_from_csv.py strip_non_ascii.py ./
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && mkdir -p /data

VOLUME /data
EXPOSE 5000 6080
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
