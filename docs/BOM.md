# Bill of Materials — SuezCanal Edge Node

> Minimum hardware kit for a fully autonomous maritime SAR + threat-detection node.
> All components run on 12V DC (boat/vehicle power) or 230V shore power via PSU.

## Core Computing

| Component | Model | Purpose | Cost (est.) |
|-----------|-------|---------|-------------|
| SBC | Raspberry Pi 5 8GB | Main compute / API / core | ~$80 |
| Storage | Samsung 1TB NVMe + USB3 adapter | SQLite forensic log, tile cache | ~$90 |
| UPS HAT | Waveshare UPS HAT (C) | Power continuity | ~$35 |
| Case | Argon ONE M.2 | Passive cooling + NVMe slot | ~$25 |

## RF / SDR

| Component | Model | Purpose | Cost (est.) |
|-----------|-------|---------|-------------|
| SDR | RTL-SDR V4 (R828D) | AIS + ADS-B + general scan | ~$40 |
| SDR (secondary) | Airspy HF+ Discovery | HF/VHF ionospheric | ~$170 |
| AIS antenna | Shakespeare 5101 | Dedicated AIS receive | ~$30 |
| ADS-B antenna | 1090 MHz FA antenna | Aircraft tracking | ~$20 |
| LNA | Nooelec Nano 3 | Improve weak signal | ~$20 |

## Seismic / Infrasound

| Component | Model | Purpose | Cost (est.) |
|-----------|-------|---------|-------------|
| Geophone | SM-24 Geophone (4.5Hz) | Ground vibration / seismic | ~$25 |
| ADC | ADS1256 24-bit HAT | Geophone digitisation | ~$30 |
| Infrasound mic | Raspberry Boom | Infrasound 0.1–20 Hz | ~$85 |

## GNSS

| Component | Model | Purpose | Cost (est.) |
|-----------|-------|---------|-------------|
| GNSS receiver | U-blox ZED-F9P | Multi-band GNSS, spoofing detection | ~$220 |
| Antenna | ANN-MB-00 survey antenna | High-precision GNSS | ~$50 |

## Connectivity

| Component | Model | Purpose | Cost (est.) |
|-----------|-------|---------|-------------|
| LTE modem | Waveshare SIM7600G HAT | Cellular uplink (4G/LTE) | ~$80 |
| SIM | Any maritime / roaming | Data plan | varies |
| WiFi | Alfa AWUS036AXML | 802.11ax long range | ~$45 |
| Ethernet | CAT6 passthrough | LAN fallback | ~$10 |

## Optional / Enhanced

| Component | Model | Purpose | Cost (est.) |
|-----------|-------|---------|-------------|
| LoRa HAT | RAK2287 | Off-grid mesh comms | ~$90 |
| Hydrophone | DolphinEar DE200 | Underwater explosion detection | ~$120 |
| Thermal camera | Seek Compact Pro | Night SAR visual | ~$300 |
| Satellite modem | RockBLOCT 9603 | Iridium fallback comms | ~$250 |

## Total (core kit, no optional)

~**$700–800 USD** per node.

---

## Assembly Notes

1. Flash Raspberry Pi OS Lite (64-bit, no desktop).
2. Run `edge/firmware/firstboot.sh` to install all dependencies.
3. Set env vars in `/etc/suezcanal.env` (see `.env.example`).
4. Deploy via `docker compose -f deploy/docker-compose.ship.yml up -d`.
5. Verify: `suezcanal sensors status` — all sensors should show MOCK or LIVE.

Power budget: ~15W average draw at full operation. 12V/3A supply recommended.
