# SeaCommons

**Open-source coordination infrastructure for maritime search and rescue.**

SeaCommons brings distress alerts, vessel information, environmental data, drift predictions and traceable incident records into a shared maritime operational picture.

[Project page](https://www.suezcanal.xyz/tools/seacommons/) · [Live console](https://www.suezcanal.xyz/seacommons/) · [API documentation](http://localhost:8000/docs) · [Contributing](./CONTRIBUTING.md)

> **Current status:** active pilot and research infrastructure. SeaCommons is not a replacement for official maritime rescue authorities, certified navigation systems or emergency procedures.

## Why SeaCommons

Maritime rescue information is often fragmented across calls, messages, vessel feeds, maps and separate operational systems. SeaCommons is designed to help teams consolidate these signals into a shared, time-aware and auditable environment.

A typical SeaCommons workflow is:

```text
Distress signal
      ↓
Structured alert and geolocation
      ↓
Vessel, weather and operational context
      ↓
Drift trajectory modelling
      ↓
Shared operational picture
      ↓
Traceable forensic record
```

## Core capabilities

- **Distress alert management** — structure coordinates, timestamps, persons at risk and vessel information.
- **Common Operational Picture (COP)** — combine alerts, vessels, weather and operational layers in one map-first interface.
- **Drift trajectory modelling** — run OpenDrift `Leeway` simulations or a lightweight Gaussian fallback for public demos.
- **Vessel and OSINT awareness** — ingest and display operationally relevant maritime and open-source signals.
- **Forensic documentation** — create signed, traceable incident records and witness packets.
- **Pilot deployment** — run a low-cost independent dashboard with Docker.
- **Optional edge sensing** — connect research-oriented onboard sensing nodes for AIS, RF, acoustic and environmental observations.

## Capability status

| Capability | Status |
| --- | --- |
| Distress alert ingestion | Available |
| Map-first operational dashboard | Available |
| Vessel and alert layers | Available |
| Weather layer | Available |
| Synthetic public demo mode | Available |
| OpenDrift with configurable constant forcing | Available |
| Live CMEMS / ERA5 forcing | Planned |
| Messaging-platform ingestion | Planned / prototype area |
| Navigation-software interoperability | Planned / research area |
| Hardware sensing node | Research module |

## Repository layout

```text
apps/
  api/        FastAPI backend, drift engine, forensic and integrations
  web/        React/Vite operational console
deploy/       Docker, Render and hosting manifests
docs/         Methodology, governance and deployment notes
scripts/      Local developer entrypoints
```

## Fastest local pilot

The pilot stack is the recommended starting point for contributors and demonstrations.

```bash
git clone https://github.com/suezcanalxyz/seacommons.git
cd seacommons
cp .env.example .env
docker compose -f deploy/docker-compose.pilot.yml up --build
```

Pilot services:

- Dashboard: `http://localhost:3000`
- API: `http://localhost:8000`
- Interactive API docs: `http://localhost:8000/docs`

The dashboard is separate from the public project site and uses a small polling surface. When published on the Suez Canal domain, the recommended public path is `/seacommons/`.

Primary pilot endpoints:

- `/api/v1/ops/summary`
- `/api/v1/vessels`
- `/api/v1/alerts/geojson`
- `/api/v1/weather`
- `/api/v1/alert`

## Full stack with Docker

Some modules require additional system libraries:

```bash
sudo apt-get install gcc g++ libcurl4-openssl-dev libgeos-dev

git clone https://github.com/suezcanalxyz/seacommons.git
cd seacommons
cp .env.example .env
docker compose -f deploy/docker-compose.yml up -d
```

The Common Operational Picture will be available at `http://localhost:3000` and the API at `http://localhost:8000`.

## Local development without Docker

```bash
bash scripts/run_dev.sh all
```

This starts:

- API from `apps/api`
- console from `apps/web`

## Public demo deployment

For a hosted public demo, do not rely on same-origin API guessing.

```env
VITE_API_BASE=https://your-api-host
MOCK=true
DEMO_PUBLIC_MODE=true
```

`DEMO_PUBLIC_MODE` keeps the API lightweight and allows SAR cases to use the Gaussian fallback when a hosted demo does not have a full OpenDrift runtime.

A starter Render blueprint is included in [`deploy/render.yaml`](./deploy/render.yaml). For a zero-cost live demo, the recommended path is:

- frontend on Cloudflare Pages;
- backend on Oracle Cloud Always Free.

See [`docs/DEPLOY_CLOUDFLARE_ORACLE.md`](./docs/DEPLOY_CLOUDFLARE_ORACLE.md).

## OpenDrift runtime

The backend can call a real OpenDrift `Leeway` simulation through a dedicated Python interpreter. The practical setup is:

- the API can keep running on the local default Python;
- OpenDrift is installed on Python 3.12;
- `OPENDRIFT_PYTHON` points to that interpreter.

The current integration uses real trajectories with configurable constant forcing:

- `OPENDRIFT_WIND_X`
- `OPENDRIFT_WIND_Y`
- `OPENDRIFT_CURRENT_X`
- `OPENDRIFT_CURRENT_Y`
- `OPENDRIFT_PARTICLES`
- `OPENDRIFT_TIMESTEP_SECONDS`
- `OPENDRIFT_OUTPUT_SECONDS`

Live CMEMS / ERA5 ocean and atmospheric readers are a planned next step. Results produced with constant forcing or demo fallback modes must not be represented as operational forecasts.

## Test with a synthetic distress alert

Use fictional or anonymised data only.

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

This enqueues a drift calculation, creates a signed forensic packet and broadcasts it to configured witness endpoints.

## Optional ship sensing node

SeaCommons also explores low-cost onboard sensing nodes as a separate research module. A full node may include Raspberry Pi compute, AIS/RF reception, infrasound, accelerometry and optional underwater acoustics. Hardware specifications and costs should be treated as research references rather than a certified maritime system.

## Safety, privacy and limitations

SeaCommons can process highly sensitive operational and personal information. Deployers are responsible for access control, data minimisation, retention policies, legal compliance and the protection of people in distress.

Do not expose real distress cases through the public demo. Do not use SeaCommons as the sole basis for navigation, rescue decisions or emergency response. Review [`SECURITY.md`](./SECURITY.md) before deploying a publicly reachable instance.

## Contributing

Contributions are welcome from software developers, SAR practitioners, cartographers, oceanographers, designers, translators, legal researchers, data-protection specialists and humanitarian organisations.

Start with [`CONTRIBUTING.md`](./CONTRIBUTING.md). Useful contribution areas include:

- deployment and documentation;
- accessibility and low-bandwidth interfaces;
- multilingual support;
- drift-model validation and environmental data readers;
- maritime-system interoperability;
- security and threat modelling;
- ethical governance and data-retention practices;
- synthetic rescue scenarios for testing and training.

## Governance and responsible use

SeaCommons is developed as open-source civic and humanitarian infrastructure. Technical contributions should support traceability, interoperability, human oversight and the safety and dignity of people at sea.

## License

SeaCommons is licensed under the [GNU Affero General Public License v3.0](./LICENSE).