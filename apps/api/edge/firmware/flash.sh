#!/usr/bin/env bash
# Flash Raspberry Pi SD card with Raspberry Pi OS Lite
set -euo pipefail
DEVICE="${1:-/dev/sdb}"
IMAGE_URL="https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2024-03-15/2024-03-15-raspios-bookworm-arm64-lite.img.xz"
IMAGE="/tmp/rpi-os.img.xz"
echo "==> Downloading Raspberry Pi OS..."
wget -qO "$IMAGE" "$IMAGE_URL"
echo "==> Flashing $DEVICE..."
xz -dc "$IMAGE" | sudo dd of="$DEVICE" bs=4M status=progress conv=fsync
echo "==> Enabling SSH..."
sudo mount "${DEVICE}1" /mnt/boot
sudo touch /mnt/boot/ssh
echo "SUEZCANAL_EDGE=true" | sudo tee /mnt/boot/suezcanal.env
sudo umount /mnt/boot
echo "==> Done. Insert SD card and boot Raspberry Pi."
echo "    Default SSH: pi@raspberrypi.local"
