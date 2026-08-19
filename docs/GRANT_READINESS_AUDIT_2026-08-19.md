# SeaCommons Grant-Readiness Repository Audit

Date: 19 August 2026  
Status: initial preparation audit for open-source funding readiness

## Executive summary

SeaCommons already contains substantial working infrastructure: a FastAPI backend, React/Vite operational console, geospatial interfaces, PostgreSQL/PostGIS support, OpenDrift integration, CMEMS support, AIS ingestion, public/private live-feed separation, forensic/provenance components, tests and CI. It should therefore be presented as an existing open-source infrastructure project that needs consolidation and clearer module boundaries, not as an MVP that needs to be invented.

The principal preparation task before an NLnet-style call is to reduce architectural ambiguity and make the reusable open core obvious. At present, the repository mixes production runtime code, experimental integrations, deployment history, public web proxies, edge code, Unreal work, operational monitoring and research tooling in a single tree. Several modules have become de facto monoliths, and there are concrete duplicate runtime files.

The recommended target is a grant-ready monorepo with one canonical backend, one canonical Live path, one explicit event contract, documented connector interfaces and optional adapters around the core.

## Current strengths

- Public AGPL-3.0-or-later repository.
- FastAPI backend with a real API surface.
- React/Vite operational web application.
- PostgreSQL/PostGIS production path with SQLite retained for local development.
- OIDC/authentication, object storage, cache and deployment tooling represented.
- OpenDrift integration exists and CMEMS integration is already present.
- AISStream integration and vessel registry are implemented.
- A versioned SeaCommons event schema already exists under `docs/contracts/`.
- A privacy-preserving public Live projection already exists.
- Forensic/provenance components already exist.
- Automated tests cover Live, security, drift, AIS and X/Twikit behaviour.
- GitHub Actions runs Python tests, web lint/simulation/build and edge tests.

These features give the project a much stronger funding position than a conceptual proposal. The preparation phase should expose this maturity rather than add more disconnected features.

## High-priority findings

### 1. Duplicate public API proxy code

`api/live.js` and `apps/web/api/live.js` are currently the exact same Git blob. This is hard duplication and should be eliminated. `api/proxy.js` and `apps/web/api/proxy.js` are also parallel implementations and should be compared and consolidated.

Recommended action:

- choose one canonical edge/serverless location;
- make the other deployment consume or build from that source;
- add a CI guard for exact duplicate source files in critical runtime paths.

### 2. Large generated/runtime data is committed

`apps/api/core/db/data/integration_events.jsonl` is approximately **33.7 MB** and tracked inside the application source tree.

This should not be part of the reusable core unless it is deliberately curated test data with a documented licence and purpose.

Recommended action:

- determine whether it is a fixture, operational data or generated state;
- if operational/generated, remove it from the active source tree and add the runtime path to `.gitignore`;
- if a fixture is useful, replace it with a small anonymised deterministic sample under `tests/fixtures/`;
- consider history cleanup separately if repository weight warrants it.

### 3. Package identity still carries legacy Suez Canal naming

`apps/api/pyproject.toml` currently declares the package as `suezcanal`, version `1.0.0`, and describes it as `SuezCanal.xyz`. The settings class is also named `SuezCanalConfig`.

Recommended action:

- rename the distributable package/project identity to `seacommons` or an explicit package such as `seacommons-core`;
- keep Suez Canal Republic as a deployment/use-case lineage rather than the software namespace;
- define an explicit release/versioning policy;
- reconsider the `1.0.0` claim while public contracts and module boundaries are still changing.

### 4. X/Twitter has competing ingestion strategies

The repository currently contains:

- `core/intel/twitter_monitor.py`: official X API v2 recent-search polling using a Bearer Token;
- `core/intel/twikit_monitor.py`: a large account-session/cookie based monitor with custom polling, reply tracking, media handling and publication logic;
- `core/ingestion/parsers/twitter.py`: a separate parsing path.

The official monitor is comparatively small, auditable and suitable as a documented supported connector. The Twikit monitor is operationally sophisticated, but it brings account-session fragility, policy risk, a large test surface and a second semantic path for the same upstream platform.

Recommended grant-ready position:

- make the **official X API connector** the canonical supported X integration;
- retain Twikit only behind an explicit `experimental` / `operator-adapter` boundary, or later move it to an optional package;
- unify parsing and normalisation after transport so both sources emit the same SeaCommons event contract;
- do not let transport-specific code determine platform-wide publication semantics.

### 5. The official X connector already provides the basis for a real-data Live feed

`twitter_monitor.py` already calls the official `https://api.x.com/2/tweets/search/recent` endpoint, cycles maritime/distress queries, tracks `since_id`, normalises author/timestamp data, deduplicates by post id and writes `IntelEvent` records.

The missing work is primarily deployment validation and connector hardening rather than a new Twitter implementation.

Preparation steps:

1. provision an X Developer app / Bearer Token;
2. configure `TWITTER_BEARER_TOKEN` in the live worker environment;
3. confirm `INTEL_ENABLED=true` and the monitor process is actually running;
4. expose connector health, last successful poll, last event and last error;
5. verify that a qualifying official-API event reaches `intel_store` and `/api/v1/live/signals` under the publication policy;
6. record exact connector, upstream id, source timestamp, ingestion timestamp and source URL in provenance metadata;
7. add an integration test using recorded X API fixtures rather than a network-dependent CI test.

