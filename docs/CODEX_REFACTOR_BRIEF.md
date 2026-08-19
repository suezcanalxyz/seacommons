# SeaCommons — Codex Refactor Brief

Status: active development brief
Date: 19 August 2026

## Objective

Refactor the current experimental repository into a smaller, clearer, testable SeaCommons core before the funding call.

This is **not** a backward-compatibility exercise. The repository is still experimental. Prefer deletion, consolidation and contract simplification over preserving historical paths.

The immediate product goal is narrow:

> A reviewer can clone SeaCommons, understand the architecture quickly, run the API/web stack, and verify a real Live data path from at least X API and AIS into one canonical public event feed.

Do not add features unless they directly support that goal.

---

## Non-negotiable engineering rules

1. **Delete dead or superseded code. Do not keep compatibility wrappers unless they are required by the current deployed path.**
2. **One responsibility, one canonical implementation.** No duplicate serverless handlers, duplicate Live endpoints, duplicate source adapters or parallel config concepts.
3. **No new large modules.** Target ~300 lines/file when practical. Files above ~500 lines must be justified or split by responsibility.
4. **Do not rewrite working domain logic merely for style.** First remove duplication and define boundaries.
5. **No speculative abstractions.** Extract interfaces only where at least two real adapters already need the same contract.
6. **No generated/runtime datasets in source.** Runtime state belongs outside tracked application code.
7. **No legacy naming in active package/runtime namespaces.** SeaCommons is the software identity.
8. **No mock fallback silently presented as Live.** Empty/unavailable is preferable to fake operational data.
9. **Every public event must carry source + timestamp + publication/provenance metadata.**
10. **A refactor is successful only if tests pass and total complexity decreases.** Prefer negative LOC where possible.

---

## Current architectural problem

The repository currently exposes too many overlapping execution paths:

```text
root api/live.js
root api/proxy.js
apps/web/api/live.js
apps/web/api/proxy.js
apps/edge/src/live.js
core/api/routes/live.py
core/live_edge_publisher.py
```

At the same time X/Twitter is represented by:

```text
core/ingestion/parsers/twitter.py
core/intel/twitter_monitor.py
core/intel/twikit_monitor.py
core/intel/x_media_utils.py
```

AIS is also split across:

```text
core/integrations/ais/
core/integrations/aisstream/
core/vessels/aisstream.py
core/vessels/registry.py
```

This makes it difficult to understand which code is canonical and encourages future duplication.

---

## Target architecture for this refactor

Keep the architecture intentionally small:

```text
External sources
   │
   ├── X official API
   ├── AISStream
   ├── CMEMS / weather
   └── partner/manual intake
   │
   ▼
source adapters
   │
   ▼
SeaCommons Event
   │
   ├── validation
   ├── provenance
   ├── publication policy
   └── persistence
   │
   ▼
FastAPI
   │
   ├── /api/v1/events        internal/general
   └── /api/v1/live/signals  privacy-safe public projection
   │
   ▼
web / external clients
```

Workers remain only for operations that genuinely need asynchronous or heavy compute, mainly drift and source polling.

Cloudflare/Vercel should proxy this API, not reimplement domain behaviour.

---

## Phase 0 — establish truth before editing

Codex must first inspect runtime references before deleting anything.

Create a short dependency map for:

- `api/live.js`
- `apps/web/api/live.js`
- `api/proxy.js`
- `apps/web/api/proxy.js`
- `apps/edge/src/live.js`
- `core/live_edge_publisher.py`
- `core/api/routes/live.py`
- `twitter_monitor.py`
- `twikit_monitor.py`
- `ingestion/parsers/twitter.py`
- both AISStream implementations

For every candidate file classify it:

```text
KEEP
MERGE
DELETE
EXPERIMENTAL
```

Do not create an `archive/` or `legacy/` folder as a substitute for deletion. Git already preserves history.

---

## Phase 1 — deletion and repository hygiene

