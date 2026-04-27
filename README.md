# Seacommons Console

Open-source maritime rescue and awareness platform bridging real-time distress signals, Lagrangian trajectory modelling, and forensic documentation.

Licensed under AGPL-3.0.

## Links

- Project page: `https://www.suezcanal.xyz/tools/seacommons/`
- Live console path: `https://www.suezcanal.xyz/seacommons/`
- Repository: `https://github.com/suezcanalxyz/seacommons`

## Repository Layout

```text
apps/
  api/        FastAPI backend, drift engine, forensic and integrations
  web/        React/Vite operational console
deploy/       Docker, Render and hosting manifests
docs/         Methodology, governance and deployment notes
scripts/      Local developer entrypoints
```

## Quickstart

Install and run the full stack in 3 commands:

```bash
# Install system dependencies (required for TID module)
sudo apt-get install gcc g++ libcurl4-openssl-dev libgeos-dev

git clone https://github.com/suezcanalxyz/seacommons.git
cd seacommons
cp .env.example .env
docker compose -f deploy/docker-compose.yml up -d
```

The Common Operational Picture (COP) will be available at `http://localhost:3000`.
The API will be available at `http://localhost:8000`.

## Pilot Runtime

The current repository is most reliable in low-cost pilot mode with an independent Seacommons dashboard.

Recommended startup:

```powershell
docker compose -f deploy/docker-compose.pilot.yml up --build
```

Pilot URLs:

- Dashboard: `http://localhost:3000`
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

The dashboard is separate from the public site and uses a small polling surface. When published on the Suez Canal domain, the recommended public path is `/seacommons/`.

- `/api/v1/ops/summary`
- `/api/v1/vessels`
- `/api/v1/alerts/geojson`
- `/api/v1/weather`
- `/api/v1/alert`

## Public Demo

For a hosted public demo, do not rely on same-origin API guessing.

- Frontend: set `VITE_API_BASE=https://your-api-host`
- Backend: set `MOCK=true`
- Backend: set `DEMO_PUBLIC_MODE=true`

`DEMO_PUBLIC_MODE` keeps the API lightweight and allows SAR cases to use the Gaussian fallback when a hosted demo does not have a full OpenDrift runtime available.

A starter Render blueprint is included in [deploy/render.yaml](./deploy/render.yaml). Render still needs this folder in a Git repository or a published image source before it can deploy the stack.

For a zero-cost live demo, the recommended path is:

- frontend on Cloudflare Pages
- backend on Oracle Cloud Always Free

See [docs/DEPLOY_CLOUDFLARE_ORACLE.md](./docs/DEPLOY_CLOUDFLARE_ORACLE.md).

## Local Dev Without Docker

```bash
bash scripts/run_dev.sh all
```

This starts:

- API from `apps/api`
- console from `apps/web`

## OpenDrift Runtime

The backend can call a real OpenDrift `Leeway` simulation through a dedicated Python interpreter.

In this repository the practical setup is:

- API/backend can keep running on the local default Python
- OpenDrift is installed on Python 3.12
- `OPENDRIFT_PYTHON` points to that interpreter

The current integration uses real OpenDrift trajectories with configurable constant forcing:

- `OPENDRIFT_WIND_X`
- `OPENDRIFT_WIND_Y`
- `OPENDRIFT_CURRENT_X`
- `OPENDRIFT_CURRENT_Y`
- `OPENDRIFT_PARTICLES`
- `OPENDRIFT_TIMESTEP_SECONDS`
- `OPENDRIFT_OUTPUT_SECONDS`

This is a real trajectory engine, but it is not yet using live CMEMS/ERA5 readers. That should be the next step when you want ocean and atmosphere forcing from operational datasets.

## Hardware Bill of Materials (BOM) — Full Ship Node

| Component | Cost | Function |
| :--- | :--- | :--- |
| Raspberry Pi 4 (4GB) | ~€55 | Main compute |
| RTL-SDR v4 dongle | ~€35 | RF / drone detection |
| VHF antenna (marine) | ~€25 | AIS + RF |
| Raspberry Boom HAT (OSOP) | ~€180 | Infrasound 0.05–20 Hz |
| ADXL355 accelerometer (SPI) | ~€15 | Hull-coupled seismic |
| Piezoelectric hydrophone | ~€50 | Underwater acoustic (optional) |
| MCP3208 ADC | ~€5 | Only if not using Boom HAT |
| SSD 256GB USB | ~€30 | Storage |
| IP65 case | ~€20 | Marine environment |
| **Total (with Boom HAT)** | **~€410** | **Complete node** |
| **Total (DIY boom, no HAT)** | **~€240** | **Budget version** |

## Test with Fake Alert

To test the full pipeline, submit a mock distress signal:

```bash
curl -X POST http://localhost:8000/api/v1/alert \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 35.123,
    "lon": 15.456,
    "timestamp": "2026-03-21T12:00:00Z",
    "persons": 45,
    "vessel_type": "rubber_boat",
    "domain": "ocean_sar"
  }'
```

This will enqueue a drift calculation task, sign the forensic packet, and broadcast it to the configured witness endpoints.
