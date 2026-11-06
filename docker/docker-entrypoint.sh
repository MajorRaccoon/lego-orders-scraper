#!/bin/bash
# Starts a virtual display + a browser-based view of it (noVNC), so the
# visible Chromium window the scraper opens for the one-time LEGO login can
# be seen and used from your own browser, then launches the web UI.
set -e

DATA_DIR="${LEGO_WORK_DIR:-/data}"
mkdir -p "$DATA_DIR/lego_browser_profile"
# The scraper keeps its saved login in <script folder>/lego_browser_profile;
# point that at the mounted volume so the login survives container restarts.
ln -sfn "$DATA_DIR/lego_browser_profile" /app/lego_browser_profile

export DISPLAY=:99
Xvfb :99 -screen 0 1280x960x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
for _ in $(seq 1 50); do
  [ -e /tmp/.X11-unix/X99 ] && break
  sleep 0.1
done
fluxbox >/tmp/fluxbox.log 2>&1 &
x11vnc -display :99 -forever -shared -nopw -localhost -rfbport 5900 -quiet >/tmp/x11vnc.log 2>&1 &
websockify --web /usr/share/novnc "${LEGO_NOVNC_PORT:-6080}" localhost:5900 >/tmp/websockify.log 2>&1 &

exec python3 /app/lego_orders_webapp.py --host 0.0.0.0 --port 5000 --no-browser
