# SeaCommons — Post-Stabilization Geospatial & Data Intelligence Upgrade Plan

> **Execution order:** `docs/fixes.md` remains authoritative until fully completed. Do not start this plan while any required `fixes.md` milestone, migration, replay, integration, privacy, CI, or production verification gate is still open.
>
> **Purpose:** raise SeaCommons from a stabilized maritime OSINT application to a production-grade geospatial and evidence-intelligence infrastructure without accumulating another layer of legacy. This document is a migration program, not a feature wishlist.

## Immediate first task after `fixes.md` closes — audit the real Live data and make lifecycle canonical

Before PostGIS, AI enrichment, new geospatial infrastructure or any other upgrade milestone, inspect the **actual production Live datasets and rendered Live UI**. Do not infer correctness from fixtures or unit tests. The first post-stabilization PRs must explain and correct what real operators/users currently see.

Audit at minimum:

```text
/api/v1/live/signals
/api/v1/live/drifts
/api/v1/live/archives
public edge projection
rendered Humanitarian Live map/panel
Alarm Phone source threads and repost/update chains
persisted IntelEvent / SourceObservation / DriftResult rows behind each visible case
```

For every currently visible Humanitarian case reconstruct a timeline:

```text
source observed_at
received_at
event timestamp used by Live
first publication time
latest source update time
latest correlated update time
Drift origin time
Drift model created_at / completed_at
current lifecycle state
why that lifecycle state was selected
whether the case is still on Live
whether a Drift is still on Live
```

Treat visible stale Drift geometry, impossible/incorrect timers, duplicate Alarm Phone markers, unresolved events that silently disappear, resolved events that remain operational-looking, and incorrect coordinates as data-model/pipeline defects — not cosmetic UI issues.

### Canonical Humanitarian case lifecycle

Stop treating each source post as the operational case itself. Persist a canonical `HumanitarianIncident`/case identity and an append-only lifecycle history. Source observations remain immutable evidence linked to that case.

Minimum lifecycle states:

```text
reported       first credible distress observation received
active         current evidence supports an ongoing incident
needs_review   updates exist but outcome/correlation is ambiguous
resolved       credible evidence says immediate distress/search is concluded
archived       case is historical and no longer operationally live
reopened       new credible evidence after resolution indicates renewed/continuing danger
```

`archived` must not mean “we have heard nothing for 24 hours”. Silence is not resolution. Age may change display prominence and trigger review, but lifecycle must describe what evidence says happened.

Every transition persists:

```text
incident_id
from_state
to_state
transition_at
effective_at
reason_code
supporting_observation_ids[]
source/correlation method
confidence
review_required
reviewed_by/reviewed_at when applicable
```

A later Alarm Phone post/reply must update the same incident when correlation is strong enough; it must not merely create a second unrelated red marker. Ambiguous correlation becomes `needs_review`, never a silent merge.

### Alarm Phone timer semantics

The UI timer must have an explicit semantic source. Never calculate one generic “age” from whichever timestamp happens to be present.

Expose at least:

```text
reported_at       when the original incident was reported/observed
last_update_at    latest evidence/update attached to the case
state_changed_at  when lifecycle last changed
data_received_at  when SeaCommons received the latest source observation
```

Public UI should normally display **“reported X ago”** plus **“updated Y ago”** when later evidence exists. For `resolved`, display **“resolved X ago”** and stop the active timer. Never reset incident age merely because SeaCommons re-ingested the same source item, reran a classifier, regenerated a projection or recalculated Drift.

All timestamps must be normalized to UTC in storage and rendered from explicit ISO timestamps. Add regression fixtures for timezone offsets, source timestamps without timezone, delayed ingestion, reposts, duplicate ingestion and out-of-order updates.

### Drift lifecycle must be owned by the incident

A Drift is a derived model product, not an independently live incident. Each Drift must reference the canonical incident and the exact origin evidence/time that generated it.

Rules:

```text
ACTIVE/NEEDS_REVIEW case + valid maritime point -> Drift may be operationally visible
RESOLVED case -> immediately remove/freeze Drift from operational Live
ARCHIVED case -> no operational Live Drift
REOPENED case -> create a new versioned Drift only from newly valid evidence
new accepted position -> old Drift becomes superseded; never display old and new as equally current
region-only/unpositioned case -> no fabricated Drift
```

Persist Drift status such as `current | superseded | resolved | failed | historical`, with `superseded_by`, origin observation ID, origin timestamp, model/version and lifecycle linkage. `public_drift_collection()` must select only the current Drift belonging to an operationally eligible case; it must not rediscover arbitrary completed historical jobs and publish them as current.

### Required production-data audit output

Before changing algorithms, produce a machine-readable report over current Live data containing, per visible case:

```text
incident/event ids
source
reported_at
last_update_at
lifecycle
lifecycle reason
position status/method
visible marker yes/no
current drift id/status/origin time
visible drift yes/no
age/timer values shown vs expected
duplicate/correlation candidates
anomaly flags
```

