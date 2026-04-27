#!/usr/bin/env bash
# First-boot setup for SuezCanal edge node on Raspberry Pi
set -euo pipefail

echo "==> SuezCanal edge node first-boot setup"

# System update
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  python3 python3-pip python3-venv git curl \
  libspi-dev i2c-tools libusb-1.0-0 \
  rtl-sdr dump1090-mutability \
  redis-server docker.io docker-compose

# Enable SPI and I2C for sensors
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0

# Clone and install SuezCanal
cd /opt
sudo git clone https://github.com/your-org/suezcanal.xyz suezcanal
cd suezcanal
sudo python3 -m venv .venv
sudo .venv/bin/pip install -e ".[core]"

# Install systemd service
sudo cp edge/firmware/suezcanal.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now suezcanal

echo "==> First-boot complete. SuezCanal running at http://$(hostname -I | cut -d' ' -f1):8000"
