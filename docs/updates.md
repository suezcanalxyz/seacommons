# SeaCommons — Post-Stabilization Geospatial & Data Intelligence Upgrade Plan

> **Execution order:** `docs/fixes.md` remains authoritative until fully completed. Do not start this plan while any required `fixes.md` milestone, migration, replay, integration, privacy, CI, or production verification gate is still open.
>
> **Purpose:** raise SeaCommons from a stabilized maritime OSINT application to a production-grade geospatial and evidence-intelligence infrastructure without accumulating another layer of legacy. This is a migration program, not a feature wishlist.

---

# FIRST PRIORITY AFTER `fixes.md` CLOSES — LIVE HUMANITARIAN OSINT + LIVING INCIDENT DATASET

Before PostGIS, AI enrichment, new geospatial infrastructure or any other upgrade milestone, inspect and correct the **actual production Live dataset and rendered Live UI**. Do not infer correctness from fixtures or unit tests.

The Humanitarian side must stop behaving like a feed of posts and become a **living incident-intelligence dataset**:

```text
SOURCE / REPORT / MEDIA ITEM
        ↓
immutable SourceObservation
        ↓
normalization + extraction + preservation
        ↓
spatial / temporal / identity candidate retrieval
        ↓
correlation / duplicate decision
        ↓
canonical HumanitarianIncident
        ↓
append-only evidence + lifecycle updates
        ↓
assessment / contradiction handling / review
        ↓
current operational projection
        ↓
Live / Drift / Archive / analyst views
```

A source post is evidence. It is not automatically the incident itself.

## Senior OSINT methodology baseline

SeaCommons should follow the operational principles used by serious event-data and digital-investigation systems:

1. **Living dataset, stable incident identity.** Once an incident is created, better later information updates the same canonical incident instead of creating a new unrelated record. Corrections, merges, source additions, location refinements and outcome updates must preserve a stable incident identity and a revision trail.
2. **Immutable source evidence.** Original observations are never overwritten by later interpretation. Store the raw/source reference, capture time, source time, retrieval time, canonical URL/identifier, hashes where applicable, media metadata and preservation status.
3. **Evidence and assessment are separate.** A source claim, a normalized field, an analyst assessment and a public projection are different objects. Never collapse them into one mutable row without provenance.
4. **Triangulation over source prestige.** Multiple independent sources may strengthen an assessment; repeated syndication/copying of one source does not. Track source independence and circular reporting risk.
5. **Conservative uncertainty.** Conflicting reports remain conflicting until resolved. Do not silently choose the most convenient number, location or outcome.
6. **Coverage is measurable.** “Following the news” means maintaining a versioned source-coverage strategy by geography, language, topic and source type, with known gaps and outages.
7. **Historical integrity matters.** Adding a new source changes observable event volume. Coverage changes must be logged and, when feasible, historically backfilled before trend comparisons are trusted.
8. **Preservation before disappearance.** Time-sensitive online evidence should be archived/preserved as early as practical because posts, pages and media may later be edited or deleted.
9. **Chronology is first-class.** Distinguish source event time, publication time, observation time, ingestion time, update time, lifecycle transition time and model-computation time.
10. **Operational state is evidence-based.** Silence is not resolution. Age may change visibility or review priority, but lifecycle must describe what evidence supports.
11. **Public safety/privacy outranks analytic completeness.** Exact vulnerable-person location, private identifiers and sensitive raw humanitarian material must remain governed by publication/privacy policy.
12. **Every automated decision is replayable.** Persist enough structured evidence, rule/model version and decision rationale to reproduce why SeaCommons correlated, updated, resolved, reopened, published or withheld a case.

These principles are consistent with mature event-data practice that treats datasets as continuously revised rather than immutable snapshots; with professional digital open-source investigation standards that emphasize collection, preservation, verification and metadata; and with humanitarian data-responsibility practice that prioritizes safe and ethical information management.

---

## A. Immediate production Live audit

Audit at minimum:

```text
/api/v1/live/signals
/api/v1/live/drifts
/api/v1/live/archives
public edge projection
rendered Humanitarian Live map/panel
Alarm Phone source threads and repost/update chains
NGO / authority / news updates correlated to Humanitarian cases
persisted IntelEvent / SourceObservation / DriftResult rows behind each visible case
```

