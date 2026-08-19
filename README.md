# SeaCommons

**Open maritime infrastructure for fleets, live vessel operations, public-interest situational awareness and reproducible ocean analysis.**

SeaCommons is an AGPL-licensed open-source maritime platform for ingesting, normalising, analysing and publishing heterogeneous maritime information. It combines fleet and vessel tracking, public-source reports, environmental and ocean data, drift modelling and provenance-aware outputs behind common API and event contracts.

SeaCommons originated from a Central Mediterranean case study, where fragmented maritime information, SAR activity, vessel movements and environmental data make interoperability especially visible as a problem. **The Central Mediterranean is the first proving ground, not the boundary of the software.** The reusable core is designed to support any maritime deployment that can benefit from open vessel, fleet, geospatial, environmental or incident infrastructure.

> **Safety and scope:** SeaCommons is research, operational-support and public-interest infrastructure. It is not a replacement for official SAR/MRCC/GMDSS channels. Public Live deliberately suppresses private messages, personal identifiers and sensitive/exact locations unless an explicit publication decision allows their release.

Licensed under **AGPL-3.0-or-later**.

## Links

- Institutional site: `https://seacommons.org/`
- Operational map: `https://live.seacommons.org/`
- Public demo: `https://play.seacommons.org/`
- Repository: `https://github.com/suezcanalxyz/seacommons`

## Product direction

SeaCommons is being developed as an **open maritime operating layer**, not as a Mediterranean-only dashboard.

A deployment should be able to:

- register and manage a fleet;
- attach vessels by MMSI, IMO or internal identity;
- track owned or selected vessels in real time where a configured data source permits it;
- expose fleet state, last position, source freshness and vessel history through one API;
- ingest additional maritime observations and incidents through replaceable adapters;
- combine vessel data with weather, ocean and drift information;
- publish privacy-safe operational or public views;
- run independently on infrastructure controlled by the deploying organisation.

This means the same open core should be useful to a research group, NGO, sailing or expedition fleet, marine observatory, port-adjacent project, environmental monitoring programme, cultural/research institution or other maritime operator without requiring Central Mediterranean-specific logic.

## Architecture

```text
Fleet / vessel registry ─┐
AIS / vessel sources ────┤
Public-source reports ───┤
Ocean + weather ─────────┤
Partner webhooks ────────┼──> connectors / normalisation
Community intake ────────┤              │
Sensors / NMEA ──────────┘              ▼
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

The long-term goal is for external applications to consume SeaCommons fleet, event and analytical contracts without requiring the SeaCommons web interface.

## Core domains

SeaCommons should converge around a small set of reusable domains:

### Fleet

```text
Fleet
  └── Vessel
       ├── identifiers
       ├── metadata
       ├── latest position
       ├── track history
       ├── source freshness
       └── optional operational state
