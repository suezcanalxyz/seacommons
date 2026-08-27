# Production hardening plan & progress log

This is the plan we followed to take SeaCommons from a working system to
production-grade engineering quality, and the log of what has been done
against it. The baseline audit it builds on is `docs/ENGINEERING_AUDIT.md`.

Scope: audit, refactor and harden the existing codebase. Not a rewrite, and
not a migration to different core technologies. SeaCommons is already a
substantial working system; the aim is that the repository holds up to
review by senior engineers, research software teams, open-source maintainers
and institutional technical reviewers.

The plan is organised as phases (the areas of work) and an execution
sequence (the order of PRs). The progress log at the end records the actual
state of each item.

========================================
CORE PRINCIPLES
========================================

1. Preserve existing behaviour.
2. Never invent functionality.
3. Do not rewrite stable code unnecessarily.
4. Prefer small, reviewable architectural improvements.
5. Every refactor must have a concrete engineering reason.
6. Tests must protect behaviour before risky refactors.
7. Production correctness > elegance.
8. Explicit contracts > implicit behaviour.
9. Observability > silent failure.
10. Documentation must reflect actual implementation.
11. Do not expose secrets, private operational data or unsafe infrastructure details.
12. Keep the project deployable throughout the refactor.

Treat current working functionality as production software.

========================================
PHASE 0 — BASELINE AUDIT
========================================

Before modifying code:

Audit the repository and produce:

docs/ENGINEERING_AUDIT.md

Include:

- current architecture
- application boundaries
- backend structure
- frontend structure
- edge/runtime components
- workers/background jobs
- databases and storage
- realtime/event architecture
- external integrations
- security model
- auth/authz model
- observability
- test coverage
- CI/CD
- deployment architecture
- technical debt
- large files / god modules
- duplicated responsibilities
- risky implicit contracts
- concurrency risks
- failure recovery
- dependency risks
- configuration complexity
- public/private data boundaries

Classify findings:

P0 = security/data correctness
P1 = architecture/reliability
P2 = maintainability/testing
P3 = polish/documentation

Do not modify implementation until this baseline audit is complete.

========================================
PHASE 1 — FRONTEND ARCHITECTURE
========================================

The frontend currently contains several very large modules.

In particular audit:

apps/web/src/main.jsx
apps/web/src/components/PlayCesium.jsx
apps/web/src/components/IntelDashboard.jsx
apps/web/src/styles.css

The goal is NOT arbitrary file splitting.

Identify actual domains and responsibilities, then migrate toward an architecture similar to:

apps/web/src/

  app/
    bootstrap/
    routing/
    providers/

  features/
    live/
    intel/
    drift/
    vessels/
    cases/
    connectors/
    simulation/

  components/
    ui/
    layout/
    map/

  hooks/

  services/
    api/
    realtime/
    storage/

  domain/
    live/
    intel/
    drift/
    vessels/

  types/

  utils/

Extract:

- API clients
- websocket/SSE handling
- event normalization
- domain transformations
- map-specific logic
- UI state
- reusable hooks
- presentation components

Avoid introducing global state libraries unless there is a demonstrated need.

Prefer local state and explicit feature boundaries.

========================================
PHASE 2 — TYPESCRIPT MIGRATION
========================================

Introduce TypeScript incrementally.

Do NOT convert the entire frontend in one massive PR.

Start with domain contracts and high-value boundaries.

Create explicit types/interfaces for at least:

LiveIncident
LiveEvent
IntelEvent
DriftRequest
DriftResult
VesselPosition
SourceHealth
Case
Connector
GeoFeature
LocationPrecision
VerificationStatus

Establish:

apps/web/src/types/
or feature-local domain types where appropriate.

Convert modules progressively:

.jsx → .tsx
.js → .ts

Enable strict TypeScript checks.

Avoid:
any
unknown casts without validation
unsafe assertions
duplicated handwritten contracts

Where API responses cross trust boundaries, validate or normalize them explicitly.

========================================
PHASE 3 — BACKEND ARCHITECTURE
========================================

Audit FastAPI route modules for mixed responsibilities.

Pay particular attention to large modules such as:

core/api/routes/live.py
core/api/routes/intel.py
core/api/routes/alerts.py
core/api/routes/cases.py
core/api/routes/ingest.py

Routes should primarily perform:

request parsing
authorization
input validation
service invocation
response serialization