For every currently visible Humanitarian case reconstruct:

```text
incident_id / event ids
source observation ids
source observed_at
source published_at
received_at
event timestamp used by Live
first publication time
latest source update time
latest correlated update time
state_changed_at
resolved_at when known
Drift origin observation/time
Drift model created_at / completed_at
current lifecycle state
why that lifecycle state was selected
whether the marker is still on Live
whether a Drift is still on Live
which source/evidence currently supports each public field
```

Treat stale Drift geometry, impossible timers, duplicate Alarm Phone markers, unresolved events that silently disappear, resolved events that remain operational-looking, incorrect coordinates and unlinked follow-up reports as data-model/pipeline defects, not cosmetic UI issues.

Required anomaly flags include:

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
UNLINKED_FOLLOWUP_REPORT
CONFLICTING_OUTCOME_WITHOUT_REVIEW
CIRCULAR_CORROBORATION
SOURCE_COVERAGE_GAP
SOURCE_STALE_OR_DOWN
```

Create privacy-redacted regression fixtures from real production failures. The audit is complete only when every unexplained visible anomaly has a code/data-path explanation and a test or remediation task.

---

## B. Canonical Humanitarian incident model

Persist a canonical `HumanitarianIncident` with stable identity. Source observations remain immutable evidence linked to it.

Minimum canonical fields:

```text
incident_id
reported_at
last_update_at
state_changed_at
resolved_at
archived_at
lifecycle
case_type
people_claims[]
current_people_assessment
outcome_claims[]
current_outcome_assessment
location_claims[]
current_location_evidence_id
current_location_precision
current_drift_id
source_observation_ids[]
correlated_incident_ids[]
supporting_evidence_ids[]
contradicting_evidence_ids[]
assessment_confidence
review_status
revision
created_at
updated_at
```

Do not overwrite conflicting source claims. Example:

```text
Alarm Phone: ~56 people
NGO source: 59 people
authority report: 61 people

incident.current_people_assessment = 59
assessment basis = [observation A, observation B]
contradiction = observation C
confidence = medium
```

The public API may expose only the bounded/appropriate assessment, but the internal evidence graph must retain all source claims.

---

## C. Canonical lifecycle

Minimum lifecycle states:

```text
reported         first credible distress observation received
active           evidence supports an ongoing incident
needs_review     updates exist but outcome/correlation is ambiguous
unresolved_stale no recent evidence, outcome unknown; operational confidence decayed
resolved         credible evidence says immediate distress/search is concluded
archived         case is historical and no longer operationally Live
reopened         credible new evidence after resolution indicates renewed/continuing danger
```

Rules:

- `archived` must never mean merely “nothing heard for 24h”.
- `unresolved_stale` explicitly represents missing outcome evidence.
- time can reduce display prominence or trigger review, but cannot manufacture a rescue/resolution.
- resolved cases continue receiving later evidence and corrections.
- a reopened case preserves the previous resolution transition; do not erase history.
- ambiguous source updates must not silently resolve or reopen a case.

Every transition persists:

```text
incident_id
from_state
to_state
transition_at
effective_at
reason_code
supporting_observation_ids[]
contradicting_observation_ids[]
correlation_method
rule/model version
confidence
review_required
reviewed_by/reviewed_at when applicable
```

---

## D. Incident-follow-up engine — Humanitarian must keep following the news

After a case opens, create an explicit `IncidentWatch` rather than relying on generic feed polling.

The watch builds a search/correlation profile from:

```text
source thread / post ids
coordinates + uncertainty
named places
people-count range
vessel description
route / departure / destination
case type
NGO / authority references
known vessel identities when publishable internally
keywords / named entities
language variants
```

The watcher searches available sources for updates and emits new immutable observations. It does not directly mutate the incident.

Suggested cadence is risk-based rather than one fixed interval:

```text
ACTIVE / REOPENED
  highest follow-up priority

NEEDS_REVIEW
  high follow-up + analyst queue

RESOLVED 0–24h
  high follow-up for outcome confirmation/corrections

RESOLVED 1–7d
  periodic follow-up for disembarkation, casualties, missing, interception/return, official/NGO corrections

7–30d
  low-frequency enrichment / historical correction

ARCHIVED
  no operational polling by default, but newly ingested evidence may still reopen or revise history
