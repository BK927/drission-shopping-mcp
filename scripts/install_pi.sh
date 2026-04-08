#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y python3 python3-venv python3-pip chromium

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo ".env created. Fill NAVER_CLIENT_ID and NAVER_CLIENT_SECRET before running."
fi

echo "Done. Run: source .venv/bin/activate && python -m shopping_mcp.asgi"