Move domain logic into appropriate layers such as:

core/domain/
core/services/
core/live/
core/intel/
core/ingestion/

Do NOT create abstraction layers just for aesthetics.

Extract only meaningful business/domain responsibilities.

Target:

thin route
→ service/orchestrator
→ domain logic
→ repository/integration

========================================
PHASE 4 — DOMAIN CONTRACTS
========================================

SeaCommons processes data from multiple external sources.

Establish explicit canonical internal models.

External providers should normalize into internal contracts before entering core logic.

Document the flow:

external source
→ connector/parser
→ normalized domain model
→ validation
→ persistence/event
→ public/private policy
→ API/realtime presentation

Ensure concepts such as:

source
source_policy
verification_status
location_precision
publication status
incident lifecycle
event version
incident identity

have single canonical definitions.

Remove duplicated interpretation logic where possible.

========================================
PHASE 5 — REALTIME RELIABILITY
========================================

Audit realtime/event architecture including:

Cloudflare edge
Durable Objects
WebSockets
publisher
outbox
database synchronization
background monitoring
live snapshots
event TTL
resolution/archive lifecycle

Check specifically for:

duplicate delivery
out-of-order events
stale state
lost updates
reconnect behaviour
retry storms
dead-letter behaviour
idempotency
versioning
partial upstream failure
race conditions
process restart recovery

Document invariants.

Examples:

- resolved incidents must never return to active Live accidentally
- unverified coordinates must never be fabricated
- repeated versions must remain idempotent
- public Live must never expose private operational content
- stale source health must not be interpreted as fresh data

Encode critical invariants in tests.

========================================
PHASE 6 — SECURITY HARDENING
========================================

Audit existing:

OIDC/JWT
RBAC
WebSocket authentication
HMAC ingestion
CORS
public/private endpoints
tenant boundaries
webhooks
secret handling
production configuration validation

Add or strengthen:

SECURITY.md

Automated security checks where appropriate:

- dependency scanning
- npm audit
- pip-audit
- CodeQL
- Dependabot or Renovate
- secret scanning compatibility

Do NOT weaken existing fail-safe production configuration.

Review whether:

/metrics
/docs
/openapi.json
health endpoints

should have different exposure depending on runtime profile.

Do not change production exposure without documenting consequences.

========================================
PHASE 7 — TESTING STRATEGY
========================================

Do not chase arbitrary coverage percentages.

Create a deliberate testing pyramid.

Backend:

unit tests
domain invariant tests
integration tests
API tests

Frontend:

domain/unit tests
React component tests where valuable
realtime state tests
critical Playwright flows

Edge:

event lifecycle
authentication
TTL
idempotency
snapshot/reconnect behaviour

Identify the 10 highest-risk user/system flows and ensure automated protection.

Examples:

1. ingest verified incident
2. publish to Live
3. update existing incident
4. resolve incident
5. remove resolved incident
6. drift simulation
7. provider failure
8. reconnect after realtime interruption
9. unauthorized operational access
10. public/private publication boundary

========================================
PHASE 8 — CI/CD
========================================

Make CI a meaningful quality gate.

Required checks:

Python:
- lint
- format/check
- type checking where practical
- pytest
- dependency security audit

Web:
- ESLint
- TypeScript
- tests
- production build

Edge:
- tests
- build/dry run

Repository:
- secret detection compatibility
- dependency checks
- git diff/check
- optional CodeQL

Do not make CI excessively slow.

Separate fast PR checks from heavier scheduled checks where useful.

========================================
PHASE 9 — CONFIGURATION
========================================

The configuration surface is currently large.

Audit configuration ownership.

Group settings conceptually:

runtime
database
auth
object storage
jobs
intel
drift
AIS
weather
messaging
external APIs
edge
observability

Avoid one enormous configuration class becoming the global domain model.

Keep backwards compatibility with deployed environment variables.

Add validation for combinations that are unsafe or impossible.

Document:

required production variables
optional integrations
development defaults
demo-only settings

========================================
PHASE 10 — OBSERVABILITY
========================================

Review:

structured logs
request IDs
Prometheus metrics
worker health
source health
queue health
realtime delivery health

Ensure operators can answer:

Is the API alive?
Is the DB alive?
Are workers alive?
Are external sources alive?
Is Live receiving events?
Are events being published?
Are drift jobs succeeding?
Are retries accumulating?
Are incidents stale?