```

Do not implement “follow all news” as an unbounded LLM/web crawl. Build bounded, auditable source adapters and queries with explicit coverage and failure metrics.

---

## E. Source Coverage Matrix

Create a versioned Source Registry + Coverage Matrix.

Each source records at minimum:

```text
source_id
name
source_type
operator/organisation
geographic coverage
route coverage
languages
content types
collection method
polling cadence
expected publication latency
historical coverage start
access/licence/terms
privacy constraints
preservation capability
current health
last successful fetch
known biases / limitations
source independence group
active_from / active_to
```

Humanitarian source categories should include, where legally/technically available and justified:

```text
Alarm Phone and relevant source threads
SAR NGOs / rescue organisations
official NGO RSS / statements
IOM / Missing Migrants / DTM outputs
UNHCR / OCHA / ReliefWeb humanitarian reporting
coastguard / MRCC / government statements
local and regional Mediterranean media
international media
verified specialist journalists / monitors
public social feeds with source-specific rules
relevant vessel/AIS evidence as corroboration, never as a humanitarian source substitute
```

Maintain geographic coverage profiles at least for:

```text
Central Mediterranean
Eastern Mediterranean
Western Mediterranean
Aegean
Adriatic / Ionian where relevant
Atlantic / Canary route when included in product scope
```

Coverage health must answer:

```text
What are we watching?
Which languages?
Which feeds are currently healthy?
How stale is each source?
Which routes have only one source family?
Which areas have no local-language coverage?
Did the source mix change recently?
Are apparent trend changes actually collection changes?
```

A new source entering production requires:

1. source profile and reason for inclusion;
2. duplicate/correlation evaluation;
3. known bias/coverage notes;
4. historical/backfill assessment;
5. before/after coverage metrics;
6. source-change log entry.

Where feasible, backfill the source before using its addition for trend comparisons. If backfill is impossible, mark the coverage break explicitly so dashboards do not interpret collection expansion as a real-world incident spike.

---

## F. Source preservation and provenance

For every important online source observation preserve enough evidence to verify what SeaCommons saw at collection time.

Persist when legally/technically permitted:

```text
canonical source URL / platform id
source account / publisher id
source publication timestamp
retrieved_at
raw content or permitted snapshot reference
media attachment references
content hash
media hash where retained
HTTP/source metadata useful for replay
parent/reply/repost/thread relations
language
parser/extractor version
archival status / archive URI when available
```

Original evidence is append-only. Corrections create new observations or revision records; they do not rewrite the source item SeaCommons originally ingested.

Preservation storage and public exposure are separate concerns. Sensitive/private humanitarian material may be retained under restricted policy while never appearing in public projection.

---

## G. Correlation and duplicate handling

Required decision taxonomy:

```text
SAME_INCIDENT
RELATED_INCIDENT
NEW_INCIDENT
UNCERTAIN
```

Candidate generation should use deterministic evidence first:

```text
thread/reply identity
source identifiers
spatial overlap + uncertainty
time overlap
people-count compatibility
vessel description
route/departure/place references
NGO / authority references
known source-specific case identifiers
```

Optional lexical/embedding/model similarity may rerank candidates later, but may not be the sole evidence for merging.

Persist a `CorrelationDecision` containing:

```text
observation_id
candidate_incident_id
decision
supporting_features[]
contradicting_features[]
source_independence assessment
method/version
confidence
review state
```

False merges are more dangerous than temporary duplicates. Prefer `UNCERTAIN` + review when evidence is weak.

Detect circular reporting: multiple articles quoting the same original report count as one evidence lineage, not multiple independent corroborations.

---

## H. Claim-level evidence and contradiction model

Important changing fields should be represented as claims rather than repeatedly overwritten values:

```text
location
people aboard
rescued count
missing count
death count
vessel type
engine condition
water ingress
last contact
interception
return/deportation
disembarkation port
rescuing vessel/authority
outcome
```

Each claim records:

```text
claim_type
value / structured value
observation_id
source_id
claimed_at
observed_at
confidence if source supplies one
extraction method/version
verification status
supersedes claim id when explicit
```

The canonical incident assessment selects or bounds claims while retaining disagreement.

Do not implement one generic numeric `trust_score` that automatically decides truth. Source reliability is contextual: a source may be strong for direct distress reports but weaker for final casualty figures, or vice versa.

---

## I. Alarm Phone timer semantics

The UI timer must have an explicit semantic source. Never calculate one generic age from whichever timestamp exists.

Expose:

```text
reported_at       original incident report/observation time
last_update_at    latest relevant evidence attached to the case
state_changed_at  latest lifecycle transition effective time
data_received_at  when SeaCommons received latest evidence
resolved_at       evidence-backed resolution time when known
```

Public UI should normally display:

```text
ACTIVE
Reported 4h 12m ago · Updated 18m ago

