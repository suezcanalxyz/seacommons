# SeaCommons

**Open maritime data infrastructure for public-interest situational awareness, research and reproducible analysis.**

SeaCommons is an AGPL-licensed open-source interoperability stack for ingesting, normalising, analysing and publishing heterogeneous maritime information. It combines vessel observations, public-source reports, environmental and ocean data, drift modelling and provenance-aware outputs behind common API and event contracts.

The project originated in Mediterranean civil-society and maritime research contexts, but the reusable core is intended for independent deployments by researchers, NGOs, civic-technology teams and other public-interest actors.

> **Safety and scope:** SeaCommons is research and public-interest infrastructure. It is not a replacement for official SAR/MRCC/GMDSS channels. Public Live deliberately suppresses private messages, personal identifiers and sensitive/exact locations unless an explicit publication decision allows their release.

Licensed under **AGPL-3.0-or-later**.

## Links

- Institutional site: `https://seacommons.org/`
- Operational map: `https://live.seacommons.org/`
- Public demo: `https://play.seacommons.org/`
- Repository: `https://github.com/suezcanalxyz/seacommons`

## What SeaCommons does

SeaCommons is being developed as a reusable maritime interoperability layer rather than a single closed dashboard.

```text
Official X API ───────┐
AIS / vessel data ────┤
Ocean + weather ──────┤
Partner webhooks ─────┼──> connectors / normalisation
Community intake ─────┤              │
Sensors / NMEA ───────┘              ▼
                           SeaCommons event contracts
                                      │
                           provenance + verification
                                      │
                                      ▼
                              FastAPI core API
                         ┌────────────┼────────────┐
                         ▼            ▼            ▼
                     PostGIS       workers     drift models
                         │            │            │
                         └────────────┼────────────┘
                                      ▼
                         privacy/publication policy
                                      │
                         ┌────────────┼────────────┐
                         ▼            ▼            ▼
                      Live API      Web UI      external clients
```

The long-term goal is for external applications to consume SeaCommons data contracts and analytical components without requiring the SeaCommons web interface.

## Current capabilities

The repository already includes:

- **FastAPI backend** with a versioned HTTP API;
- **React/Vite operational console** with MapLibre/Cesium-based geospatial interfaces;
- **PostgreSQL/PostGIS** production support, with SQLite for local development;
- **AISStream** integration and vessel tracking components;
- **official X API v2 recent-search ingestion**, implemented and activated when a Bearer Token is configured;
- **Telegram, WhatsApp and signed partner-webhook ingestion** paths;
- **Copernicus Marine (CMEMS)** integration for ocean data;
- **OpenDrift** trajectory modelling with deterministic fallback behaviour;
- **versioned JSON contracts** for SeaCommons events, live signals, environment snapshots and drift scenes;
- **privacy-preserving public Live projection** separating operational/private data from publishable signals;
- **forensic and provenance-oriented components** for derived outputs;
- **edge/public gateway code** and separate operational/demo deployment paths;
- **automated tests and GitHub Actions CI** for the API, web application and edge runtime;
- optional sensor, NMEA, TimeZero and immersive/Unreal experiments.

Not every component has the same stability level. The repository is currently undergoing a consolidation phase to make the reusable open core, supported adapters and experimental/operator-specific modules explicit.

See [`docs/GRANT_READINESS_AUDIT_2026-08-19.md`](./docs/GRANT_READINESS_AUDIT_2026-08-19.md) for the current repository audit and preparation roadmap.

## Public Live

The canonical public projection is exposed under:

```text
GET /api/v1/live/signals
GET /api/v1/live/sources
```

Live is designed around publication and privacy rules rather than mirroring every internally ingested event. Raw private distress messages, sender identifiers and sensitive coordinates are not automatically exposed.

### Real X data

SeaCommons already contains an official X API connector using the X API v2 recent-search endpoint. It is enabled by configuring a server-side Bearer Token:

```env
TWITTER_BEARER_TOKEN=...
INTEL_ENABLED=true
INTEL_MONITORS_ENABLED=true
```

The connector polls curated maritime/SAR queries, tracks upstream post IDs, normalises source metadata and deduplicates events before they enter the intelligence store.