Do not log sensitive content.

========================================
PHASE 11 — DOCUMENTATION
========================================

Improve public engineering documentation.

README should communicate within the first screen:

What SeaCommons is
What is actually operational
Core architecture
Technology stack
Live/demo links
How to run locally

Add:

docs/ARCHITECTURE.md
docs/DATA_FLOW.md
docs/SECURITY_MODEL.md
docs/REALTIME_ARCHITECTURE.md
docs/DEPLOYMENT.md
docs/DEVELOPMENT.md

Include Mermaid diagrams where useful.

Separate clearly:

implemented
experimental
planned
research

Never present planned functionality as production functionality.

========================================
PHASE 12 — REPOSITORY PROFESSIONALISM
========================================

Make the GitHub repository look intentionally maintained.

Add/review:

CONTRIBUTING.md
SECURITY.md
CODEOWNERS if useful
issue templates
PR template
release/version strategy
CHANGELOG.md
architecture decision records

Use conventional commits.

Prefer feature branches and focused PRs.

Every PR must include:

Why
What changed
Architecture impact
Tests
Risks
Rollback considerations

========================================
PHASE 13 — AI-ASSISTED ENGINEERING POLICY
========================================

Parts of the repository are developed with Codex / Claude Code. The
canonical version of this policy is `docs/AI_ENGINEERING_POLICY.md`; the
summary below is kept here for the plan's completeness.

AI is an engineering tool, not an authority.

Every AI-generated change must pass:

1. deterministic tests
2. lint/type checks
3. architectural review
4. security review for relevant changes
5. human approval before merge

Do not leave large unexplained AI-generated diffs.

Prefer small PRs.

If uncertain about domain behaviour, stop and document the uncertainty instead of guessing.

========================================
PHASE 14 — PROPOSED: NAVAL COMMUNICATIONS MONITORING
========================================

Status: design proposal, not started. This section scopes a requested
capability — a general monitoring layer over live naval/maritime
communications — so it can be reviewed before any code is written. It does
not commit the project to building it.

--- Goal ---

Give operators a single view of the maritime-communications picture around
an area of interest: who is broadcasting distress, safety and routing
traffic, and how that corroborates or contradicts the OSINT/AIS incident
feed SeaCommons already has.

--- What already exists (do not rebuild) ---

- AIS position/voyage traffic via AISStream (core/vessels/aisstream.py),
  including an optional dedicated NGO/SAR-fleet subscription by MMSI.
- OSINT distress ingestion (Alarm Phone / X / news) with canonical
  incident lifecycle and public/private policy.
- A hardware sensor node design with an RTL-SDR already in the BOM
  (docs/BOM.md) — RF decode is within reach of the existing node.

--- Candidate sources, roughly by effort ---

1. AIS safety-related messages already in the AISStream feed but currently
   ignored: AIS-SART / AIS-MOB / AIS-EPIRB (message types 1/14 with the
   974xxxxxx MMSI range), safety-related broadcast (type 14) and
   addressed safety (type 12). Lowest effort — same transport, same
   parser file, no new provider.
2. DSC (Digital Selective Calling) distress and safety on VHF ch70 / MF /
   HF. Requires either an SDR + a DSC decoder on the sensor node, or an
   online DSC aggregator feed if a lawful one is available in-region.
3. NAVTEX (518 kHz) and other Maritime Safety Information (MSI) text —
   navigational/meteorological/SAR warnings. SDR + decoder, or an online
   MSI text feed. Text-only, geocodable by NAVAREA/subarea.
4. Coast-guard / MRCC public situation broadcasts and press updates where
   published as feeds (some MRCCs publish structured SAR bulletins).
5. Out of scope for now: decoding voice ch16, and anything requiring
   interception of non-broadcast or encrypted traffic.

--- Architecture sketch ---

    source connector (per protocol)
        -> normalize to a canonical NavalCommsEvent
        -> classify: distress / safety / routine / MSI
        -> distress  -> existing incident pipeline (core/intel), same
                        lifecycle, public/private policy and projection
        -> non-distress -> a separate "comms" context stream, operator-only
                           by default, never auto-published

New code would live under a `core/comms/` subsystem parallel to
`core/ingestion/` and `core/vessels/`, not inside them. Each connector is
independently enable/disable via config, defaults off, and degrades
cleanly when its source is unavailable (same contract as the AIS and
intel connectors).

