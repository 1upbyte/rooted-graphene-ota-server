#!/usr/bin/env sh
set -eu

APP_DIR="/app"
PUBLISH_DIR="$APP_DIR/publish"

run_build() {
  echo "[entrypoint] Running build..."
  uv run "$APP_DIR/scripts/build_oriole_publish.py"
}

start_server() {
  echo "[entrypoint] Starting HTTP server on :80"
  cd "$PUBLISH_DIR"
  python3 -m http.server 80
}

# Run first build immediately.
run_build

# Start HTTP server in background and then rebuild every 24h.
start_server &
SERVER_PID=$!

while true; do
  sleep 86400
  run_build
  # Keep server running unless it has died.
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "[entrypoint] HTTP server stopped; restarting"
    start_server &
    SERVER_PID=$!
  fi
done