**Current preparation milestone:** production-validate this connector against the public Live pipeline and expose explicit connector freshness/health. Until a credentialed production deployment has been verified, the repository should not claim that X is continuously supplying the public Live endpoint.

A streaming X adapter may be evaluated later for lower latency, while keeping the same normalised SeaCommons event boundary.

## Event contracts

SeaCommons already maintains versioned contracts under [`docs/contracts/`](./docs/contracts/), including:

```text
docs/contracts/seacommons-event-v1.schema.json
docs/contracts/live-signal-v1.schema.json
docs/contracts/environment-snapshot-v1.schema.json
docs/contracts/drift-scene-v1.schema.json
```

The next core refactor will make the SeaCommons event contract the canonical boundary between upstream transports/connectors and downstream storage, analysis and publication.

A connector should ultimately be responsible only for:

```text
fetch / receive
      ↓
validate
      ↓
normalise
      ↓
SeaCommons event
```

Transport-specific rules should not leak into the rest of the platform.

## Repository layout

```text
apps/
  api/        FastAPI backend, ingestion, drift, intel and integrations
  web/        React/Vite operational and public geospatial clients
  edge/       optional edge/public gateway
  site/       institutional site
  unreal/     experimental immersive client

docs/
  contracts/  versioned data contracts
  *.md        architecture, deployment, research and historical runbooks

deploy/       container/reverse-proxy/runtime deployment assets
ops/          production service configuration examples
scripts/      developer and deployment entrypoints
tests/        Python integration/unit tests
```

This remains a monorepo for now. The preparation work will establish stable internal package/adaptor boundaries before deciding whether any component deserves an independent repository.

## Quickstart

Clone the repository and create a local environment file:

```bash
git clone https://github.com/suezcanalxyz/seacommons.git
cd seacommons
cp .env.example .env
```

For the full Docker stack:

```bash
docker compose -f deploy/docker-compose.yml up -d
```

Local endpoints are typically:

```text
Web console: http://localhost:3000
API:         http://localhost:8000
API docs:    http://localhost:8000/docs
```

For local development without Docker:

```bash
bash scripts/run_dev.sh all
```

See the deployment documentation under [`docs/`](./docs/) for production and edge-specific setups.

## Drift and environmental data

SeaCommons integrates OpenDrift and contains a CMEMS data adapter. Drift computation is being moved toward a reproducible pipeline in which every result can state:

- model and version;
- environmental forcing sources;
- observation/model timestamps;
- uncertainty and limitations;
- transformation/provenance metadata.

The grant-preparation roadmap prioritises making this reproducibility explicit and separating durable worker execution from API request lifecycle concerns.

## Development priorities

The current preparation sequence is:

1. **Repository hygiene** — remove duplicate runtime paths, generated data and legacy naming ambiguity.
2. **Canonical events and connectors** — make a stable event schema and connector interface the core boundary.
3. **Real-data Live validation** — demonstrate privacy-safe real data from at least two independent upstream sources, including the official X API path.
4. **Drift + provenance** — strengthen operational environmental forcing, uncertainty and reproducibility.
5. **Contributor-facing open core** — connector documentation, SDK/examples and additional GIS clients after contracts stabilise.

The objective is not to add features for their own sake. It is to make SeaCommons understandable, installable, extensible and independently reusable as open maritime infrastructure.

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md).

Before opening a pull request, the current baseline checks are:

```bash
python -m pytest -q

cd apps/web
npm run lint
npm run test:simulation
npm run build

cd ../edge
npm test
```

New analytical outputs should document their source, timestamp, model/version, uncertainty and limitations. Never commit credentials, personal data, live distress locations or unredacted operational exports.

## Funding preparation

SeaCommons is being prepared for open-source/public-interest infrastructure funding. Appropriate funded work should strengthen reusable components such as interoperability, data contracts, connector tooling, provenance, reproducible drift analysis, documentation and independent deployment — not create a closed or single-operator product.

A detailed technical audit and proposed preparation sprints are maintained in [`docs/GRANT_READINESS_AUDIT_2026-08-19.md`](./docs/GRANT_READINESS_AUDIT_2026-08-19.md).

## License

SeaCommons is licensed under **AGPL-3.0-or-later**.