--- Canonical model (to define in Phase 4 terms) ---

    naval_comms_event: id, received_at, observed_at, protocol
      (ais_sart | dsc | navtex | msi | mrcc_bulletin), category
      (distress | urgency | safety | routine), station/MMSI (if any),
      position or NAVAREA, free text, source_policy, verification_status.

Reuse the existing LocationPrecision, VerificationStatus and publication
policy vocabulary — a comms event that reaches Public Live must obey the
same "distress-only, no fabricated coordinates, fail closed" rules as an
OSINT incident.

--- Invariants (must hold before anything ships) ---

- A routine or safety broadcast must never appear on Public Live.
- A DSC/SART position is a reported position only when the message
  actually carried coordinates; a bare distress alert with no position
  stays unpositioned.
- A comms event that corroborates an existing incident links to it; it
  does not create a duplicate incident.
- Source-station identity is recorded but a raw MMSI is operator-only
  unless it is a public SAR asset.
- No connector records or rebroadcasts traffic it is not lawfully
  permitted to receive in its deployment region; this is a
  per-deployment configuration decision, documented, not a default.

--- Suggested phasing ---

  Phase 14a - AIS safety-related messages (SART/MOB/EPIRB, type 12/14)
              from the existing AISStream feed. Smallest, highest-value
              slice. Adds a NavalCommsEvent model + the AIS branch + tests.
  Phase 14b - canonical NavalCommsEvent contract + the operator-only comms
              context stream and a dedicated monitoring view.
  Phase 14c - DSC ingestion (SDR-on-node decoder or a lawful online feed).
  Phase 14d - NAVTEX / MSI text ingestion and geocoding by NAVAREA.
  Phase 14e - MRCC/coast-guard structured bulletin connectors, per region.

--- Open questions for a human decision ---

- Which sources are lawful to receive and retain in the intended
  deployment region(s)? This gates everything after 14a.
- Does the comms stream get its own persistence and retention policy, or
  reuse the intel event store?
- Is there an existing in-region DSC/NAVTEX aggregator with an API, or is
  SDR-on-node the only path?

========================================
PHASE 15 — PROPOSED: DRIFT FIDELITY AND PER-OBJECT MODEL HIERARCHY
========================================

Status: design proposal, not started. Requested as a priority: make the
operational drift trajectories realistic, upgrade the forcing sources and
their request hierarchy, and apply the right drift model to the right kind
of object (a drifting cargo ship does not move like a person in the water).

--- Current state (from a read of core/drift/) ---

The live engine is core/drift/opendrift_pool.run_leeway (NOT the older,
now-unused opendrift_runner.py). It is better than it first looks:

- Forcing is already gridded and time-varying: a 5x5 Open-Meteo grid
  (_GridReader) supplies wind and fallback currents; a CMEMS 0.083 degree
  NetCDF slice (reader_netCDF_CF_generic) is inserted first-priority for
  ocean currents when CMEMS_USERNAME/PASSWORD are set.
- reader_constant is only a last-resort fallback.

What still limits realism:

1. One model for everything. `_Leeway` is hard-coded. OceanDrift, OpenOil
   and WindBlow are defined in core/drift/models.py but never used. Only
   the `ballistic` domain branches away (a custom solver).
2. No large-vessel object class. core/drift/models.py LEEWAY_OBJECT_TYPE
   has no cargo/container/tanker entry, so resolve_object_type() falls
   through to 26 -- "person in water". A reported drifting cargo ship is
   currently simulated with swimmer leeway coefficients.
3. Stokes (wave) drift is explicitly disabled
   (`sim.set_config("drift:stokes_drift", False)`), even though CMEMS also
   publishes a wave dataset and Open-Meteo marine has wave fields.
4. No landmask reader is added, so particles can drift across coastline.
5. CMEMS is credential-gated. If the operational box has no CMEMS
   credentials, currents come only from the coarser Open-Meteo grid --
   verify the production configuration; this alone changes trajectory
   quality substantially.
6. case_type does not reach the drift path. Intel auto-drift takes a
   vessel_type string (default "rubber_boat"); cases (which now carry
   case_type) are a separate object and are not linked to intel drift.
7. Single OpenDrift concurrency slot on a 1 GB VM. A "run drift for every
   active incident daily" mode needs the ARM 12 GB worker
   (see docs/CLOUDFLARE_EDGE_DEPLOYMENT.md "Future ARM 12 GB").

