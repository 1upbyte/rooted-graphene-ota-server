#!/usr/bin/env sh
set -eu

APP_DIR="/app"
PUBLISH_DIR="$APP_DIR/publish"

run_build() {
  echo "[entrypoint] Running build..."
  uv run "$APP_DIR/scripts/build_oriole_publish.py"
}

build_loop() {
  while true; do
    run_build
    sleep 86400
  done
}

# Ensure publish dir exists
mkdir -p "$PUBLISH_DIR"

# Start build loop in background
build_loop &

# Start nginx in foreground (so Docker keeps the container running)
exec nginx -g 'daemon off;'