RESOLVED
Reported 9h ago · Resolved 2h 14m ago · Updated 37m ago

UNRESOLVED_STALE
Reported 31h ago · Last update 27h ago · Outcome unknown
```

Never reset incident age because of duplicate ingestion, a classifier rerun, projection refresh or Drift recomputation.

Normalize timestamps to UTC and test timezone offsets, missing timezone, delayed ingestion, reposts, duplicate ingestion and out-of-order updates.

---

## J. Drift lifecycle belongs to the incident

A Drift is a derived model product, not an independently live incident.

Rules:

```text
ACTIVE/REOPENED + valid maritime point -> current Drift may be visible
NEEDS_REVIEW -> Drift visible only if origin evidence remains eligible and policy permits
UNRESOLVED_STALE -> hide/freeze operational Drift according to explicit stale-model policy; never imply current search certainty
RESOLVED -> immediately remove/freeze Drift from operational Live
ARCHIVED -> no operational Live Drift
new accepted position -> old Drift becomes superseded
REOPENED -> create a new versioned Drift only from newly valid evidence
region-only/unpositioned -> no fabricated Drift
```

Persist:

```text
drift_id
incident_id
origin_observation_id
origin_timestamp
origin_geometry_evidence_id
model/version
forcing inputs/version
created_at
completed_at
status = current | superseded | resolved | failed | historical
superseded_by
```

`public_drift_collection()` must select only the incident's current operational Drift; it must not rediscover arbitrary completed historical jobs and publish them as current.

---

## K. Archive and revision semantics

Live and Archive are projections over the same incident history.

Archive must retain:

```text
stable incident id
first report time
final/current lifecycle
revision number
resolution/outcome when known
bounded public location
historical Drift references when publication-safe
source-count / provenance summary
last revised_at
```

Later evidence may revise an archived incident without reintroducing it to operational Live unless lifecycle rules actually reopen it.

Maintain an internal revision/change log describing at least:

```text
incident created
observation attached
field assessment changed
location refined
lifecycle transition
incident merge/split
source correction
historical backfill
public projection changed
```

---

## L. Humanitarian review queue

Automation must route uncertainty instead of hiding it.

Create review reasons such as:

```text
AMBIGUOUS_DUPLICATE
CONFLICTING_LOCATION
CONFLICTING_OUTCOME
RESOLUTION_LOW_CONFIDENCE
REOPEN_AFTER_RESOLUTION
PEOPLE_COUNT_DIVERGENCE
COORDINATE_OCR_VS_IMAGE_CONFLICT
STALE_ACTIVE_CASE
SOURCE_THREAD_BROKEN
CIRCULAR_REPORTING_RISK
PUBLICATION_PRIVACY_REVIEW
```

Review decisions must themselves be persisted with who/when/reason, and become replayable evidence for lifecycle/publication decisions.

---

## M. Coverage + dataset quality metrics

Do not report only ingestion counts. Track:

```text
source success rate / latency / staleness
coverage by region / route / language / source family
single-source incident rate
multi-independent-source corroboration rate
duplicate rate
false-merge rate from labelled corpus
unresolved-stale rate
median time report -> first ingestion
median time report -> Live publication
median time update -> incident attachment
median time resolution evidence -> lifecycle resolution
location-positioned rate by method
location correction rate
outcome-known rate
historical revision rate
source-coverage changes over time
stale Drift count
Drift-after-resolution count
```

Trend dashboards must expose or account for material collection-coverage changes.

---

## FIRST-PRIORITY EXIT GATE

This first priority is complete only when:

- production Live marker/Drift/timer inventory is committed;
- every visible Humanitarian item maps to a canonical incident or an explicit review state;
- source observations are immutable and provenance-bearing;
- Alarm Phone updates/resolutions/reopens modify the same incident when evidence supports correlation;
- silence alone cannot produce `resolved` or `archived` semantics;
- `unresolved_stale` or equivalent explicitly represents unknown outcome after evidence goes quiet;
- stale/superseded Drift cannot remain operationally current;
- timers use explicit event/update/state timestamps;
- source coverage and source health are measurable;
- follow-up watches continue to ingest relevant news after initial report and after resolution for bounded enrichment windows;
- circular reporting does not count as independent corroboration;
- new source additions have coverage/backfill/change-log semantics;
- archived incidents remain revisable without being operationally reopened unless evidence requires it;
- Live and Archive are projections of one incident history rather than separate incompatible datasets.

---

# 0. Operating principle

Every milestone must do at least one of the following:

1. remove an architectural limitation;
2. replace duplicated/ad-hoc logic with a canonical subsystem;
3. measurably improve correctness, observability, performance, replayability, privacy or interoperability;
4. delete legacy code or create an explicit deletion path.

**Hard rule:** every new subsystem must replace, simplify or measurably improve an existing path. Do not leave previous authoritative paths alive indefinitely.

**AI rule:** model output is evidence enrichment or candidate analysis, never an unproven source of truth.

---

# 1. Preconditions — `fixes.md` must be closed first

Before starting M0, prove on the exact `main` commit used as the upgrade baseline:

- every required `docs/fixes.md` milestone complete;
- backend suite green;
- lint/typecheck/build green;
- DB migrations tested on PostgreSQL and retained SQLite-compatible test paths;
- deterministic replay gates green;
- Humanitarian and Maritime live/public projections verified;
- privacy contracts verified;
- no unresolved P0/P1 stabilization defect hidden behind skips/fallbacks/mock-only paths;
- latest production verification documented;
- FIRST PRIORITY Humanitarian Live/lifecycle/source-coverage gate above completed.

If any fail, return to stabilization/first-priority work.

---

# 2. Mandatory agent execution protocol

```text
1. sync main
2. confirm fixes.md closed
3. confirm FIRST PRIORITY Live/Humanitarian gate remains green
4. read updates.md
5. inspect current implementation
6. identify legacy path being replaced/retained
7. write failing tests / migration / replay fixtures first
8. implement smallest coherent vertical slice
9. run targeted tests
10. run full relevant suites
11. measure performance/query/model impact where applicable
12. review duplicate logic / compatibility / dead code
13. document canonical path + removed legacy
14. document temporary compatibility + deletion milestone
15. open one reviewable PR
16. merge only after green CI + exit-gate evidence
17. update main and continue
```

For every PR include:

```text
Existing implementation:
Target implementation:
Legacy removed:
Temporary compatibility retained:
Deletion milestone:
Files touched:
Tests proving parity/correctness:
Migration/replay evidence:
Known limitations:
```

AI-enabled PRs additionally include:

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

---

# 3. Global non-negotiable constraints

1. PostGIS does not replace evidence semantics, provenance, confidence, review or publication policy.
2. Spatial SQL performs retrieval/geometry candidate generation; domain reasoning remains explicit and testable.
3. Raw, reported, derived, uncertainty and public geometries remain distinguishable.
4. No inferred geometry may be presented as reported position.
5. Humanitarian privacy takes precedence over analytic convenience.
6. Never destroy original source geometry/content when producing corrected or public derivatives.
7. Every derived geometry/result carries method/version/input provenance.
8. Unknown CRS is a validation failure, not a guess.
9. No speculative dependency/index; require a measured query/capability.
10. Every compatibility layer has a removal milestone.
11. AI providers are replaceable adapters; provider structures do not leak into canonical domain models.
12. Model output conforms to typed schemas before domain use.
13. AI failure/rate limits/outage degrade to deterministic behavior and never block core ingestion.
14. No Humanitarian publication/lifecycle/private-location decision may rely solely on an LLM/VLM.
15. VLM coordinates are candidate/derived claims, never automatically `reported_geometry`.
16. Embeddings generate/rerank candidates; they do not prove same-event identity.
17. AI-generated allegations require the same evidence/review gates as all other hypotheses.
18. Sensitive Humanitarian content may be sent to a provider only when data-processing/privacy policy permits it.
19. Persist enough model/result provenance to replay decisions without regenerating the external response.
20. Coverage changes and source outages are part of data quality and must be visible to operators.

---

# 4. Target architecture

```text
SOURCE / SENSOR / DATASET
        ↓