--- Target architecture ---

    request (case_type + vessel_type/object hint)
        -> drift_profile registry: object_class -> (OpenDrift model, params)
        -> ForcingProvider: per-field source hierarchy, each attempt tagged
        -> OpenDrift run with the selected model + best available readers
        -> result carries forcing_quality; operational_use gated on it

drift_profile (new, replaces resolve_object_type):

    object_class            model        notes
    person_in_water         Leeway 26    unchanged
    life_raft               Leeway 27/29 unchanged (by persons)
    rubber_boat             Leeway 38    unchanged
    small_wooden_boat       Leeway 46    unchanged
    fishing_vessel_small    Leeway 52    unchanged
    sailboat                OceanDrift   wind_drift_factor ~0.03, shallow
    cargo_container_ship    OceanDrift   wind_drift_factor ~0.01-0.02,
                                         wind_drift_depth deeper; current-
                                         dominated
    tanker                  OceanDrift   as above, even lower windage
    lost_container/debris   OceanDrift   object-specific windage; often an
                                         ensemble spread
    oil_light/medium/heavy  OpenOil      weathering on

case_type -> default object_class when no better hint:

    distress_sar        -> rubber_boat (or vessel_type if given)
    pushback            -> rubber_boat
    missing_persons     -> person_in_water + rubber_boat ensemble
    shipwreck           -> debris field (multi-object OceanDrift ensemble)
    interception        -> rubber_boat
    vessel_incident     -> from vessel_type; cargo/tanker -> OceanDrift
    monitoring          -> no automatic drift

ForcingProvider hierarchy (explicit, logged, and scored):

    current : CMEMS gridded NetCDF -> Open-Meteo marine grid -> zero (flag)
    wind    : (future) NWP gridded  -> Open-Meteo forecast grid -> default
    waves   : CMEMS wave dataset    -> Open-Meteo marine waves  -> Stokes off

Each level that actually covered the simulation's space/time domain is
recorded in metadata.forcing_quality (e.g. "cmems_current+oms_wind+waves"
vs "omg_current_only"). The UI shows high-fidelity vs degraded, and
operational_use stays false below a threshold.

--- Invariants (must hold before anything ships) ---

- A cargo/tanker/large-vessel drift must never use Leeway PIW coefficients.
- A wind-only drift (no current data at all) must be flagged degraded in
  the output and the UI and must not be presented as operational.
- The demo fallback stays visibly degraded (unchanged).
- Enabling Stokes/landmask must not silently change historical stored
  trajectories; re-runs are versioned like any other drift update.
- No fabricated forcing: a missing field is zero-with-a-flag, never a
  plausible-looking guess.

--- Suggested phasing ---

  Phase 15a - drift_profile registry + object classes (incl. cargo/tanker/
              debris) + model dispatch (Leeway | OceanDrift | OpenOil) in
              opendrift_pool + case_type/vessel_type -> profile mapping +
              forcing_quality metadata. No new data sources. Deterministic
              tests with constant readers. Medium risk.
  Phase 15b - enable Stokes drift from wave data; add the CMEMS wave
              dataset (or Open-Meteo waves) to the reader stack; add
              reader_global_landmask so particles beach. Needs an
              integration test with real readers.
  Phase 15c - gridded NWP wind (ERA5 reanalysis or GFS forecast) as the
              top wind source, replacing the Open-Meteo grid where covered.
  Phase 15d - daily batch analysis: scheduled drift for every active
              unresolved distress incident; store trajectory history; show
              predicted-vs-observed divergence where an AIS or a later
              report corroborates a position. This is the "daily maritime
              data analysis capacity" ask -- depends on the ARM 12 GB
              worker being provisioned.
  Phase 15e - ensemble / uncertainty: proper Leeway coefficient
              perturbation, multi-object shipwreck debris fields, and a
              calibrated probability cone instead of a convex hull.

--- Open questions for a human decision ---

- Is CMEMS configured on the operational box today? 15b/15c planning
  depends on the answer.
- Is the ARM 12 GB worker provisioned, or is 15d blocked on hardware?
- ERA5 (reanalysis, ~5 day lag, free via CDS) or GFS (forecast, near-real-
  time) for gridded wind in 15c?
- Should a case running its own drift override the intel event's
  auto-drift, or run alongside it?

========================================
IMPORTANT: DO NOT DO THESE THINGS
========================================