For lower latency, the official X filtered-stream API can be evaluated as a later adapter. It should reuse the same normalisation/event path rather than create another X-specific domain model.

### 6. Public Live policy is sophisticated but distributed

`core/api/routes/live.py` already provides a strong privacy-preserving projection and explicitly blocks several source policies. At the same time, individual monitors can set publication/source-policy metadata themselves.

Recommended action:

Create one explicit publication-decision model, for example:

- `transport_trust`: `official | partner | operator | experimental`;
- `publication_status`: `private | review | published`;
- `verification_status`: `unverified | corroborated | verified`;
- `location_precision`: `exact | approximate | withheld`.

Then make Live depend on this common decision model rather than monitor-specific conventions.

### 7. Core module boundaries are visible but not yet clean

The backend already contains useful conceptual areas (`drift`, `forensic`, `ingestion`, `integrations`, `intel`, `ocean`, `sensors`, `vessels`, `zones`), but the current `core/` namespace is carrying too many responsibilities.

Large files that deserve responsibility-based decomposition include at least:

- `apps/web/src/main.jsx` — approximately 148 KB;
- `apps/web/src/components/PlayCesium.jsx` — approximately 58 KB;
- `core/intel/twikit_monitor.py` — approximately 49 KB;
- `core/intel/store.py` — approximately 39 KB;
- `core/intel/geoextract.py` — approximately 37 KB;
- `core/drift/opendrift_pool.py` — approximately 36 KB;
- `core/api/routes/live.py` — approximately 31 KB;
- `core/api/routes/intel.py` — approximately 25 KB.

File size alone is not a defect, but these files now carry multiple responsibilities. Grant preparation should split them along stable interfaces, not cosmetically.

### 8. Frontend composition is concentrated in one entry file

`apps/web/src/main.jsx` is roughly 148 KB while several workspaces already exist as separate components. This suggests an incomplete migration away from a monolithic application entrypoint.

Recommended action:

- leave a full visual redesign outside the first preparation sprint;
- extract routing, API client, map orchestration, Live state and application shell from `main.jsx`;
- preserve behaviour while reducing the entrypoint to composition/bootstrap responsibilities.

### 9. Edge/runtime paths overlap

The repository currently includes:

- root `api/` serverless functions;
- `apps/web/api/` serverless functions;
- `apps/edge/` Cloudflare Worker code;
- `core/live_edge_publisher.py`;
- production reverse-proxy/systemd files.

This is understandable historically but difficult for a new contributor or evaluator to reason about.

Recommended action: define only three conceptual runtime roles.

1. **Core API/worker** — authoritative ingest, models, storage and computation.
2. **Edge gateway** — optional cache/privacy-preserving public projection.
3. **Clients** — web, GIS and other applications consuming stable contracts.

Every runtime file should map clearly onto one of these roles.

### 10. Documentation contains useful history but lacks a single current truth

The `docs/` directory includes production audits, migration audits, cutover notes, zero-cost deployment notes and research audits. These are valuable historical records but currently compete with the current architecture documentation.

Recommended structure:

```text
docs/
  architecture/
  concepts/
  contracts/
  connectors/
  deployment/
  governance/
  development/
  history/
```

Dated migration/audit documents can move under `docs/history/` after their still-actionable items have been absorbed into current documentation.

## Recommended target architecture

The repository should remain a monorepo for now. Splitting repositories before interfaces stabilise would create artificial maintenance overhead.

```text
seacommons/
  apps/
    api/                 # FastAPI composition and HTTP routes
    web/                 # operational/public clients
    edge/                # optional edge gateway
    site/                # institutional site
  packages/
    events/              # event model + JSON Schema
    connectors/          # connector interface + shared normalisation
    drift/               # drift domain and engine adapters
    provenance/          # evidence/provenance manifests
    geo/                 # shared geo types/transforms
  adapters/
    x-official/
    aisstream/
    cmems/
    telegram/
    whatsapp/
    timezero/
    x-twikit-experimental/
  docs/
  examples/
  tests/
  deploy/
```

This is a **target boundary**, not an instruction to perform a one-shot filesystem rewrite. The first refactor should establish interfaces inside the current tree and then move modules through small, reviewable commits.

## Canonical SeaCommons event model

The repository already contains `docs/contracts/seacommons-event-v1.schema.json`. The next preparation milestone should make this the actual canonical boundary between connectors and consumers.

Every connector should emit a record conceptually equivalent to:

```json
{
  "id": "provider-stable-id",
  "type": "distress.report",
  "source": {
    "provider": "x",
    "connector": "x-official",
    "upstream_id": "..."
  },
  "observed_at": "...",
  "received_at": "...",
  "geometry": null,
  "properties": {},
  "provenance": {},
  "verification_status": "unverified",
  "publication_status": "review"
}
```

The exact schema can evolve, but transport-specific objects should be normalised before entering the reusable core.