SOURCE PRESERVATION + SourceObservation
        ↓
DETERMINISTIC EXTRACTION / NORMALIZATION
        ↓
GEOSPATIAL NORMALIZATION
        ↓
SPATIAL + TEMPORAL CANDIDATE RETRIEVAL
        ↓
OPTIONAL AI / SEMANTIC CANDIDATE ENRICHMENT
        ↓
CORRELATION + CLAIM/EVIDENCE GRAPH
        ↓
INCIDENT / EPISODE / ASSESSMENT
        ↓
LIFECYCLE + REVIEW
        ↓
PUBLICATION POLICY
        ↓
PRIVACY-AWARE PUBLIC GEOMETRY / DATA
        ↓
REST / WS / VECTOR TILE / GIS EXPORT
```

Forbidden shortcut:

```text
SOURCE → LLM/VLM → production truth
```

Canonical vector target:

```text
PostgreSQL + PostGIS
        ↑
GeoAlchemy2
        ↑
Python domain services ↔ Shapely / PyProj
```

AI target remains provider-agnostic:

```text
AIProvider
  ├─ NVIDIA NIM-compatible
  ├─ Groq-compatible
  ├─ Gemini-compatible multimodal
  └─ OpenRouter-compatible benchmark/fallback
        ↓
typed result
        ↓