Do NOT:

- rewrite SeaCommons from scratch
- replace FastAPI
- replace React
- replace Cesium
- introduce Kubernetes
- introduce microservices without concrete justification
- add Kafka merely for architectural prestige
- replace PostgreSQL
- introduce Redux unless clearly necessary
- convert every file at once
- change APIs without compatibility planning
- fabricate production claims
- fabricate realtime data
- fabricate coordinates
- silently change incident lifecycle semantics
- remove safety/privacy constraints
- expose operational secrets
- optimize prematurely

========================================
TARGET QUALITY BAR
========================================

At completion, the repository should demonstrate:

Senior-level system design
Clear domain boundaries
Typed contracts
Production-conscious security
Realtime reliability
Strong tests
Intentional CI/CD
Observability
Clear failure modes
Responsible data handling
Maintainable frontend architecture
Thin backend controllers
High-quality documentation
Professional GitHub workflow

A senior engineer reviewing the repository should be able to understand:

WHAT the system does
WHY it is designed this way
WHERE each responsibility lives
HOW correctness is verified
HOW production failures are handled
HOW sensitive/public data boundaries are enforced

========================================
EXECUTION STRATEGY
========================================

Do NOT implement everything in one branch.

After the audit, create a proposed sequence of PRs.

Prefer roughly:

PR 1 — engineering baseline + CI improvements
PR 2 — frontend domain contracts / TypeScript foundation
PR 3 — extract realtime/live frontend architecture
PR 4 — extract map/Cesium responsibilities
PR 5 — backend live/intel route decomposition
PR 6 — canonical event/domain contracts
PR 7 — realtime reliability/invariant tests
PR 8 — security automation and hardening
PR 9 — observability
PR 10 — documentation / repository polish

The sequence below was adjusted after examining the actual repository; the
progress log records where it diverged and why. Each PR is meant to be
understandable independently.

The work started from the baseline audit (`docs/ENGINEERING_AUDIT.md`):
architecture map, debt/risk classification (P0–P3), the ordered PR plan, and
the first safe refactor. No broad refactor was done in the first pass.

========================================
PROGRESS LOG (updated 2026-08-27)
========================================

Actual PR sequence, adjusted from the plan above after examining the
repository (see docs/ENGINEERING_AUDIT.md for the full baseline audit
this sequence is based on):

PR 1 — engineering baseline + CI improvements
  Status: OPEN, not merged. https://github.com/suezcanalxyz/seacommons/pull/13
  Branch: ci/baseline-audit-and-gates
  What: docs/ENGINEERING_AUDIT.md (baseline audit); wired ruff/mypy/pip-audit
  into the api CI job and npm audit into web/edge; .github/dependabot.yml
  (weekly pip/npm/github-actions). Baseline debt found (ruff ~125
  minimal-ruleset findings, mypy ~176 errors, 3 transitive npm vulns in web)
  is wired report-only (continue-on-error), not blocking -- fixing it wasn't
  in scope for a CI-wiring PR. edge npm audit is blocking (already 0 vulns).
  No application code touched.

PR 2 — backend public/private policy consolidation
  Status: OPEN, not merged. https://github.com/suezcanalxyz/seacommons/pull/14
  Branch: feature/public-private-policy-consolidation
  What: core/api/routes/live.py and core/live_edge_publisher.py each
  hand-maintained their own copy of _BLOCKED_SOURCE_POLICIES and the
  "explicit private is absolute" check (live_edge_publisher.py's own comment
  already flagged "the values must stay identical" with nothing enforcing
  it). Extracted core/intel/public_policy.py (is_explicitly_private,
  is_blocked_source, zero framework deps) used by both. Added
  tests/test_public_policy.py with a parity test proving both paths agree.
  214 tests pass (was 211 baseline, +3 new). Deliberately did NOT unify
  which event types are eligible for public exposure without an explicit
  publish decision -- the VM feed (broader "public signals" context feed)
  and the edge feed (operational distress-only Live map) diverge there in a
  way that looks like an intentional product distinction, not a bug; left
  for a human call per this doc's own "stop and document uncertainty
  instead of guessing" rule.

  This PR order differs from the original plan's PR2 (frontend TypeScript
  foundation) -- the audit found the public/private duplication was a live
  P1 correctness risk (two independently-maintained eligibility checks that
  could silently diverge), so it was pulled forward ahead of the frontend
  work, which carries no correctness risk of the same kind.