Flag at least:

```text
STALE_DRIFT
DRIFT_AFTER_RESOLUTION
MULTIPLE_CURRENT_DRIFTS
DRIFT_ORIGIN_OLDER_THAN_CURRENT_ACCEPTED_POSITION
TIMER_SOURCE_MISMATCH
RECEIVED_AT_USED_AS_REPORTED_AT
OUT_OF_ORDER_UPDATE
RESOLUTION_NOT_LINKED
ARCHIVED_BY_SILENCE_ONLY
DUPLICATE_LIVE_INCIDENT
OPEN_CASE_DROPPED_FROM_LIVE
RESOLVED_CASE_STILL_ACTIVE_LOOKING
LOCATION_CHANGED_WITHOUT_DRIFT_SUPERSESSION
```

Create regression fixtures from real problematic records after removing/private-redacting sensitive content. The audit is complete only when every unexplained visible anomaly has a code/data-path explanation and a test or explicit remediation task.

**Immediate-first-task exit gate:** production Live marker/Drift/timer inventory committed; lifecycle transitions are evidence-based and persisted; Alarm Phone updates resolve/reopen/update one canonical case; stale/superseded Drift cannot remain operationally visible; timers use explicit event/update/state timestamps; archive and Live are distinct projections of the same incident history.

---

# 0. Operating principle

Every milestone in this document must do at least one of the following:

1. remove an existing architectural limitation;
2. replace duplicated or ad-hoc logic with a canonical subsystem;
3. improve correctness, observability, performance, replayability, privacy or interoperability in a measurable way;
4. delete legacy code or create an explicit and testable deletion path for it.

A new dependency, service, schema, abstraction, model provider, compatibility field, dual-write path or fallback is not progress by itself.

**Hard rule:** every new subsystem must either replace, simplify or measurably improve an existing path. Do not leave previous authoritative paths alive indefinitely.

**AI rule:** model output is evidence enrichment or candidate analysis, never an unproven source of truth. No LLM/VLM provider may silently become canonical domain logic.

---

# 1. Preconditions — `fixes.md` must be closed first

Before starting M0, the agent must prove on the exact `main` commit used as the upgrade baseline:

- every required milestone in `docs/fixes.md` is complete;
- backend full suite green;
- lint/typecheck/build green where applicable;
- DB migrations tested on PostgreSQL and retained SQLite-compatible test paths;
- deterministic replay gates green;
- Humanitarian and Maritime live/public projections verified;
- privacy contracts verified;
- no unresolved P0/P1 stabilization defect is hidden behind a skipped test, fallback, mock-only path or compatibility branch;
- latest production verification is documented.

If any of those fail, return to `fixes.md`. Do not use this document to bypass stabilization work.

---

# 2. Mandatory agent execution protocol

Every milestone follows this loop:

```text
1. sync main
2. read docs/fixes.md and confirm it remains closed
3. read docs/updates.md
4. inspect current implementation before proposing edits
5. identify the exact legacy path being replaced or retained
6. write failing tests / migration tests / replay fixtures first
7. implement the smallest coherent vertical slice
8. run targeted tests
9. run the full relevant suites
10. measure query/performance impact where DB, map or model calls change
11. self-review duplicate logic, compatibility leftovers and dead code
12. document what became canonical
13. document what legacy code was removed
14. document temporary compatibility and its deletion milestone
15. open one reviewable PR
16. merge only after green CI and explicit exit-gate evidence
17. update main and continue with the next dependency-ready milestone
```

For every PR include:

```text
Existing implementation:
Target implementation:
Legacy removed in this PR:
Temporary compatibility retained:
Compatibility deletion milestone:
Files touched:
Tests proving parity/correctness:
Migration/replay evidence:
Known limitations:
```

For AI-enabled PRs also include:

```text
AI mode: disabled | shadow | assistive | bounded-authoritative
Provider/model(s):
Deterministic fallback:
Persisted provenance fields:
Evaluation corpus:
Accuracy/divergence metrics:
Privacy review:
Failure/degradation behaviour:
```

A milestone is not DONE if the new system exists but an older authoritative path silently controls production behaviour.

---

# 3. Global non-negotiable constraints

