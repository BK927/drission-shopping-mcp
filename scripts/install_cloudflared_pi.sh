#!/usr/bin/env bash
set -euo pipefail

sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null

sudo apt-get update
sudo apt-get install -y cloudflared
cloudflared --version

echo "cloudflared installed."
echo "Recommended next step for remote-managed tunnel:"
echo "  sudo cloudflared service install <TUNNEL_TOKEN>"
echo

echo "If you want a locally-managed tunnel instead:"
echo "  1) cloudflared tunnel login"
echo "  2) cloudflared tunnel create shopping-mcp"
echo "  3) copy deploy/cloudflared/config.example.yml to /etc/cloudflared/config.yml"
echo "  4) sudo cloudflared service install"