persisted AI evidence/provenance
        ↓
domain validator / correlator
```

Provider names are candidates, not architecture.

---

# 5. M0 — Legacy eradication and architecture census

Inventory backend, DB, migrations, tests, frontend contracts, edge/live publisher, fixtures and deployment paths.

Search/classify at minimum:

```text
legacy deprecated compat compatibility fallback old_
TODO migration remove after remove once dual write
maritime_domain lat/lon assumptions area_geojson
haversine bearing bbox point_to_segment
GeoJSON in generic JSON
provider-specific AI helpers
ad-hoc OCR/model calls
embedding/vector experiments
post-as-incident assumptions
stored lifecycle shortcuts
arbitrary completed Drift lookup
```

Each item: `KEEP | MIGRATE | DELETE | TEMP COMPAT` with deletion milestone.

**M0 exit gate:** complete inventory; no unclassified known legacy path; no production behavior change except proven dead-code removal.

---

# 6. M1 — PostGIS geospatial foundation

Introduce PostGIS, GeoAlchemy2, Shapely and PyProj only as required by the first slice.

Introduce canonical `location_geom` while scalar lat/lon remain temporary compatibility. Writes pass through one helper; divergence is an error.

Create GiST indexes only for measured query paths. Benchmark recent positioned events, bbox, radius search and vessel positions.

Migration backfills valid coordinates, flags invalid ranges, preserves null/unpositioned states and is restart-safe.

**M1 exit gate:** PostGIS active; one canonical spatial path; query test and migration evidence; no duplicated authority.

---

# 7. M2 — Canonical spatial evidence model

Explicit roles:

```text
reported_geometry
derived_geometry
uncertainty_geometry
public_geometry
```

Use typed geometry-evidence records when provenance is multi-valued. Preserve raw AIS points. Drift migrates from generic JSON toward typed trajectory/cone geometry with model/version/forcing inputs/start time.

**M2 exit gate:** source geometry never overwritten; roles documented/tested; generic metadata geometry no longer authoritative where typed replacement exists.

---

# 8. M3 — Spatial query migration and deterministic candidate generation

Move candidate retrieval/math into PostGIS while interpretation stays explicit in Python.

Priority:

```text
nearby events
nearby vessels
bbox
point-in-zone
infrastructure proximity
track/area intersection
drift/track intersection
nearest object
spatiotemporal fusion shortlist
dedup/correlation shortlist
```

DB answers which records are plausible candidates; domain layer answers whether evidence represents the same incident/episode/hypothesis.

**M3 exit gate:** measured query improvement/justification; no replay regression; superseded math removed.

---

# 9. M4 — Humanitarian geolocation V2

Supported evidence:

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

Do not collapse claims early. Preserve exact source evidence and attach derived uncertainty-aware geometry.

Replay corpus includes Alarm Phone text coordinates, map screenshots, contradictory text/image claims, land cases, coastline ambiguity, invalid OCR, exact-coordinate updates and no-position negatives.

**M4 exit gate:** no fake precision; analyst/public location separate; source geometry preserved; method accuracy measured.

---

# 9A. M4A — AI evidence-enrichment foundation

Create a canonical provider-neutral interface for:

```text
structured text extraction
classification
multimodal extraction
embeddings
reranking
bounded correlation/reasoning
```

Persist provider/model/version, capability, schema/prompt version, input observation IDs, timestamp, latency, status/errors, usage metadata, structured result and validation status.

Initial mode is shadow:

```text
deterministic_result = current_pipeline(input)
ai_candidate = ai_pipeline(input)
compare_and_record(...)
return deterministic_result
```

**M4A exit gate:** provider abstraction proven; all AI disable-able; outage does not block deterministic pipeline; no public decision depends on AI.

---

# 9B. M4B — Multimodal Humanitarian geolocation

Workflow:

```text
source image/screenshot
   ↓