### 1. Remove exact duplicate Live handler

`api/live.js` and `apps/web/api/live.js` are the exact same Git blob.

Keep only the location actually required by the current deployment configuration. Delete the other.

Then inspect the two `proxy.js` files and consolidate them in the same way.

Acceptance:

- only one canonical Vercel/serverless handler implementation exists;
- build/deployment config points explicitly to it;
- no generated copy is committed.

### 2. Remove runtime data from source

`apps/api/core/db/data/integration_events.jsonl` is ~33.7 MB.

Determine whether any test depends on it.

Expected action:

- remove it from tracked source;
- add relevant runtime DB/event paths to `.gitignore`;
- if tests need examples, create tiny deterministic fixtures under `tests/fixtures/`.

Do not preserve a full operational dump.

### 3. Remove obsolete deployment/history docs from active docs surface

Historical dated migration/audit documents should either be deleted when obsolete or moved only if they remain genuinely useful operational records.

Do not keep documentation solely because it once existed.

The active docs root should eventually be understandable from roughly:

```text
ARCHITECTURE.md
EVENT_MODEL.md
LIVE.md
CONNECTORS.md
DEVELOPMENT.md
DEPLOYMENT.md
SECURITY.md
GRANT_READINESS_AUDIT_2026-08-19.md
```

Do not perform a documentation rewrite before runtime boundaries are settled.

---

## Phase 2 — software identity cleanup

Active code still declares:

```toml
name = "suezcanal"
```

and uses `SuezCanalConfig`.

Rename active package/runtime identity to SeaCommons.

Preferred direction:

```text
project package: seacommons
settings class: SeaCommonsConfig
```

Do this mechanically and update imports/tests.

Do not introduce alias classes for backward compatibility unless an active external consumer demonstrably requires them.

Acceptance:

```bash
grep -R "SuezCanalConfig\|name = \"suezcanal\"" apps/api
```

should return no active package/config identity references.

Historical/project-credit prose may still mention Suez Canal Republic where contextually correct.

---

## Phase 3 — canonical event contract

There is already `docs/contracts/seacommons-event-v1.schema.json` and `core/domain/events.py`.

Do not invent another event model.

Inspect both and make one canonical event representation used by source adapters.

Minimum fields:

```text
id
schema_version
type
observed_at
received_at
source
source_id / external_id
geometry optional
properties
provenance
publication_status
```

Important distinction:

- source adapter output = normalized observation/event;
- public Live output = projection of that event;
- UI-specific payload must not become the domain model.

Acceptance:

X and AIS adapters should both be convertible to the same event model without Live knowing source-specific implementation details.

---

## Phase 4 — X/Twitter consolidation

### Supported path

The canonical supported connector should be:

```text
X official API -> normalized SeaCommons Event -> store -> publication policy -> Live
```

`core/intel/twitter_monitor.py` already implements official X API recent search and is the starting point.

Refactor it only as needed to implement a clean adapter boundary.

### Twikit

`twikit_monitor.py` is ~49 KB and currently contains polling, session recovery, reply tracking, repost/quote semantics, media processing, publication decisions and other policy logic.

This is too much responsibility for the canonical source path.

Because the project is experimental, do not preserve this complexity by default.

Codex should identify which unique behaviours are actually required for the current demo.

Expected outcome:

- official X API is canonical;
- if Twikit is not required for the current real-data demo, remove it and its dedicated tests/dependencies;
- if a specific unique feature is required, retain only a thin optional adapter and reuse the same normalization/publication pipeline;
- do not let Twikit define public Live semantics.

Also inspect `core/ingestion/parsers/twitter.py`. If official X data no longer passes through this parser, delete it. If generic external tweet payload ingestion genuinely uses it, rename/reframe it around that exact purpose.

### X acceptance test

With `TWITTER_BEARER_TOKEN` configured:

```text
X recent search
 -> fetch public post
 -> normalized event
 -> persisted/deduplicated
 -> publication policy
 -> /api/v1/live/signals
```