PR 3 — realtime invariant tests (edge + publisher)
  Status: IMPLEMENTED LOCALLY, not committed or pushed (2026-08-26).
  Gap analysis confirmed that tests/test_live_edge_publisher.py already covers
  publisher outbox durability/dedup/versioning/live-window expiry (18 tests),
  while apps/edge/src/live.test.js did not exercise LiveRoom state at all.
  Added an in-memory Durable Object harness and three integration-level edge
  tests covering exact duplicate delivery (one stored event/one broadcast),
  out-of-order observed_at delivery, state/head-hash recovery after restart,
  removal-tombstone persistence, and the snapshot sent on WebSocket reconnect.

  The tests exposed a P1 reliability bug rather than only a coverage gap: a
  delayed older version could replace the current incident, and a retry after
  incident_removed could make a resolved incident active again. Added a small
  guard in apps/edge/src/live.js: persist the latest per-incident observation
  (including removal tombstones), accept stale retries idempotently with
  stale=true, and leave events/head_hash/broadcast state unchanged. A genuinely
  newer source observation can still supersede the tombstone; payload and
  endpoint contracts are otherwise unchanged.

  Verification: edge 9/9 tests pass (6 baseline + 3 new); full backend suite
  211/211 passes; git diff --check passes. Exact files changed for PR 3:
  apps/edge/src/live.js and apps/edge/src/live.test.js. Remaining follow-up for
  a later reliability pass: runtime-level concurrent/multi-region replay tests
  need a Workers/Miniflare integration harness; the current unit harness covers
  deterministic state transitions and persisted restart/reconnect behaviour.

PR 4 — frontend domain contracts / TypeScript foundation
  Status: IMPLEMENTED LOCALLY on feature/frontend-domain-contracts (`e213eb9`).
  Added strict domain types for Live, Intel, drift, vessels, cases, connectors,
  GeoJSON and verification/location vocabulary.

PR 5 — realtime/live frontend extraction
  Status: IMPLEMENTED LOCALLY on refactor/live-realtime-frontend (`73dc8ab`).
  Extracted response normalization, API client and realtime hook, with focused
  unit tests for malformed payloads, lifecycle updates and API failures.

PR 6 — Cesium/map responsibility extraction
  Status: IMPLEMENTED LOCALLY on refactor/cesium-map-responsibilities (`712ace5`).
  Extracted sea rendering and drift scene modelling from PlayCesium, with
  deterministic scene-model tests.

PR 7 — backend Live/Intel route decomposition
  Status: IMPLEMENTED LOCALLY on refactor/backend-live-intel-routes (`c0ac398`).
  Routes now delegate public projection, feed, query, ingestion and drift work
  to focused services. Full backend regression suite passed before commit.

PR 8 — canonical Live/domain contracts
  Status: IMPLEMENTED LOCALLY on feature/canonical-live-contracts (`22a87fc`).
  Added canonical Python/JSON Schema/Edge vocabulary, fail-closed projection and
  cross-runtime contract tests.

PR 9 — split-runtime observability
  Status: IMPLEMENTED LOCALLY on feat/split-runtime-observability (`7297c68`).
  Added DB-sync recovery/failure metrics, log escalation, worker and source
  health gauges, with sensitive exception detail excluded from logs.

PR 10 — documentation and repository professionalism
  Status: IMPLEMENTED LOCALLY on docs/consolidate-architecture (`a852dda`) and
  chore/repository-polish (`d7a0b7d`). Added canonical architecture/data-flow/
  security/realtime docs, documentation index, CODEOWNERS, templates, changelog
  and ADRs.

Security/CI enforcement follow-up
  Status: IMPLEMENTED LOCALLY on ci/enforce-production-gates (`a9ce804`).
  Critical Ruff, canonical mypy, declared-project pip-audit, npm audits and
  CodeQL are blocking; the frontend advisory-bearing transitive lock entries
  were updated.

Combined verification branch
  Status: IN PROGRESS on roadmap/production-hardening (2026-08-27). The backend,
  CI/security, documentation and frontend branches are combined here. PR 3's
  stale-version/tombstone logic has been reconciled with the newer canonical
  Edge contracts: 11 Edge tests, the full extracted frontend test set and the
  production builds pass together.