## Real-data Live milestone

The practical target for the preparation phase should be:

> **A clean `/api/v1/live/signals` endpoint that demonstrably contains privacy-safe, real external data from at least two independent connectors, one of which is the official X API.**

Suggested acceptance criteria:

- official X credentials configured outside the repository;
- X connector health reports active/inactive state, last successful poll and last error;
- one curated query/account set documented in configuration;
- real posts are ingested without storing secrets;
- upstream IDs are deduplicated;
- raw source content remains internal where publication policy requires it;
- public projection emits only allowed fields;
- provenance includes connector name, source URL, source timestamp and received timestamp;
- the API has a deterministic fixture-based integration test;
- Live returns a schema version and feed freshness metadata;
- X failure does not take down the Live endpoint.

A second real-data connector should preferably be AISStream and/or CMEMS because both are already represented in the codebase and demonstrate that SeaCommons is a maritime interoperability stack rather than a social-media monitor.

## CI and quality preparation

Current CI is a good baseline. Before a funding call, add:

- `ruff check` to CI (Ruff is already a development dependency but CI currently only runs pytest for Python quality);
- selective type-checking for stable packages rather than trying to type-check the whole legacy tree at once;
- JSON Schema validation for files in `docs/contracts/`;
- a guard preventing generated DB/runtime data from being committed;
- dependency/security scanning;
- a lightweight duplicate-source check for canonical runtime paths;
- test coverage reporting for the reusable core;
- a compatibility matrix only for versions the project genuinely supports.

## Repository metadata preparation

Before submission:

- update the GitHub repository description and topics around open source, maritime, geospatial, interoperability, SAR, PostGIS, OpenDrift and civic technology;
- add `GOVERNANCE.md`;
- expand `CONTRIBUTING.md` with connector-development guidance;
- add issue templates and `good first issue` labels;
- add `FUNDING.yml` when sponsorship is configured;
- define `ROADMAP.md` with fundable milestones;
- create tagged releases once contracts stabilise;
- publish a concise architecture diagram in README/docs.

## Proposed preparation sprints

### Sprint 0 — repository hygiene

- remove duplicate Live/proxy serverless implementations;
- quarantine/remove runtime/generated data;
- update package identity;
- reorganise dated docs into history;
- document the three current runtime roles;
- add lint/schema/generated-data checks to CI.

### Sprint 1 — canonical events + connectors

- promote `seacommons-event-v1` into the actual connector boundary;
- define a connector protocol/interface;
- adapt official X, AISStream and CMEMS to that boundary;
- centralise provenance fields;
- centralise source-health reporting.

### Sprint 2 — real Live endpoint

- deploy the official X connector with a real Bearer Token;
- verify a second real-data path through AIS and/or CMEMS;
- expose connector health and feed freshness;
- centralise privacy/publication policy;
- add fixture-based integration tests and a reproducible public demo.

### Sprint 3 — drift + provenance

- standardise CMEMS/atmospheric forcing inputs;
- improve uncertainty/ensemble outputs;
- make derived products reproducible from source manifests;
- separate worker execution cleanly from API request lifecycle.

### Sprint 4 — contributor-facing open core

- Python/TypeScript client examples;
- connector SDK documentation;
- minimal independent deployment example;
- QGIS proof-of-concept only after core contracts are stable.

## What should not be done yet

- Do not split SeaCommons into multiple repositories merely to create multiple grant applications.
- Do not rewrite the stack in a new framework.
- Do not add another X/social scraping implementation.
- Do not redesign the full UI before stabilising contracts.
- Do not claim a real-time X feed until a credentialed production deployment has been verified.
- Do not expose private distress text or exact sensitive locations to make the demo look richer.

## Grant-readiness definition of done

SeaCommons should be considered ready to submit as an open-infrastructure project when a new technical evaluator can, from the repository alone:

1. understand the public-interest problem in under two minutes;
2. see the reusable interoperability core without reading deployment history;
3. run a local demo with documented commands;
4. inspect the canonical event schema;
5. add a connector using a documented interface;
6. see CI passing on the default branch;
7. verify that at least two real data adapters have production-tested paths;
8. understand which components are stable, experimental and operator-specific;
9. see an explicit roadmap whose milestones correspond to requested funding;
10. understand governance, licensing, privacy and provenance decisions.

## Immediate development tickets

1. `repo: remove duplicated live/proxy serverless implementations`
2. `repo: remove runtime integration_events.jsonl from source tree`
3. `core: define connector protocol around seacommons-event-v1`
4. `x: harden official X connector and source health reporting`
5. `live: add feed freshness and connector provenance metadata`
6. `policy: centralise publication and transport-trust decisions`
7. `web: extract API/live orchestration from main.jsx`
8. `ci: enforce ruff + schema validation + generated-data guard`
9. `docs: current architecture + connector development guide`
10. `release: rename legacy suezcanal package identity and define version policy`

## Next audit checkpoint

Update this document after Sprint 0 with:

- measured CI/test results;
- live production endpoint checks;
- confirmed X/AIS/CMEMS connector status;
- repository size/history measurements;
- a final grant scope, work-package structure and budget recommendation.