The Live response must expose provenance/source fields but not sensitive/private data.

When the token is absent, health must say `unconfigured`; it must not fabricate data.

---

## Phase 5 — AIS consolidation

Inspect overlap among:

```text
core/integrations/ais/adapter.py
core/integrations/aisstream/client.py
core/vessels/aisstream.py
core/vessels/registry.py
```

Desired split:

```text
connectors/aisstream.py   transport/provider
vessels/registry.py       vessel domain state only if actually needed
```

Delete duplicate provider clients.

The provider module should not contain UI concerns.

Acceptance:

- one AISStream connection implementation;
- one configuration path;
- vessel observations can become SeaCommons Events;
- source health reports last successful observation/poll.

---

## Phase 6 — Live endpoint simplification

`core/api/routes/live.py` is ~31 KB and currently contains projection, privacy logic, persistence queries, lifecycle logic and endpoint handling.

Do not make it larger.

Split only along real responsibilities, for example:

```text
core/live/projection.py
core/live/service.py
core/api/routes/live.py
```

Where:

- `projection.py` = internal event -> public representation;
- `service.py` = query/filter/assemble public signals;
- route file = parameter validation + HTTP/WebSocket response only.

Do not create additional layers beyond these unless necessary.

Remove compatibility fallbacks that return fake/constructed Live data from serverless code.

Canonical rule:

> If upstream Live is unavailable, return unavailable/empty with explicit health metadata. Never synthesize operational-looking data.

---

## Phase 7 — split oversized frontend modules

Do this after backend contracts stabilize.

`apps/web/src/main.jsx` is ~148 KB and should not remain the application module.

Do not redesign the UI during this task.

Extract existing responsibilities only:

```text
app bootstrap
routing/layout
API client
map state
live feed state
feature rendering
```

Likewise inspect `PlayCesium.jsx` (~58 KB) and `IntelDashboard.jsx` (~39 KB).

Target is not arbitrary tiny files; target is understandable responsibility boundaries.

Avoid component fragmentation where a file contains only trivial forwarding code.

---

## Phase 8 — config cleanup

`.env.example` and `core/config.py` contain a large number of experiments and hardware options.

Classify configuration into:

```text
core
live connectors
optional experimental sensors
optional simulation/drift
```

Do not remove active experiments merely because they are optional, but move their configuration close to their module or clearly mark them optional.

Delete stale variables with zero references.

Codex should search references before retaining any setting.

Acceptance:

- every environment variable documented in `.env.example` has an active code reference or an explicit documented deployment purpose;
- every active required setting has an example entry;
- no duplicated names for the same concept.

---

## Phase 9 — dependency cleanup

After deletion, inspect `pyproject.toml` and npm packages.

Remove dependencies only used by deleted code.

Specific check:

- if Twikit is removed, remove `twifork` and Twikit-only test/support dependencies;
- detect imports that exist only in experimental hardware modules and consider optional dependency groups;
- do not force heavy scientific packages into the minimal API install if the API can operate without them.

Longer-term desirable split:

```text
seacommons core install
seacommons[drift]
seacommons[sensors]
seacommons[dev]
```

Only implement this now if it materially simplifies installation; do not turn packaging into its own project.

---

## Tests Codex should preserve/add

Keep tests focused on contracts and behaviour rather than implementation details.

Required minimum:

```text
1. event schema validation
2. official X payload -> normalized event
3. duplicate X ID -> no duplicate event
4. AIS observation -> normalized event
5. private event -> absent from public Live
6. published eligible event -> present in Live
7. exact coordinates/privacy rules remain enforced
8. Live unavailable -> no fake fallback events
9. API smoke test
10. web build
```

Delete tests whose only purpose is preserving code that has been intentionally deleted.

Do not preserve implementation-specific Twikit tests if Twikit itself is removed.

---

## CI target

Keep CI small and strict:

```text
Python:
  ruff
  pytest

Web:
  lint
  tests
  build

Edge:
  tests only if edge remains an independent runtime
```

Add checks for:

- event schema validity;
- forbidden tracked runtime data paths;
- possibly accidental duplicate critical handlers.

Do not create a huge CI matrix.

---

## Deletion candidates to evaluate first

These are candidates, not blind deletions. Search references before removing.

High confidence:

```text
one of:
  api/live.js
  apps/web/api/live.js

apps/api/core/db/data/integration_events.jsonl
```

Strong candidates after dependency inspection:

```text
one of the duplicate proxy.js implementations
obsolete dated migration docs
unused demo/deploy scripts
unused Windows-only scripts
unused duplicate AISStream client
core/ingestion/parsers/twitter.py if no generic ingestion path uses it
Twikit monitor + tests + dependency if official X path is sufficient
```

Evaluate separately, do not mix into the core refactor unless currently required:

```text
apps/unreal/
physical sensors
missile/TID experimentation
SDR/seismic/infrasound experiments
```

Important: experimental does **not** mean legacy. These can remain as optional research modules if they are active, but they must not obscure the SeaCommons core or inflate its default dependency/runtime path.

---

## Files that should become smaller

Priority order:

```text
apps/web/src/main.jsx                     ~148 KB
apps/web/src/components/PlayCesium.jsx    ~58 KB
apps/api/core/intel/twikit_monitor.py      ~49 KB
apps/web/src/components/IntelDashboard.jsx~39 KB
apps/api/core/intel/store.py               ~39 KB
apps/api/core/intel/geoextract.py          ~37 KB
apps/api/core/drift/opendrift_pool.py      ~36 KB
apps/api/core/api/routes/live.py           ~31 KB
```

Do not split all of them mechanically.

For each, first answer:

1. Is the whole feature still needed?
2. Can code be deleted?
3. Are there duplicate responsibilities elsewhere?
4. Only then split what remains.

Deletion comes before refactoring.

---

## Sequence for Codex

Do not attempt the repository-wide refactor in one giant patch.

### Patch A — truth + deletion

- dependency/reference map;
- remove exact duplicate handler;
- remove tracked runtime data;
- remove obviously dead files;
- update ignore rules;
- run tests/build.

### Patch B — identity + contracts

- SeaCommons package/config naming;
- canonical event model;
- normalize official X adapter;
- tests.

### Patch C — real Live vertical slice

- official X -> event -> store -> public Live;
- AIS -> event -> store/Live where relevant;
- health/freshness metadata;
- remove fake compatibility fallbacks.

### Patch D — consolidate source implementations

- Twikit decision/remove or thin adapter;
- AIS duplicate client removal;
- dependency cleanup.

### Patch E — oversized modules

- reduce/split Live route;
- frontend `main.jsx` responsibilities;
- only after contracts are stable.

Each patch should leave the repository runnable.

---

## Definition of done for the preparation refactor

The preparation is complete when:

```text
[ ] README matches actual architecture
[ ] no duplicate Live serverless implementation
[ ] no runtime data dump tracked in core
[ ] active Python package identity is SeaCommons
[ ] one canonical SeaCommons event model
[ ] one canonical official X connector
[ ] one canonical AISStream connector
[ ] /api/v1/live/signals serves real normalized source data
[ ] Live never fabricates operational events
[ ] source health/freshness is inspectable
[ ] privacy/publication projection is tested
[ ] CI passes
[ ] default install does not pull unnecessary experimental dependencies
[ ] major files have understandable responsibilities
[ ] dead code was deleted rather than archived
```

## Final instruction to Codex

Optimize for **clarity, deletion and demonstrable behaviour**, not completeness.

SeaCommons is still being shaped. Breaking an internal experimental path is acceptable if the resulting architecture is smaller and the supported path is explicit. Do not build compatibility layers for code we no longer want.

Before adding a file or abstraction, ask whether deleting or merging something existing solves the same problem.
