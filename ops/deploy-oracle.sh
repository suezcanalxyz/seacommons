#!/usr/bin/env bash
# ops/deploy-oracle.sh — Deploy / update SeaCommons API on Oracle Cloud
# Run as the 'ubuntu' user on 204.216.210.155
# Usage: bash ops/deploy-oracle.sh

set -euo pipefail
REPO=/home/ubuntu/seacommons
API=$REPO/apps/api
VENV=$REPO/.venv

echo "=== [1/7] Pull latest code ==="
cd "$REPO"
git pull origin main

echo "=== [2/7] Install / update Python dependencies ==="
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$API/requirements-api.txt" -q

echo "=== [3/7] Install / configure nginx ==="
if ! command -v nginx &>/dev/null; then
    sudo apt-get update -q && sudo apt-get install -y nginx -q
fi
sudo cp "$REPO/ops/nginx.conf" /etc/nginx/sites-available/seacommons
sudo ln -sf /etc/nginx/sites-available/seacommons /etc/nginx/sites-enabled/seacommons
sudo rm -f /etc/nginx/sites-enabled/default  # remove nginx default page
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx || sudo systemctl start nginx

echo "=== [4/7] Open firewall ports ==="
# Oracle OS-level firewall (nftables / iptables)
if command -v ufw &>/dev/null; then
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    sudo ufw --force enable
elif command -v firewall-cmd &>/dev/null; then
    sudo firewall-cmd --permanent --add-service=http
    sudo firewall-cmd --permanent --add-service=https
    sudo firewall-cmd --reload
else
    # Fall back to iptables
    sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || \
        sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
    sudo iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || \
        sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT
fi

echo "=== [5/7] Install systemd service ==="
sudo cp "$REPO/ops/seacommons-api.service" /etc/systemd/system/seacommons-api.service
sudo systemctl daemon-reload
sudo systemctl enable seacommons-api

echo "=== [6/7] Check /etc/seacommons.env exists ==="
if [ ! -f /etc/seacommons.env ]; then
    echo ""
    echo "  ERROR: /etc/seacommons.env does not exist."
    echo "  Create it from ops/.env.production.example:"
    echo "    sudo cp $REPO/ops/.env.production.example /etc/seacommons.env"
    echo "    sudo nano /etc/seacommons.env   # fill in real values"
    echo "    sudo chmod 600 /etc/seacommons.env"
    echo ""
    exit 1
fi
sudo chmod 600 /etc/seacommons.env

echo "=== [7/7] Restart API service ==="
sudo systemctl restart seacommons-api
sleep 4
sudo systemctl status seacommons-api --no-pager

echo ""
echo "=== Health check ==="
curl -sf http://127.0.0.1:8000/health && echo "  Backend OK" || echo "  FAILED — check: sudo journalctl -u seacommons-api -n 50"
curl -sf http://127.0.0.1/health      && echo "  Nginx proxy OK" || echo "  FAILED — check nginx logs"
echo ""
echo "Done. Tail logs with:"
echo "  sudo journalctl -u seacommons-api -f"