```

Fleet membership is application-owned state. Vessel observations may arrive from AISStream or other configured providers, but the SeaCommons domain must not be coupled to one AIS vendor.

### Maritime events

Observations, incidents, alerts and other source records should enter one canonical SeaCommons event model with source, time, geometry, provenance and publication metadata.

### Environment

Weather, currents, waves and other environmental data should enrich maritime state through replaceable providers rather than becoming provider-specific UI logic.

### Analysis

OpenDrift and future analytical modules consume canonical events/environment data and return reproducible derived products with explicit model version, forcing sources, timestamps, uncertainty and provenance.

## Current capabilities

The repository already includes:

- **FastAPI backend** with a versioned HTTP API;
- **React/Vite operational console** with MapLibre/Cesium-based geospatial interfaces;
- **PostgreSQL/PostGIS** production support, with SQLite for local development;
- **AISStream** integration and vessel tracking components;
- **X/Twitter ingestion paths**, including an official API adapter and an optional session-based adapter under consolidation;
- **Telegram, WhatsApp and signed partner-webhook ingestion** paths;
- **Copernicus Marine (CMEMS)** integration for ocean data;
- **OpenDrift** trajectory modelling;
- **versioned JSON contracts** for SeaCommons events, live signals, environment snapshots and drift scenes;
- **privacy-preserving public Live projection** separating operational/private data from publishable signals;
- **forensic and provenance-oriented components** for derived outputs;
- **edge/public gateway code** and separate operational/demo deployment paths;
- **automated tests and GitHub Actions CI** for the API, web application and edge runtime;
- optional sensor, NMEA, TimeZero and immersive/Unreal experiments.

Not every component has the same stability level. The repository is currently undergoing a consolidation phase to make the reusable open core, supported adapters and experimental/operator-specific modules explicit.

See [`docs/GRANT_READINESS_AUDIT_2026-08-19.md`](./docs/GRANT_READINESS_AUDIT_2026-08-19.md) and [`docs/PRODUCT_SCOPE.md`](./docs/PRODUCT_SCOPE.md).

## Public Live

The canonical public projection is exposed under:

```text
GET /api/v1/live/signals
GET /api/v1/live/sources
```

Live is designed around publication and privacy rules rather than mirroring every internally ingested event. Raw private messages, sender identifiers and sensitive coordinates are not automatically exposed.

The public Live view is one client of the SeaCommons core. It must not define the entire product model. Fleet operations, vessel state and private organisational views can exist independently of public publication.

## Event contracts

SeaCommons already maintains versioned contracts under [`docs/contracts/`](./docs/contracts/), including:

```text
docs/contracts/seacommons-event-v1.schema.json
docs/contracts/live-signal-v1.schema.json
docs/contracts/environment-snapshot-v1.schema.json
docs/contracts/drift-scene-v1.schema.json
```

The core refactor will make SeaCommons contracts the canonical boundary between upstream transports/connectors and downstream storage, analysis and publication.

A connector should ultimately be responsible only for:

```text
fetch / receive
      ↓
validate
      ↓
normalise
      ↓
SeaCommons domain event / observation
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
  *.md        architecture, product scope, deployment and research notes
deploy/       container/reverse-proxy/runtime deployment assets
ops/          production service configuration examples
scripts/      developer and deployment entrypoints
tests/        Python integration/unit tests
```

This remains a monorepo for now. Stable internal package/adapter boundaries should be established before deciding whether any component deserves an independent repository.

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

## Development priorities

The current preparation sequence is:

1. **Repository reduction** — remove duplicate runtime paths, generated data, dead code and naming ambiguity.
2. **Fleet + vessel core** — make fleet membership and provider-independent vessel identity/position first-class domains.
3. **Canonical events and connectors** — one event boundary for source adapters, provenance and publication.
4. **Real-data vertical slice** — demonstrate real vessel tracking plus at least one public-source/event path through the canonical API.
5. **Environment + drift** — strengthen CMEMS/weather integration, reproducibility and uncertainty.
6. **Contributor-facing open core** — connector documentation, SDK/examples and additional GIS clients after contracts stabilise.

The objective is not to reproduce commercial fleet-management suites feature-for-feature. For the preparation phase and an approximately €40k open-source funding scope, priority goes to the reusable substrate: fleet/vessel identity, provider-independent observations, event contracts, connector interfaces, real-time state, provenance, deployment and a convincing reference implementation.

## Funding preparation

SeaCommons is being prepared as an open-source maritime infrastructure cluster. Its first case study is the Central Mediterranean, but funded work should create components that remain useful across maritime contexts.

A coherent first funding scope should strengthen a compact reusable core rather than attempt every possible maritime feature at once. Appropriate outputs include:

- fleet and vessel domain model;
- real-time vessel observation pipeline;
- canonical maritime event contracts;
- replaceable source adapters;
- source health/freshness;
- privacy/publication policy;
- environmental enrichment;
- reproducible drift analysis;
- deployment documentation and reference clients.

Central Mediterranean SAR/public-source monitoring remains an important reference deployment and stress test, not a hard-coded product boundary.

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

## License

SeaCommons is licensed under **AGPL-3.0-or-later**.