1. PostGIS does not replace evidence semantics, provenance, confidence, review or publication policy.
2. Spatial SQL performs retrieval, geometry operations and candidate generation; domain reasoning remains explicit and testable.
3. Raw, reported, derived, uncertainty and public geometries remain distinguishable.
4. No inferred geometry may be presented as a reported position.
5. Humanitarian privacy constraints take precedence over analytical convenience.
6. Do not expose exact vulnerable-person locations merely because the canonical datastore contains them.
7. Never destroy original source geometry when producing corrected, snapped, generalized or public geometry.
8. Every derived geometry carries method/version/input provenance.
9. Every imported geospatial dataset records source, version/date, licence/terms and import version.
10. Unknown CRS is a validation failure, not an invitation to guess.
11. Never assume EPSG:4326 without explicit source knowledge.
12. No new spatial dependency enters production without deterministic tests.
13. No speculative index. Every non-trivial production index corresponds to a documented query path or measured plan.
14. No large GIS dataset is hardcoded in Python when it can be versioned as data.
15. No technology or model provider is added solely for keyword coverage or novelty.
16. Every compatibility layer has an explicit removal milestone.
17. `legacy`, `deprecated`, `compat`, `fallback`, duplicate geometry helpers and obsolete schema fields are release-review targets, not permanent architecture.
18. AI providers are replaceable adapters; provider-specific response structures must not leak into canonical domain models.
19. All model-derived outputs persist provider, model, model/version identifier where available, prompt/schema version, timestamp, input IDs and confidence/quality metadata where meaningful.
20. New model calls start **disabled or in shadow mode**. They may not alter production publication, incident lifecycle, privacy projection or canonical geometry until their bounded promotion gate is passed.
21. Model output must conform to explicit typed/JSON schemas before entering domain logic. Free-form prose is never a database contract.
22. AI failure, rate limiting, quota exhaustion or provider outage must degrade to deterministic behaviour rather than block core ingestion.
23. No Humanitarian public publication decision may be made solely by an LLM/VLM.
24. No VLM-inferred coordinate may be labelled `reported_geometry`; it is a candidate/derived claim until deterministic validation or explicit review promotes it.
25. Embeddings and semantic similarity generate candidates; they do not independently prove that two observations refer to the same event.
26. AI-generated allegations or identity claims are prohibited from public projection without the same evidence and review gates as any other hypothesis.
27. Source content containing sensitive Humanitarian information must only be sent to a provider when data-processing/privacy policy explicitly permits that provider and mode.
28. Persist enough structured model output to replay downstream decisions without requiring the same external model response to be regenerated.

---

# 4. Target architecture

Long-term flow:

```text
SOURCE / SENSOR / DATASET
        ↓
CANONICAL OBSERVATION + PROVENANCE
        ↓
DETERMINISTIC EXTRACTION / NORMALIZATION
        ↓
GEOSPATIAL NORMALIZATION
        ↓
REPORTED / DERIVED / UNCERTAINTY GEOMETRY
        ↓
SPATIAL + TEMPORAL CANDIDATE RETRIEVAL
        ↓
OPTIONAL AI EVIDENCE ENRICHMENT / SEMANTIC CANDIDATES
        ↓
VALIDATION + DOMAIN CORRELATION / INTELLIGENCE LOGIC
        ↓
INCIDENT / EPISODE / ASSESSMENT
        ↓
REVIEW + PUBLICATION POLICY
        ↓
PRIVACY-AWARE PUBLIC GEOMETRY
        ↓
REST / WS / VECTOR TILE / GIS EXPORT
```

The forbidden shortcut is:

```text
SOURCE → LLM/VLM → production truth
```

The required model-assisted pattern is:

```text
SOURCE
  ↓
deterministic extraction
  ↓
model candidate/enrichment (optional)
  ↓
typed validation
  ↓
comparison/correlation
  ↓
canonical domain decision
```

Canonical vector storage target:

```text
PostgreSQL + PostGIS
        ↑
GeoAlchemy2
        ↑
Python domain services
        ↔ Shapely / PyProj
```

AI integration target:

```text
AIProvider interface
  ├─ Groq-compatible adapter
  ├─ Gemini-compatible multimodal adapter
  ├─ NVIDIA NIM-compatible adapter
  └─ OpenRouter-compatible fallback/benchmark adapter

Provider output
  ↓
typed schema
  ↓
persisted AI evidence/provenance
  ↓
domain validator / correlator
```

Provider names above are initial candidates, not permanent architecture. Adding or removing a provider must not require rewriting event, incident, geometry or publication models.

Raster target where required:

```text
source raster / model output
        ↓
GDAL / xarray normalization
        ↓
Cloud Optimized GeoTIFF or equivalent object-storage artifact
        ↓
rio-tiler / TiTiler only when justified
        ↓
MapLibre / Cesium / analyst tooling
```

Do not store large raster archives in PostgreSQL by default.

---

# 5. M0 — Legacy eradication and architecture census

**Goal:** establish exactly what must disappear before new GIS/intelligence infrastructure becomes authoritative.

Audit backend, DB models, migrations, tests, frontend contracts, edge/live publisher, docs, deployment files, fixtures and environment variables.

Classify at minimum:

```text
legacy
deprecated
compat
compatibility
fallback
old_
TODO migration
remove after
remove once
dual write
maritime_domain
lat/lon assumptions
area_geojson
_haversine / haversine
bearing
bbox
point_to_segment
GeoJSON stored in JSON
provider-specific AI helpers
ad-hoc OCR/model calls
embedding/vector experiments
```

Each item is `KEEP`, `MIGRATE`, `DELETE` or `TEMP COMPAT` with a named deletion milestone.

