#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8000}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found. Run scripts/install_cloudflared_pi.sh first."
  exit 1
fi

echo "Starting temporary quick tunnel to http://127.0.0.1:${PORT}"
echo "This URL is ephemeral. Good for testing, not for stable ChatGPT connector use."
cloudflared tunnel --url "http://127.0.0.1:${PORT}"
