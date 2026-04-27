#!/usr/bin/env bash
# Install NMEA bridge as systemd service on Raspberry Pi / Linux
set -euo pipefail
echo "==> Installing SuezCanal NMEA bridge"
python3 -m pip install pyserial
cat > /etc/systemd/system/suezcanal-nmea.service << 'EOF'
[Unit]
Description=SuezCanal NMEA Bridge
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/suezcanal
EnvironmentFile=/opt/suezcanal/.env
ExecStart=/opt/suezcanal/.venv/bin/python connect/nmea_bridge.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now suezcanal-nmea
echo "==> NMEA bridge service installed and started."
systemctl status suezcanal-nmea --no-pager