Map all implementations of distance, bearing, bbox, proximity, point-to-segment, land/sea, nearest-sea snapping, clustering, containment, track proximity, infrastructure proximity, GeoJSON parsing, drift geometry and uncertainty representation.

Audit geospatial/analytical fields hidden in generic metadata and decide whether each belongs in a typed DB column, typed geometry column, derived artifact, immutable provenance payload or compatibility metadata.

**M0 exit gate:** complete inventory committed; no unclassified known legacy path; every temporary compatibility item has a deletion milestone; no production behaviour changed except safe dead-code removal proven by tests.

---

# 6. M1 — PostGIS geospatial foundation

**Goal:** introduce a canonical spatial database layer without breaking current contracts.

Add only the dependencies required for the first vertical slice: PostGIS, GeoAlchemy2, Shapely and PyProj. Do not add GeoServer, GDAL, H3, TimescaleDB, Kubernetes or tile servers here.

Introduce `location_geom` for one bounded canonical observation/event location path while scalar lat/lon remain temporary API/persistence compatibility. Writes must pass through one canonical helper and divergence is an error.

Create GiST indexes only for proven query paths and benchmark at minimum recent positioned events, bbox events, events within radius and vessel positions within radius using representative PostgreSQL fixtures.

Migration must backfill valid lat/lon, flag invalid ranges, preserve null/unpositioned states, be restart-safe and verify row/geometry counts.

**M1 exit gate:** PostGIS active in integration; one canonical location path spatially backed; GiST query test exists; no public contract break; no duplicated dual-write; rollback/backfill evidence captured.

---

# 7. M2 — Canonical spatial data model

**Goal:** stop treating all location as a single point.

Explicit geometry roles:

```text
reported_geometry   = directly supplied by source/sensor
derived_geometry    = deterministically or analytically derived from evidence
uncertainty_geometry = plausible area/trajectory uncertainty
public_geometry     = privacy/publication projection only
```

Prefer a dedicated typed geometry-evidence record when provenance becomes multi-valued. Suggested fields include owner, role, geometry, CRS, method, method version, precision class, uncertainty, input observation IDs, source reference and creation time.

Raw AIS points remain evidence/time-series primitives even if derived `LineString` tracks are created.

Drift output migrates from generic JSON toward typed trajectory/cone geometry while preserving model version, forcing inputs, start time and simulation parameters.

SAR regions, EEZs, territorial waters, ports, infrastructure corridors and AOIs become versioned reference data where real datasets exist.

**M2 exit gate:** geometry semantics documented/tested; raw evidence never overwritten; drift/track migration tested; generic metadata geometry is not authoritative where a typed replacement exists.

---

# 8. M3 — Spatial query migration and deterministic candidate generation

**Goal:** move candidate retrieval and geometry math into PostGIS while evidence interpretation remains explicit in Python.

Priority conversions:

1. nearby events;
2. nearby vessels;
3. bbox selection;
4. point-in-zone;
5. infrastructure proximity;
6. track/area intersection;
7. drift/track or drift/event intersection;
8. nearest-object lookup;
9. spatiotemporal candidate generation for fusion;
10. deduplication shortlist generation.

Use appropriate PostGIS primitives such as `ST_DWithin`, `ST_Intersects`, `ST_Covers`, `ST_Distance`, `ST_ClosestPoint`, `ST_LineLocatePoint`, `ST_MakeLine`, `ST_Envelope`, `ST_Expand`, `ST_Simplify` while validating units and geography-vs-geometry semantics.

The DB answers: **which recent observations/events are plausible spatial/temporal candidates?**

The domain layer answers: **do these observations support the same incident, episode or hypothesis?**

This becomes the mandatory first-stage shortlist for later semantic similarity. Do not run expensive embedding/LLM comparisons across the entire corpus when deterministic spatial/temporal constraints can safely bound candidates.

After each migration delete superseded local geometry code and retain semantic parity/replay tests.

**M3 exit gate:** representative query benchmark improved/justified; no fusion/replay semantic regression; superseded math removed; query plans recorded for high-volume paths.

---

# 9. M4 — Humanitarian geolocation V2

**Goal:** make Humanitarian location evidence explicit, uncertainty-aware, multimodal-ready and privacy-safe.

Supported evidence types include:

```text
reported coordinate
OCR coordinate
map screenshot coordinate
map pin inference
named place
relative location phrase
named region
operator-reviewed position
land humanitarian location
unpositioned
```

Do not collapse multiple claims early. An event may carry text, OCR, image/map, thread/repost and external corroborating claims simultaneously.

Examples:

```text
exact reported coordinate -> Point + source precision
OCR coordinate -> candidate Point + OCR confidence + uncertainty
place centroid -> derived Point + regional uncertainty geometry
"south of Lampedusa" -> sector/area, not fake precision
map-pin fit -> derived candidate Point + fit uncertainty
VLM coordinate -> derived candidate claim + model provenance + uncertainty
```

Land/sea validation preserves source coordinates; corrected/snapped geometry is derived; land Humanitarian remains visible under its own policy.

