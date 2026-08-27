# Development

Status: canonical development guide. Last reviewed: 2026-08-27.

## Prerequisites

- Python 3.12 (production and CI target; 3.11 also works locally)
- Node.js >= 22.13.0 (`apps/web` and `apps/edge` `engines`)
- Git. Docker is optional and only needed for the full production-like stack.

No database server is required for development: the default is SQLite.

## Setup

```bash
git clone https://github.com/suezcanalxyz/seacommons.git
cd seacommons
cp .env.example .env
python -m pip install -e "apps/api[dev]"
npm --prefix apps/web ci
npm --prefix apps/edge ci
```

## Run the dev stack

```bash
bash scripts/run_dev.sh all      # API :8000 + Vite :5173
bash scripts/run_dev.sh backend  # API only
bash scripts/run_dev.sh frontend # Vite only
```

On Windows: `powershell -File scripts/start.ps1`.

Defaults when `.env` is absent or minimal: `MOCK=true`,
`DEMO_PUBLIC_MODE=true`, SQLite, no auth. API docs at
`http://localhost:8000/docs`, console at `http://localhost:5173`.

The edge Worker runs separately: `cd apps/edge && npm run dev`.

## Layout

```text
apps/api/core/
  api/routes/     thin HTTP handlers: parse, authorize, delegate, serialize
  domain/         canonical vocabulary and validation models
  live/           Live projection and services
  intel/          public/private policy, geometry, OSINT
  ingestion/      provider-specific parsers and connectors
  integrations/   outbound integrations
apps/web/src/
  app/            bootstrap, routing, providers
  features/       live, intel, drift, vessels, cases, connectors, simulation
  services/       api clients, realtime, storage
  domain/ types/  typed contracts
  components/     ui, layout, map
apps/edge/src/    Worker entrypoint + LiveRoom Durable Object
```

Dependency direction is one-way: `route / entrypoint -> domain service ->
store or integration adapter -> database / provider`. Domain policy must not
move back into route handlers. See [ARCHITECTURE.md](ARCHITECTURE.md#backend-boundaries).

## Tests, lint, types

```bash
python -m pytest -q                         # backend
cd apps/web && npm run lint && npm test && npm run build
cd apps/edge && npm test
```

`npm run lint` in `apps/web` runs `eslint src --quiet` (errors block) then
`tsc --noEmit`. `npm run lint:js:full` is the report-only warning baseline
(currently 27 known warnings). These mirror the CI gates in
`.github/workflows/ci.yml`.

What each layer's tests protect, and the map from the ten highest-risk flows to
their tests, is in [TESTING.md](TESTING.md).

## Conventions

- Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `ci:`, `chore:`).
- Feature branch + the PR template (why / what / architecture impact / tests /
  risks / rollback). See [../CONTRIBUTING.md](../CONTRIBUTING.md).
- A change to a durable boundary, contract or the operating model needs an ADR
  under `docs/adr/`; small implementation choices do not.
- New analytical outputs must record source, timestamp, model/version,
  uncertainty and limitations.
- Never commit credentials, personal data, live distress locations or
  unredacted operational exports. `.gitignore` blocks `.env*`; the CI
  `repository` job runs gitleaks and `git diff --check`.

## Common tasks

### Change a Live/domain contract

Update the canonical definition in `apps/api/core/domain/`, the JSON Schema
under `docs/contracts/`, and the edge vocabulary in `apps/edge/src/`. The
cross-runtime tests (`tests/test_live_contracts.py`,
`tests/test_runtime_contracts.py`, `apps/edge/src/live.test.js`) must stay
green — they exist to catch drift between the three runtimes.

### Add an ingestion connector

Parser and classifier go in `apps/api/core/ingestion/`. Normalize to the
canonical internal model before anything reaches core logic; user-originated
signals are private by default. Add parser tests to `tests/test_connectors.py`.

### Touch public/private policy

`core/intel/public_policy.py`, `core/intel/public_geometry.py`,
`core/live/projection.py`, `core/domain/live_contracts.py` are the only places
public-exposure decisions live. Keep the VM and edge paths in agreement —
`tests/test_public_policy.py` proves parity.

## Related documents

- [Architecture](ARCHITECTURE.md)
- [Deployment](DEPLOYMENT.md)
- [Testing strategy](TESTING.md)
- [Security model](SECURITY_MODEL.md)
- [Contribution rules](../CONTRIBUTING.md)
