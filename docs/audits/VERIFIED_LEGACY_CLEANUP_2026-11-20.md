# SeaCommons legacy audit and verified cleanup — 20 November 2026

## Scope and safeguards

Read-only inventory of the isolated repository checkout, followed by narrow deletion of demonstrably unreferenced frontend artifacts on a dedicated branch. No Oracle production files, archived observations, database schemas, migrations, runtime services, credentials, public API routes or external consumer contracts were changed.

The audit was performed against the in-progress shared LIVE/PLAY layout branch. It is **not** a full proof of safety for unexamined backend modules or third-party integrations.

## Inventory and evidence

- 1,159 tracked files in the inspected checkout before cleanup.
- Approximately 64 MB checked-out repository tree (the local checkout size is not the Git object history size).
- No tracked `dist/`, `node_modules/`, `build/`, `__pycache__/`, `.pytest_cache/` or `*.bak` artifacts were found; the existing `.gitignore` covers them.
- `apps/api/core/db/data/integration_events.jsonl` is a large, approximately 32 MiB **tracked** JSONL artifact. Its purpose and external dependencies need explicit verification before converting it to fixtures, archive-only data or object storage. **Not removed.**
- Multiple Alembic revisions, including two filenames beginning with `0027`, exist. Revision identifiers and Alembic dependency edges require a graph check; do **not** infer a collision from filenames or delete migration history.

## Verified dead legacy — removed

| Item | Evidence | Action |
| --- | --- | --- |
| `apps/web/src/components/BottomNav.jsx` | No importing frontend module or entrypoint; CSS was forcibly hidden with `display:none!important` | Delete unused component |
| `.bottom-nav*` CSS in `apps/web/src/styles.css` | Exclusively styled the unused BottomNav | Delete CSS and unconditional hiding override |
| `.live-basemap-switch*` CSS | No LIVE JSX uses the old class. Superseded by `MapBasemapSwitch` and `.sc-basemap-switch`. | Delete obsolete positioning/mobile styling |
| `.play-cartographic-legend` and `.play-key-*` CSS | No PLAY JSX renders the old permanent legend. Superseded by modal `MapReferenceBar`. | Delete obsolete styles |
| Old position assertions in `mobileLayout.test.js` | Asserted deleted control placement | Replace with checks for the actual responsive shared basemap switch |
| Old legend E2E overlay selector | Referenced deleted overlay | Replace with current shared reference modal selector |

## Retained, required, or still unknown

**A — Required:** current LIVE/PLAY files, supported map fallbacks, source provenance, asset attribution, historical datasets used by tests, API contracts, archived incident evidence, Alembic chain, vendor radio decoder sources.

**B — Temporary compatibility:** dual MapLibre / Leaflet renderers remain useful for a controlled fallback, but should share data semantics and be covered by equivalent tests; retain until a documented migration can guarantee parity.

**D — Investigate before removal:** the large tracked integration JSONL; old API compatibility routes; historical feature flags; vendor libraries and scripts with possible external users; dynamically loaded frontend modules. Lack of simple text references alone is not sufficient for deletion.

## Follow-on backlog

1. Trace `integration_events.jsonl` through tests, ingest, builds and deployments; decide whether to retain as reproducible fixture, migrate to object storage or use a smaller anonymized sample. Preserve checksums and rollback.
2. Generate an OpenAPI route → consumer matrix from API logs, web clients, tests and external docs before removing deprecated routes.
3. Run a dependency/entrypoint-aware frontend module graph (including dynamic imports, worker URLs and Vite entrypoints) before deleting other JSX or CSS.
4. Reconcile concurrent #547 (evidence contracts), #548 (vessel symbols), #549 (map), and shared panel layout before merging to main.
5. Keep the Oracle dirty working tree untouched; align production through a controlled deployment procedure once the integration CI is green.

**Rule:** delete only what is conclusively unused, not merely old, large or inconvenient.