Public Humanitarian geometry may be exact only when policy permits, otherwise generalized, buffered, regionalized, cell-based or withheld, with machine-readable precision class.

Replay corpus must include Alarm Phone text coordinates, Alarm Phone map screenshots, coarse regions, contradictory text/image coordinates, land cases, coastline ambiguity, invalid OCR pairs, exact coordinate superseding stale region geometry and no-position negatives.

**M4 exit gate:** no fake precision; analyst/public location tested independently; source geometry preserved; location-method accuracy metrics reported.

---

# 9A. M4A — AI evidence-enrichment foundation

**Goal:** introduce provider-agnostic model infrastructure without changing production decisions.

This milestone starts only after M4's evidence/geometry semantics are stable enough to store model-derived claims correctly.

## M4A.1 — Provider abstraction

Create one canonical `AIProvider`-style interface for bounded capabilities such as:

```text
structured text extraction
classification
multimodal/image extraction
embeddings
reranking
bounded reasoning/correlation
transcription (later/optional)
```

Adapters may initially target NVIDIA NIM, Groq, Gemini and OpenRouter, but canonical services must depend on capability contracts rather than provider names.

## M4A.2 — Structured result envelope

Every persisted invocation/result records at minimum:

```text
provider
model
model_version/revision where available
capability
schema_version
prompt/instruction version
input observation IDs or immutable source references
request timestamp
latency
status/error class
usage metadata where available
structured result
validation status
```

Never persist model prose as the only machine-readable result.

## M4A.3 — Shadow mode

Initial integration must be observational:

```text
deterministic_result = current_pipeline(input)
ai_candidate = ai_pipeline(input)
compare_and_record(deterministic_result, ai_candidate)
return deterministic_result
```

Model output may not alter canonical incident creation, lifecycle, public publication, privacy projection, Drift eligibility or reported geometry during this phase.

## M4A.4 — Failure and cost controls

Requirements:

- feature flag OFF by default;
- per-capability/provider configuration;
- bounded timeout;
- rate-limit/quota handling;
- deterministic fallback;
- no retry storm;
- observability for latency/error/usage;
- cache only where input identity and model/schema version make cache semantics deterministic;
- provider secrets never committed.

## M4A exit gate

- at least two interchangeable provider adapters pass the same contract tests, or one real adapter plus a deterministic fake proves provider separation;
- all AI calls can be disabled without changing core ingestion behaviour;
- shadow results persist with full provenance;
- provider outage/rate limit does not block deterministic ingestion;
- no production/public decision depends on AI output.

---

# 9B. M4B — Multimodal Humanitarian geolocation and Alarm Phone image evidence

**Goal:** improve screenshot/map extraction without replacing deterministic OCR or inventing precision.

Primary workflow:

```text
source image/screenshot
        ↓
existing OCR / deterministic extraction
        ├──────────────┐
        ↓              ↓
text/location claims   VLM structured extraction
        └──────┬───────┘
               ↓
claim comparison + validation
               ↓
candidate derived geometry / uncertainty
               ↓
review or bounded promotion policy
```

A VLM should extract a strict schema containing only fields justified by the source, for example coordinates/raw coordinate text, named places, map labels, apparent pin location, people-count claims, event-type cues and per-field confidence/quality indicators. Absence stays null/unknown.

Never allow a model to convert a vague map region into an exact point merely to satisfy a schema.

For Alarm Phone screenshots specifically compare:

- deterministic OCR coordinate extraction;
- VLM coordinate extraction;
- text caption/thread evidence;
- land/sea validity;
- map extent/pin plausibility when available.

Persist disagreements rather than silently choosing one.

Promotion states:

```text
shadow_candidate
validated_candidate
review_required
accepted_derived
rejected
```

No VLM coordinate becomes `reported_geometry`.

Evaluation corpus metrics:

- coordinate detection precision/recall;
- coordinate numeric accuracy;
- false precise-point rate;
- land/sea consistency;
- agreement/disagreement with OCR;
- correct null/no-position rate;
- privacy-policy compliance.

## M4B exit gate

- labelled Alarm Phone/map screenshot corpus evaluated;
- VLM improves at least one defined metric without unacceptable precision hallucination;
- disagreements remain inspectable;
- source image/text provenance retained;
- public projection remains governed by deterministic privacy policy;
- model unavailability returns the existing OCR/deterministic path unchanged.

---

# 9C. M4C — Semantic correlation, duplicate resolution and OSINT intelligence layer

**Goal:** use embeddings/reranking/bounded reasoning to improve candidate correlation while preserving evidence semantics.

Required cascade:

```text
new observation
      ↓
PostGIS + temporal deterministic shortlist
      ↓
optional embedding similarity / lexical features
      ↓
semantic candidate shortlist
      ↓
domain correlation rules + evidence comparison
      ↓
SAME_EVENT | RELATED_EVENT | NEW_EVENT | UNCERTAIN
```