CI enforcement follow-up 2 (ESLint/secret/whitespace gates)
  Status: COMMITTED on roadmap/production-hardening (`af14ea2`, 2026-08-27).
  apps/web now has a flat ESLint config (@eslint/js recommended + react-hooks);
  `lint:js` (errors only) is blocking via the existing `lint` script and
  `lint:js:full` (27 known warnings) runs report-only in CI. ci.yml runs the
  full `npm test` suite on web, adds `wrangler deploy --dry-run` on edge, and a
  new `repository` job running `git diff --check` and gitleaks over the pushed
  range. No application code touched. Web lint/typecheck/test/build, edge 13,
  backend 217 pass locally.

Testing strategy documentation
  Status: COMMITTED on roadmap/production-hardening (2026-08-27).
  Added docs/TESTING.md: the testing pyramid (backend 217 / edge 13 /
  frontend 23) and an explicit map from the ten highest-risk flows (ingest,
  publish, update, resolve, remove, drift, provider failure, reconnect,
  unauthorized access, public/private boundary) to the named tests guarding
  each. No new tests were required -- every flow already had coverage; the gap
  was that it was not written down. Linked from docs/README.md. Remaining
  gap recorded in the doc: no Playwright end-to-end layer.

Deployment / development / AI-engineering documentation
  Status: COMMITTED on roadmap/production-hardening (2026-08-27).
  Added docs/DEPLOYMENT.md (deployment surfaces, the three deployment modes,
  required production configuration with the fail-closed variable list from
  core/security.py, DNS, rollout and rollback order), docs/DEVELOPMENT.md
  (prerequisites, dev stack, layout, test/lint commands mirroring CI, common
  contributor tasks) and docs/AI_ENGINEERING_POLICY.md (Phase 13: the review
  gates every AI-assisted change must pass and the things it must never do).
  All three are synthesized from existing runbooks and code, not invented.
  Linked from docs/README.md; CONTRIBUTING.md updated to point at the new dev
  guide and AI policy and to drop the stale `npm run test:simulation` command.

Configuration grouping and combination validation
  Status: COMMITTED on roadmap/production-hardening (2026-08-27).
  core/config.py was left as a flat data holder (deliberately not refactored
  into groups -- that would risk the deployed-env-var compatibility the
  roadmap protects and turn the settings class into a god object the roadmap
  warns against). Instead: core/config_validation.py adds cross-field checks
  for combinations that are impossible or unsafe regardless of profile
  (invalid JOB_EXECUTION_MODE, DEMO_PUBLIC_MODE on production, reused
  AISSTREAM key, unauthenticated drift worker, inverted correlation
  thresholds) as hard errors, plus incomplete-integration warnings. Wired
  into the API lifespan after validate_production_security and runnable
  standalone as `python -m core.config_validation` for pre-deploy checks.
  The conceptual grouping is documented in docs/CONFIGURATION.md. Every check
  fires only on an already-broken combination. tests/test_config.py +8
  (226 -> 234 backend). ruff + mypy clean on the new module.

Publisher / outbox observability
  Status: COMMITTED on roadmap/production-hardening (2026-08-27).
  The edge publisher (core/live_edge_publisher.py) is a standalone process
  that previously emitted only log lines. Added Prometheus instrumentation in
  core/observability.py -- cycle counter by outcome, an events counter
  (collected / delivered / delivery_failed), an outbox depth gauge
  (pending / retrying), last-cycle and last-delivery timestamps and a
  heartbeat-ok gauge -- fed from deliver(), heartbeat() and the run loop.
  The process exposes its own /metrics only when LIVE_EDGE_METRICS_PORT is
  set (0 = off, so nothing changes for existing deployments); metric updates
  are wrapped so they can never break the delivery loop. Alert guidance in
  docs/REALTIME_ARCHITECTURE.md updated to name the new series;
  docs/CONFIGURATION.md lists the publisher env vars. tests/test_live_edge_publisher.py
  +2 (234 -> 236 backend). ruff clean; the one mypy hit (os.uname on the
  Windows checker) is pre-existing and not in the CI mypy gate set.

All roadmap audit items in the progress log are now implemented locally on
roadmap/production-hardening. Remaining work is human review and the PR
sequence described at the top of this file; no remote merge or production
deployment is claimed here.

Working method: implementation remains divided into focused branches/commits.
The combined branch exists to prove that the independently reviewable changes
compose without losing invariants. No claim of remote merge or production
deployment is made by this local progress log.
