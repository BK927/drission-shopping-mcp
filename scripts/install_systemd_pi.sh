#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-$(pwd)}"
SERVICE_SRC="$APP_DIR/deploy/systemd/shopping-mcp.service"
SERVICE_DST="/etc/systemd/system/shopping-mcp.service"

if [[ ! -f "$SERVICE_SRC" ]]; then
  echo "Service file not found: $SERVICE_SRC"
  exit 1
fi

SERVICE_USER="$(whoami)"
SERVICE_HOME="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"
SERVICE_HOME="${SERVICE_HOME:-$HOME}"
CACHE_DIR="$SERVICE_HOME/.cache/drission-shopping-mcp"

TMP_FILE="$(mktemp)"
sed \
  -e "s|^User=.*|User=$SERVICE_USER|" \
  -e "s|^WorkingDirectory=.*|WorkingDirectory=$APP_DIR|" \
  -e "s|^EnvironmentFile=.*|EnvironmentFile=$APP_DIR/.env|" \
  -e "s|^ExecStart=.*|ExecStart=$APP_DIR/.venv/bin/python -m shopping_mcp.asgi|" \
  -e "s|^ReadWritePaths=.*|ReadWritePaths=$APP_DIR $CACHE_DIR|" \
  "$SERVICE_SRC" > "$TMP_FILE"

sudo cp "$TMP_FILE" "$SERVICE_DST"
rm -f "$TMP_FILE"

sudo systemctl daemon-reload
sudo systemctl enable --now shopping-mcp
sudo systemctl status shopping-mcp --no-pager || true

echo
echo "Installed shopping-mcp.service"
echo "Health check: curl http://127.0.0.1:8000/healthz"