Embeddings are candidate-generation features, not truth. Persist embedding model/version and recompute policy.

Do not build a permanent provider-specific vector architecture before measuring whether PostgreSQL/pgvector or the existing datastore can satisfy the actual scale. Introduce a separate vector database only through an ADR with measured need.

## M4C.1 — Cross-source event matching

Evaluate cases where Alarm Phone, NGO reporting, press, authority statements, AIS observations or other feeds describe the same incident differently.

Signals may include:

- spatial/temporal overlap;
- people-count compatibility;
- vessel description;
- departure/location references;
- event lifecycle;
- shared source/thread identity;
- semantic text similarity;
- contradiction strength.

The result stores supporting and contradicting features, not only a score.

## M4C.2 — Contradiction detection

Model-assisted reasoning may produce a typed analytical record such as:

```text
claims
agreements
contradictions
missing_information
source_independence indicators
candidate interpretation
confidence/quality metadata
```

It must not decide that one source is true merely because of provider language-model preference. Source reliability/policy remains explicit domain configuration/evidence.

## M4C.3 — Provider roles

Initial likely routing, subject to benchmark:

```text
Groq-class fast inference      -> high-frequency structured extraction/classification
Gemini-class multimodal        -> image/map understanding where privacy policy permits
NVIDIA NIM/Nemotron-class      -> embeddings/reranking/bounded analytical correlation
OpenRouter                     -> benchmark/fallback access, not canonical routing logic
```

These are implementation candidates only. Routing decisions must be capability/benchmark driven and replaceable.

## M4C.4 — Promotion ladder

```text
DISABLED
  ↓
SHADOW
  ↓
ASSISTIVE (analyst/candidate ranking only)
  ↓
BOUNDED_AUTHORITATIVE
```

`BOUNDED_AUTHORITATIVE` is permitted only for a narrowly defined field/action after replay metrics and failure-mode tests prove it. Publication and Humanitarian privacy decisions remain outside model-only authority.

## M4C exit gate

- labelled duplicate/correlation corpus exists;
- precision/recall/F1 reported for `SAME_EVENT`, `RELATED_EVENT`, `NEW_EVENT`, `UNCERTAIN` or equivalent taxonomy;
- false-merge rate has an explicit release threshold;
- contradiction records cite source observation IDs;
- model/provider outage does not prevent deterministic candidate correlation;
- no public allegation or Humanitarian publication is created solely from semantic similarity/model reasoning.

---

# 10. M5 — H3 spatial intelligence layer

**Goal:** introduce a discrete spatial index only where it measurably improves privacy, aggregation or clustering.

Use H3 for density aggregation, privacy-preserving public cells, spatial statistics, coarse clustering, heatmaps, regional summaries and justified cache keys. Geometry remains authoritative; H3 resolution is explicit.

**M5 exit gate:** H3 reproducible from geometry; privacy tested across cell boundaries; no exact private location leaks through H3 metadata/API.

---

# 11. M6 — Geospatial dataset ingestion with GDAL/OGR

**Goal:** deterministic, provenance-aware import of external vector/raster geography.

Support justified inputs such as GeoJSON, GeoPackage, Shapefile, KML and CSV with explicit coordinate schema. Potential datasets include SAR regions, EEZs, territorial waters, coastlines, ports, subsea cables, pipelines, offshore infrastructure, protected areas and AOIs.

Every import records source identity/version, licence/terms, retrieval time, checksum, original/canonical CRS, tool version, transforms, feature count and validation result.

Reject or quarantine invalid geometry, unknown CRS, impossible coordinates, malformed polygons, unexpected feature-count collapse and duplicate source versions. Preserve source defects rather than silently hiding them.

**M6 exit gate:** one real dataset reproducibly imported; identical input checksum gives identical canonical feature identity; provenance/licence recorded; import replayable from scratch.

---

# 12. M7 — QGIS operational QA and analyst validation

**Goal:** make spatial correctness inspectable independently of the frontend.

QGIS is QA tooling, not runtime. Provide read-only analyst/debug layers for raw/reported, derived, uncertainty and public geometry, Humanitarian events, AIS positions/tracks, drift trajectories/cones, SAR/EEZ/reference zones, infrastructure and correlated alerts.

Where AI-derived claims exist, provide a separable QA layer/table view showing candidate geometry, method/model provenance and validation state; do not visually merge it with reported geometry.

**M7 exit gate:** representative geospatial/model-derived location bugs independently inspectable; QA procedure documented; no runtime coupling; vulnerable-person exact locations protected by role.

---

# 13. M8 — Map delivery and vector-tile scaling

**Goal:** stop sending unnecessarily large GeoJSON payloads when measured volume requires it.

Candidate path: `PostGIS → ST_AsMVT / Martin / pg_tileserv → MapLibre`. Choose the smallest system satisfying actual requirements.

Tiles must respect public/private projection, zoom-aware simplification and cache invalidation; private attributes never enter public tiles. Separate map transport from detail APIs where necessary.