deterministic OCR + VLM structured extraction
   ↓
claim comparison
   ↓
validation / land-sea / map plausibility
   ↓
candidate derived geometry + uncertainty
   ↓
review or bounded promotion
```

No model may invent exact coordinates to fill missing data. Persist disagreements.

Evaluation includes coordinate detection precision/recall, numeric accuracy, false-precision rate, land/sea consistency, OCR agreement and correct null rate.

---

# 9C. M4C — Semantic correlation and duplicate intelligence

Cascade:

```text
new observation
   ↓
PostGIS + temporal shortlist
   ↓
optional lexical/embedding/reranking
   ↓
correlation rules + evidence comparison
   ↓
SAME_INCIDENT | RELATED_INCIDENT | NEW_INCIDENT | UNCERTAIN
```

Persist supporting/contradicting features and source-independence/circular-reporting analysis.

A false merge threshold is a release gate. Model/provider outage must leave deterministic correlation functional.

---

# 10. M5 — H3 spatial intelligence layer

Use only where measured value exists for privacy aggregation, density, clustering, heatmaps or regional summaries. Geometry remains authoritative.

---

# 11. M6 — Geospatial dataset ingestion with GDAL/OGR

Reproducibly ingest justified vector/raster reference geography. Record source/version/licence/retrieval/checksum/CRS/transforms/count/validation.

Reject/quarantine invalid geometry and unknown CRS rather than silently repairing source defects.

---

# 12. M7 — QGIS operational QA

Provide read-only QA layers for raw/reported/derived/uncertainty/public geometry, Humanitarian incidents, AIS tracks, Drift products, reference zones and AI-derived candidates.

Sensitive exact humanitarian location remains role-restricted.

---

# 13. M8 — Map delivery / vector-tile scaling

Adopt vector tiles only after measured GeoJSON volume justifies them. Public/private projection and cache invalidation remain policy-aware.

---

# 14. M9 — Raster and ocean-data architecture

Preferred path:

```text
source → xarray/GDAL → COG/object storage → rio-tiler/TiTiler when justified → map/analyst tools
```

PostgreSQL stores metadata/provenance rather than becoming a raster archive.

---

# 15. M10 — AIS spatial/time-series scale

Start with native PostgreSQL/PostGIS indexes/partitioning/retention and measured query plans. Evaluate TimescaleDB only after demonstrated bottlenecks.

---

# 16. M11 — Reproducible infrastructure

Automate VM/runtime/PostgreSQL/PostGIS/reverse proxy/TLS/workers/secrets references/backups/logging/monitoring/restart policy with Docker/Ansible or the smallest justified reproducible approach.

Provider outage must not prevent deterministic API/ingestion startup.

---

# 17. M12 — GIS interoperability

Expose GeoJSON/GeoPackage/WMS/WFS/WMTS/OGC API Features only when a real consumer requires them. Privacy policy applies to every export.

---

# 18. M13 — Explicit non-goals / prohibited premature dependencies

Do not add technologies merely because they are common:

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

Likewise no NIM/Groq/Gemini/OpenRouter provider enters production because a free tier exists. Each provider must serve a measured capability and remain replaceable.

---

# 19. M14 — Final legacy deletion

After parity:

- remove spatial dual-write authority;
- remove legacy metadata geometry authority;
- remove superseded geospatial helpers;
- remove post-as-incident and stale lifecycle shortcuts;
- remove historical Drift rediscovery as current-state logic;
- remove obsolete provider/model bypasses and temporary compatibility;
- retain historical provenance readability.

Repository-wide audit all remaining legacy/deprecated/compat/fallback/TODO-migration markers.

---

# 20. M15 — Production qualification

Correctness:

- full backend/web suites;
- PostGIS migration/query tests;
- Humanitarian incident/lifecycle replay;
- source-correlation replay;
- Alarm Phone update/resolution/reopen replay;
- Drift lifecycle replay;
- AIS/fusion replay;
- AI contract/schema/evaluation tests where enabled.

Privacy:

- analyst/public geometry separation;
- exact-location leakage tests;
- Humanitarian publication contract;
- provider data-handling review;
- proof unreviewed AI-derived exact locations cannot reach public output.

Operational data-quality qualification additionally reports:

```text
source coverage by route/language/family
source outage/staleness
incident correlation precision/recall
false merge rate
unresolved-stale rate
resolution latency
historical revision rate
circular-reporting detection
stale Drift rate
timer correctness
public/edge/VM parity
```

AI evaluation is capability-specific, not one global score.

Failure testing includes provider timeout/429/5xx/malformed output/refusal/version change and deterministic-only operation.

---

# 21. Recommended dependency graph

```text
fixes.md COMPLETE
      ↓