**M8 exit gate:** benchmark shows material improvement; privacy tests green; legacy bulk endpoint removed or explicitly retained as bounded export.

---

# 14. M9 — Raster and ocean-data architecture

**Goal:** support oceanographic/satellite/model rasters without turning the core DB into a raster archive.

Preferred pattern: source → xarray/GDAL → COG or equivalent → object storage → rio-tiler/TiTiler when justified → MapLibre/Cesium. PostgreSQL stores metadata/provenance.

Potential use: currents, wind, waves, SST, bathymetry, satellite detections, drift forcing and model uncertainty.

**M9 exit gate:** one raster pipeline reproducible end-to-end; checksum/provenance recorded; no uncontrolled local-file dependency; licensing verified.

---

# 15. M10 — AIS spatial/time-series scale

**Goal:** keep vessel history performant as retention/coverage increases.

Start with native PostgreSQL/PostGIS: spatial, temporal and measured composite indexes; time partitioning where justified; retention/pruning; VACUUM/ANALYZE expectations; representative benchmarks.

Benchmark track by MMSI/time, bbox/time, nearby vessels, rendezvous candidates, zone crossing, infrastructure proximity and recent multi-MMSI history at increasing data volumes.

Evaluate TimescaleDB only after measured native-Postgres bottlenecks.

**M10 exit gate:** data-volume envelope documented; query plans captured; retention tested; no full-table spatial scans on primary paths.

---

# 16. M11 — Reproducible infrastructure with Docker + Ansible

**Goal:** replace manual VM configuration with reproducible deployment.

Automate supported Ubuntu/base users/SSH/firewall/runtime/PostgreSQL/PostGIS/Redis where required/reverse proxy/TLS/application workers/secrets references/backups/log rotation/monitoring/restart policies.

Do not split containers for aesthetics; separate API/worker/geospatial/drift/model gateway only when dependency weight, isolation or scaling justifies it.

AI provider secrets/configuration belong in deployment secret management. A provider outage must not prevent API startup or deterministic ingestion.

Prove clean VM → operational stack, idempotent redeploy and backup restore including PostGIS geometry and required artifacts.

---

# 17. M12 — GIS interoperability

**Goal:** expose standards only when an external consumer needs them.

Potential requirements: GeoJSON/GeoPackage export, WMS/WFS/WMTS, OGC API Features. GeoServer is allowed only after an ADR proves FastAPI/PostGIS or a lightweight service cannot cleanly satisfy the requirement.

Exports must not leak private geometry or unreviewed AI-derived claims.

---

# 18. M13 — Explicit non-goals / prohibited premature dependencies

Do not introduce technologies merely because they are common in GIS/AI stacks:

```text
Django
.NET
Oracle Spatial
SQL Server Spatial
ESRI runtime dependencies
FME
GeoNode
Kubernetes
TimescaleDB
GeoServer
standalone vector DB
model orchestration framework
agent framework
self-hosted GPU inference cluster
```

Any reconsideration requires an ADR documenting the unsolved requirement, alternatives, operational cost, migration/exit strategy and test plan.

Likewise do not introduce NVIDIA NIM, Groq, Gemini, OpenRouter or any other provider into production simply because a free tier exists. Each provider must serve a measured capability and remain replaceable.

---

# 19. M14 — Final legacy deletion

**Goal:** after parity is proven, remove transitional architecture.

Remove spatial dual-write authority once geometry is canonical; scalar lat/lon may remain only as derived API projection fields.

Remove authoritative dependence on legacy `area_geojson` or similar metadata once typed geometry evidence has parity.

Remove superseded custom geospatial helpers and stale taxonomy/compatibility fields.

Remove temporary AI shadow/compatibility infrastructure that no longer has a defined role, including provider-specific bypasses, obsolete prompt/schema versions from active routing, duplicate model-call helpers and fallback branches whose deletion condition has passed. Historical persisted provenance must remain readable even after a provider adapter is removed.

Repository-wide audit every remaining occurrence of `legacy`, `deprecated`, `compat`, `fallback`, `old_`, `remove after`, `TODO migration` and AI/provider bypass markers. Every remaining case must be justified or actively scheduled for deletion.

---

# 20. M15 — Production qualification

**Goal:** prove the upgraded system is more correct and operable than the stabilized baseline.

## Correctness

- full backend/web suites;
- PostGIS integration and geometry migration tests;
- CRS/coordinate tests;
- Humanitarian location replay;
- AIS/fusion replay;
- drift replay;
- AI provider contract tests where enabled;
- AI structured-schema validation tests;
- semantic duplicate/correlation replay where enabled.

## Privacy

- analyst vs public geometry;
- exact-location leakage;
- vector-tile privacy when enabled;
- export policy;
- Humanitarian public projection;
- provider data-handling/privacy review for each enabled AI capability;
- proof that unreviewed AI-derived exact Humanitarian locations cannot leak to public output.

## AI evaluation

Report by capability and corpus, not one global "AI accuracy" number:

```text
classification precision/recall/F1
publication-decision agreement (shadow only unless independently promoted)
lifecycle agreement
coordinate extraction precision/recall
coordinate numeric error / false-precision rate
no-position/null accuracy
duplicate-resolution precision/recall/F1
false-merge rate
contradiction detection quality
AI vs deterministic divergence rate
provider/model-specific failure rate
latency distribution
usage/cost or quota consumption
```

A provider/model change affecting a promoted capability requires replay against the same labelled corpus before production rollout.

## Performance

Benchmark pre/post upgrade for nearby-event query, AIS bbox/time, fusion candidate generation, track retrieval, map load/pan/zoom and DB size/index overhead. When AI is enabled also measure model-call latency, queue/backpressure impact and percentage of observations requiring model calls after deterministic candidate filtering.

## Failure/degradation

Prove behaviour for:

- provider timeout;
- provider 429/quota exhaustion;
- provider 5xx/outage;
- malformed/non-schema model output;
- model refusal/empty result;
- embedding provider unavailable;
- model version change;
- deterministic-only operation with all AI disabled.

Core ingestion, storage, privacy and public policy must remain safe in every case.

## Operations and observability

Prove fresh deploy, migration, backup, restore, worker restart, DB reconnect, invalid geodata rejection and artifact degradation.

Record at minimum ingestion failures, invalid/unpositioned geometry, derivation failures, spatial query latency, AIS volume, drift failures, geodata import version and—where enabled—AI invocation count, provider/model, validation failures, latency, rate limiting, shadow divergence and promotion state.

## Documentation

Final docs describe canonical spatial model, geometry evidence, DB/index architecture, ingestion, privacy projection, QGIS workflow, deployment/restore, interoperability where enabled, AI provider abstraction, model-derived evidence semantics, promotion gates, evaluation corpus and removed legacy architecture.

---

# 21. Recommended milestone dependency graph

```text
fixes.md COMPLETE
      ↓
LIVE DATA + LIFECYCLE AUDIT (mandatory immediate first task)
      ↓
M0 Legacy census
      ↓
M1 PostGIS foundation
      ↓
M2 Canonical spatial model
      ↓
M3 Spatial + temporal candidate retrieval
      ↓
M4 Humanitarian geolocation V2
      ↓
M4A AI provider + shadow evidence infrastructure
      ↓
 ┌────┴────────────────────┐
 ↓                         ↓
M4B Multimodal          M4C Semantic correlation
Humanitarian evidence   / duplicate intelligence
 └───────────┬─────────────┘
             ↓
M5 H3 (optional if justified)
      ↓
M6 GDAL/OGR ingestion
      ↓
M7 QGIS QA
      ↓
M8 Vector-tile scaling (only when measured)
      ↓
M9 Raster/ocean architecture (when required)
      ↓
M10 AIS scale
      ↓
M11 Docker/Ansible reproducibility
      ↓
M12 GIS interoperability (only on demand)
      ↓
M14 Legacy deletion
      ↓
M15 Production qualification
```

M13 is a standing non-goal gate throughout the program.

M4B and M4C may proceed independently only after M4A passes its exit gate and only when they do not compete for authority over the same data path. No model capability may skip directly from implementation to production authority.

Parallel work elsewhere is allowed only when milestones do not modify the same schema/contracts and each independently satisfies its exit gate.

---

# 22. Definition of DONE

The upgrade program is DONE only when:

1. `fixes.md` remains green after all upgrades;
2. production Live cases have a canonical evidence-backed lifecycle and explicit event/update/state timestamps;
3. stale/superseded Drift products cannot appear operationally current;
4. Alarm Phone updates/resolutions/reopens are linked to canonical incidents rather than rendered as unrelated posts;
5. PostGIS is the canonical spatial query layer;
6. source/reported/derived/uncertainty/public geometry are distinguishable;
7. high-value spatial queries no longer depend on scattered ad-hoc loops;
8. Humanitarian location is uncertainty-aware and privacy-safe;
9. imported geography is versioned and provenance-aware;
10. large map delivery is scalable if measured volume justified tiles;
11. raster/model data has an explicit artifact architecture when used;
12. AIS scale limits are measured rather than guessed;
13. deployment is reproducible;
14. model providers are replaceable and cannot bypass canonical evidence/publication policy;
15. every enabled AI capability has a labelled evaluation corpus, persisted provenance, deterministic degradation path and explicit promotion state;
16. no AI-derived exact Humanitarian location or allegation can reach public output outside deterministic privacy/evidence gates;
17. legacy compatibility introduced during migration has been removed;
18. repository-wide legacy audit has no unexplained production residue;
19. production qualification demonstrates correctness, privacy, performance, provider degradation and recovery on the final commit.

The target is not "more GIS tools" or "AI everywhere". The target is a simpler, more rigorous SeaCommons whose geospatial and evidence-intelligence capabilities are first-class, testable, reproducible, privacy-safe and operationally credible.