LIVE HUMANITARIAN AUDIT
      ↓
CANONICAL INCIDENT + LIFECYCLE
      ↓
SOURCE COVERAGE MATRIX + FOLLOW-UP WATCHES
      ↓
PROVENANCE / PRESERVATION / CORRELATION / REVIEW
      ↓
PRODUCTION LIVE + DRIFT + TIMER REPLAY GATE
      ↓
M0 Legacy census
      ↓
M1 PostGIS
      ↓
M2 Spatial evidence model
      ↓
M3 Spatial/temporal candidate retrieval
      ↓
M4 Humanitarian geolocation V2
      ↓
M4A AI shadow foundation
      ↓
 ┌────┴───────────────┐
M4B multimodal     M4C semantic correlation
 └───────┬────────────┘
         ↓
M5 H3 if justified
      ↓
M6 geodata ingestion
      ↓
M7 QGIS QA
      ↓
M8 tiles if justified
      ↓
M9 raster/ocean
      ↓
M10 AIS scale
      ↓
M11 reproducible infrastructure
      ↓
M12 interoperability if required
      ↓
M14 legacy deletion
      ↓
M15 production qualification
```

M13 is a standing non-goal gate.

---

# 22. Definition of DONE

The upgrade is DONE only when:

1. `fixes.md` remains green;
2. Humanitarian Live is incident-centric rather than post-centric;
3. production cases have stable IDs and immutable source observations;
4. lifecycle is evidence-backed with `unresolved_stale` distinct from `resolved/archived`;
5. Alarm Phone and other source updates attach to the same canonical incident when evidence supports it;
6. resolved and archived incidents remain revisable as new reporting arrives;
7. source coverage by route/language/source family is versioned and observable;
8. source outages and coverage changes cannot silently masquerade as real-world trend changes;
9. online source provenance/preservation is sufficient for replay and verification;
10. circular reporting is not counted as independent corroboration;
11. stale/superseded Drift cannot appear current;
12. Live timer semantics distinguish reported/update/state/received/resolved time;
13. review queues capture ambiguity instead of hiding it;
14. PostGIS becomes canonical spatial query layer;
15. source/reported/derived/uncertainty/public geometry are distinguishable;
16. Humanitarian geolocation is uncertainty-aware and privacy-safe;
17. model providers are replaceable and cannot bypass evidence/publication policy;
18. every enabled AI capability has labelled evaluation, provenance and deterministic degradation;
19. transitional legacy paths are removed;
20. production qualification demonstrates correctness, privacy, coverage integrity, performance, provider degradation and recovery on the final commit.

The target is not “more feeds”, “more GIS tools” or “AI everywhere”. The target is a rigorous maritime OSINT system where observations are preserved, incidents evolve as a living dataset, news updates are continuously correlated, uncertainty remains visible, source coverage is measurable, lifecycle is evidence-based, and public output remains privacy-safe and operationally credible.
