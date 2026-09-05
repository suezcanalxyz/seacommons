# SeaCommons — Maritime OSINT Platform Upgrade Plan

> **Authority:** `docs/fixes.md` remains authoritative until its production-closure gate is complete. This plan starts only after that gate is green on the exact `main` SHA used as baseline.
>
> **Target:** SeaCommons is a production-grade **maritime OSINT platform**. It continuously acquires open-source observations, preserves provenance, resolves entities and incidents, correlates independent evidence, follows cases over time, performs bounded geospatial/intelligence analysis, exposes reviewable assessments, and publishes privacy-aware outputs.
>
> **This document is executable.** Every section defines canonical objects, invariants, work packets, tests and exit gates. It is not a branding document and not a feature wishlist.

---

# 0. Platform definition

SeaCommons has two first-class operational verticals sharing one evidence platform:

```text
HUMANITARIAN OSINT
  distress / SAR / rescue / interception / missing / disembarkation / outcome

MARITIME INTELLIGENCE
  AIS integrity / identity / behaviour / dark activity / rendezvous /
  sanctions-linked facts / infrastructure context / hypotheses
```

Both use the same platform primitives:

```text
Source Registry
Connector / Collector
SourceObservation
PreservedArtifact
Claim
Entity
Relationship
CorrelationDecision
Incident / Episode
Assessment / Hypothesis
Watch
ReviewDecision
PublicationDecision
GeometryEvidence
Revision / AuditEvent
```

The shared canonical flow is:

```text
SOURCE
  ↓
CONNECTOR / COLLECTOR
  ↓
IMMUTABLE SourceObservation + provenance
  ↓
PRESERVATION / media / hashes where permitted
  ↓
DETERMINISTIC extraction + normalization
  ↓
CLAIMS + entities + geometry evidence
  ↓
SPATIAL / TEMPORAL / IDENTITY candidate retrieval
  ↓
CORRELATION / entity resolution / duplicate decision
  ↓
INCIDENT / EPISODE / ENTITY GRAPH
  ↓
WATCH + follow-up collection
  ↓
ASSESSMENT / contradiction / review
  ↓
PUBLICATION POLICY + privacy projection
  ↓
LIVE / ARCHIVE / API / EXPORT / ANALYST UI
```

Forbidden shortcuts:

```text
SOURCE → post-as-incident
SOURCE → LLM/VLM → production truth
completed Drift job → current operational Drift
single list match → behavioural allegation
silence → resolved
age → archived without lifecycle semantics
multiple copied articles → independent corroboration
```

---

# 1. Non-negotiable OSINT invariants

1. **Observation is not incident.** A source item is immutable evidence. Canonical incidents/episodes are derived, revisable objects.
2. **Stable identity.** Better later information updates the same incident/entity whenever evidence supports continuity; merges/splits keep redirects and revision history.
3. **Evidence and assessment are separate.** Raw/source claims, normalized claims, analyst/automated assessments and public projections are different records.
4. **Provenance is mandatory.** Every claim and derived output points back to observation IDs and method/version.
5. **Contradictions are data.** Conflicting claims are retained and surfaced; do not overwrite disagreement.
6. **Independent corroboration is explicit.** Syndication/copying does not multiply source independence.
7. **Coverage is measurable.** The platform knows what sources/regions/languages it covers, what is stale/down and when source mix changes.
8. **Historical integrity matters.** High-yield new sources require a backfill/coverage-break assessment before trend comparisons are trusted.
9. **Chronology is typed.** Event time, publication time, retrieval time, ingestion time, update time, lifecycle time and model-computation time are never interchangeable.
10. **Silence is not resolution.** No time threshold alone may claim rescue, interception, death, resolution or closure.
11. **False merge cost is high.** Prefer `UNCERTAIN` + review over an unsupported incident merge.
12. **Original geometry is preserved.** Reported, derived, uncertainty and public geometry are distinct.
13. **Privacy precedes convenience.** Humanitarian public outputs never inherit internal precision or private identifiers by accident.
14. **AI is bounded.** Models may extract, rank, classify or propose correlations, but may not silently become canonical truth.
15. **Every automated decision is replayable.** Rule/model/schema versions and supporting evidence are persisted.
16. **Live and Archive are projections of one history.** They are not separate truth stores.
17. **One authoritative path per concept.** Compatibility may exist temporarily only with an explicit deletion milestone.

---

# 2. Agent execution contract

The agent must treat this file as a dependency graph, not as permission to work broadly.

## 2.1 Work-packet rule

Before coding any packet, write a short implementation note in the PR body containing:

```text
Packet ID:
Problem observed:
Production path affected:
Canonical object/contract changed:
Existing authoritative path:
Target authoritative path:
Schema/migration delta:
Legacy to delete:
Temporary compatibility:
Deletion packet:
Tests to write first:
Replay/fixture evidence:
Observability added:
Privacy/publication impact:
Known non-goals:
```

Then execute only that packet.

## 2.2 PR boundary rule

One PR may change one semantic authority at a time. Examples of valid PR boundaries:

```text
observation provenance schema
incident lifecycle persistence
correlation decision persistence
source coverage registry
current-Drift ownership
Live timer contract
one connector adapter
one PostGIS query family
one AI shadow capability
```

Invalid PR boundary:

```text
"improve humanitarian pipeline"
"upgrade OSINT"
"refactor live"
"add AI intelligence"
```

If a packet requires unrelated schema, UI and infrastructure rewrites, split it unless they are required for one tested vertical slice.

## 2.3 TDD / replay order

For each packet:

```text
1. sync main
2. prove fixes.md closure still green
3. read this packet + direct dependencies
4. inspect production path and current DB schema
5. capture a failing regression fixture from real/redacted data where possible
6. write failing unit/integration/replay test
7. implement smallest vertical slice
8. run targeted tests
9. run relevant full suites
10. run migration up/down/re-up when schema changes
11. inspect duplicate authority / stale compatibility
12. verify public/privacy projection
13. verify observability
14. self-review diff against packet exit gate
15. open PR with evidence
16. merge only green
17. update main before next packet
```

## 2.4 Stop conditions

Stop the packet and report instead of widening scope when:

- required source data is inaccessible or terms prohibit planned collection;
- schema semantics are ambiguous enough to create two possible authorities;
- a migration cannot preserve existing provenance/history;
- privacy/publication impact is unclear;
- the packet needs a dependency scheduled later;
- a proposed model capability has no labelled evaluation corpus;
- a production anomaly cannot be reproduced/explained from data/code;
- a change would make source observation mutable;
- tests require inventing precision or truth not supported by evidence.

Do not solve stop conditions by adding silent fallback logic.

---

# 3. FIRST PRIORITY — Production Humanitarian Live as a real OSINT vertical

This is the first work after `fixes.md` closes. Do not start PostGIS, provider integrations or new GIS infrastructure first.

Goal: every Humanitarian item visible in production must be traceable from source observation through canonical incident, lifecycle, current geometry, current Drift, timer and publication decision.

## P0.1 — Production truth-table audit

Build a machine-readable audit over:

```text
/api/v1/live/signals
/api/v1/live/drifts
/api/v1/live/archives
edge/public projection
rendered Humanitarian Live UI
persisted IntelEvent / SourceObservation / DriftResult data
Alarm Phone threads/replies/reposts
correlated NGO / authority / news observations
```

For each visible case output:

```text
visible feature id
candidate incident id
source observation ids
source ids
reported/event time
source publication time
retrieved_at / received_at
last relevant update time
lifecycle + reason
state_changed_at
resolved_at if any
current location evidence id + method + precision
current Drift id + origin observation/time + status
marker visible yes/no
Drift visible yes/no
public timer values
expected timer values
publication decision
correlation candidates
anomaly flags
```

Required flags:

```text
STALE_DRIFT
DRIFT_AFTER_RESOLUTION
MULTIPLE_CURRENT_DRIFTS
DRIFT_ORIGIN_OLDER_THAN_CURRENT_POSITION
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

**Exit:** every unexplained visible anomaly has a code/data-path explanation and a redacted regression fixture or explicit remediation packet.

## P0.2 — Immutable SourceObservation + provenance boundary

Make `SourceObservation` the canonical source-evidence primitive.

Minimum fields:

```text
observation_id
source_id
source_item_id
canonical_url
parent/reply/repost/thread ids
published_at
observed_at
retrieved_at
ingested_at
language
raw_text_ref / permitted snapshot ref
media_refs[]
content_hash
parser/extractor version
collection_method
access/preservation status
raw metadata payload
```

Rules:

- idempotent collection by stable source identity/hash;
- corrections from the source become new observations or explicit source revisions;
- normalized fields never overwrite the captured source representation;
- deleted/edited source state may be recorded as a later observation;
- public exposure of raw content is a separate policy.

**Exit:** replay can reconstruct what SeaCommons saw and when; duplicate ingestion does not reset incident time.

## P0.3 — Canonical HumanitarianIncident

Create/persist a stable incident object independent of any one source post.

Minimum structure:

```text
incident_id
lifecycle
reported_at
last_update_at
state_changed_at
resolved_at
archived_at
case_type
source_observation_ids[]
current_location_evidence_id
current_people_assessment_id
current_outcome_assessment_id
current_drift_id
review_status
revision
created_at
updated_at
redirect/merge/split metadata
```

The incident owns current operational state. Source observations do not.

**Exit:** multiple updates to one real case can be attached without creating unrelated Live markers.

## P0.4 — Claim + assessment model

Important facts become claims, not mutable scalar truth:

```text
location
people aboard
rescued
missing
deaths
vessel description/type
engine/condition
water ingress
last contact
interception
return/deportation
disembarkation port
rescuing vessel/authority
outcome
```

Each claim:

```text
claim_id
claim_type
structured value
observation_id
source_id
claimed_at
observed_at
extraction method/version
verification status
explicit supersedes id if applicable
```

Assessment:

```text
assessment_id
incident_id
field/type
selected/bounded value
supporting_claim_ids[]
contradicting_claim_ids[]
method/version
confidence
review state
created_at
```

Never implement one global numeric source `trust_score` as truth arbitration.

**Exit:** conflicting people/location/outcome claims can coexist while public/internal assessment remains explicit and traceable.

## P0.5 — Evidence-based lifecycle

Canonical states:

```text
reported
active
needs_review
unresolved_stale
resolved
archived
reopened
```

Meaning:

```text
reported          credible initial distress evidence exists
active            current evidence supports ongoing danger/search
needs_review      material update/correlation is ambiguous
unresolved_stale  outcome unknown; fresh evidence has gone quiet
resolved          positive evidence supports conclusion of immediate distress/search
archived          no longer operationally Live; history retained
reopened          new credible evidence after resolution supports renewed/continuing danger
```

Every transition:

```text
transition_id
incident_id
from_state
to_state
transition_at
effective_at
reason_code
supporting_observation_ids[]
contradicting_observation_ids[]
method/version
confidence
review_required
review_decision_id
```

Rules:

- time alone may move `active -> unresolved_stale` only under an explicit stale-evidence policy;
- time alone cannot create `resolved`;
- `archived` is presentation/operational retirement after lifecycle policy, not a synonym for no update;
- later evidence may revise a resolved/archived incident;
- reopening retains prior transitions.

**Exit:** same input history always yields the same lifecycle replay; no stored ingestion-era shortcut can override canonical transition history.

## P0.6 — Humanitarian timer contract

Expose typed timestamps:

```text
reported_at
last_update_at
state_changed_at
resolved_at
data_received_at
```

UI semantics:

```text
ACTIVE
Reported 4h 12m ago · Updated 18m ago

RESOLVED
Reported 9h ago · Resolved 2h 14m ago · Updated 37m ago

UNRESOLVED_STALE
Reported 31h ago · Last update 27h ago · Outcome unknown
```

Rules:

- timer derives from explicit server timestamps;
- reruns, duplicate ingestion, projection refresh and Drift recomputation never reset incident age;
- UTC storage; offset-aware rendering;
- out-of-order source updates do not move `reported_at` forward.

Test delayed ingestion, timezone offsets, duplicate posts, reposts, source edits, missing timezone and out-of-order arrival.

**Exit:** public timer can be reconstructed from API fields with no hidden frontend inference.

## P0.7 — Drift ownership and supersession

A Drift is a versioned derived artifact owned by an incident.

Minimum record:

```text
drift_id
incident_id
origin_observation_id
origin_geometry_evidence_id
origin_timestamp
model/version
forcing inputs/version
created_at
completed_at
status = current | superseded | resolved | failed | historical
superseded_by
```

Rules:

```text
ACTIVE/REOPENED + valid point -> current Drift may be operational
NEEDS_REVIEW -> only if origin evidence remains eligible by explicit policy
UNRESOLVED_STALE -> freeze/hide operational Drift according to stale-model policy
RESOLVED -> remove/freeze from Live immediately
ARCHIVED -> never operational Live
new accepted position -> old Drift superseded before new current Drift becomes public
region-only/unpositioned -> no fabricated trajectory
```

`public_drift_collection()` must select `incident.current_drift_id`; it must not rediscover arbitrary completed jobs.

**Exit:** exactly zero or one operational current Drift per incident; stale/historical jobs remain replayable but cannot appear current.

---

# 4. Source acquisition and coverage subsystem

A serious OSINT platform must know what it watches and where it is blind.

## P1.1 — Source Registry

Each source:

```text
source_id
name
source_family
source_type
operator/organisation
geographic coverage
route coverage
languages
content types
collection method
polling cadence
expected latency
historical coverage start
terms/licence/access constraints
privacy constraints
preservation capability
independence group
known limitations
active_from / active_to
```

Source reliability is contextual metadata, not one global truth score.

## P1.2 — Coverage Matrix

Track at least:

```text
Central Mediterranean
Eastern Mediterranean
Western Mediterranean
Aegean
Adriatic / Ionian when in scope
Atlantic / Canary route when in scope
```

Across dimensions:

```text
region / route
language
source family
active sources
healthy sources
last successful fetch
expected vs actual cadence
local-language coverage
single-family dependency
coverage change date
backfill status
```

Source families should include, when legally/technically justified:

```text
Alarm Phone / distress networks
SAR NGOs / rescue organisations
NGO statements/RSS
IOM / Missing Migrants / DTM
UNHCR / OCHA / ReliefWeb
MRCC / coastguard / government statements
local Mediterranean media
regional/international media
verified specialist journalists/monitors
source-specific public social feeds
AIS/vessel evidence as corroborating maritime evidence
```

Do not claim “all news”. The platform must expose its observable universe and gaps.

## P1.3 — Coverage-change integrity

A high-yield new source can create an artificial trend break.

Before using a new source for comparative trends:

```text
record inclusion rationale
measure unique-event yield
measure duplicate/correlation yield
assess historical availability
backfill when feasible
record coverage break when not feasible
version the coverage profile
```

Dashboards/exports must expose material collection-method changes.

**P1 exit:** operators can answer what SeaCommons is watching, what is down, which areas/languages have weak coverage and when coverage changed.

---

# 5. Connector architecture

Use a connector contract instead of source-specific logic leaking into domain code.

Connector classes:

```text
IMPORT      pull/poll external source and emit SourceObservation
STREAM      continuously receive source events
ENRICH      query external source for a known incident/entity/watch
PRESERVE    archive permitted source artifact/media
EXPORT      emit selected platform objects to external consumers
```

Each connector must implement:

```text
capabilities
source_id
checkpoint/cursor semantics
idempotency key
rate-limit policy
retry/backoff
failure classification
health signal
raw-to-observation mapping
terms/privacy notes
fixture/replay mode
```

Connector failure must not mutate existing incidents or silently mark sources as empty.

Test:

```text
first fetch
no-op repeat fetch
new item
edited item
pagination
out-of-order item
429
5xx
timeout
partial malformed payload
cursor recovery
source deletion where observable
```

Do not build one giant “news scraper”. Build bounded adapters with measurable coverage.

---

# 6. Preservation and evidentiary provenance

For public web/social evidence, preserve enough to verify what the platform observed at collection time where terms/law/privacy permit.

Persist/reference:

```text
canonical URL/platform id
publisher/account id
publication timestamp
retrieved_at
raw text or permitted snapshot
media references
content/media hashes
thread/parent relations
language
HTTP/source metadata useful for replay
parser version
preservation status
archive URI/reference when available
```

Preservation and public publication are separate policies.

For sensitive Humanitarian material:

- minimize retained personal identifiers;
- segregate restricted artifacts;
- make retention policy explicit;
- never leak internal artifact URLs/hashes if they reveal sensitive content;
- preserve provenance even when public content is generalized/withheld.

---

# 7. Correlation, entity resolution and evidence graph

## P2.1 — CorrelationDecision

Taxonomy:

```text
SAME_INCIDENT
RELATED_INCIDENT
NEW_INCIDENT
UNCERTAIN
```

Persist:

```text
observation_id
candidate_incident_id
decision
supporting_features[]
contradicting_features[]
source_independence_result
method/version
confidence
review state
```

Candidate generation order:

```text
1. exact thread/source IDs
2. known source-specific case IDs
3. temporal bounds
4. spatial overlap + uncertainty
5. place/route/departure compatibility
6. people-count range
7. vessel description/identity
8. NGO/authority references
9. lexical/entity overlap
10. optional embedding/reranker
```

Model similarity cannot be sole merge evidence.

## P2.2 — Circular reporting lineage

Represent derivation/quotation relationships where detectable:

```text
original report → article A → article B
```

Independent-source count must use evidence lineages, not URL count.

## P2.3 — Entity graph

Canonical entities may include:

```text
vessel
organisation
source account
port
place
maritime zone
infrastructure
incident
episode
observation
```

Relationships carry provenance and time bounds:

```text
reported_by
mentions
located_at
near
responding_to
involved_in
observed_as
same_as_candidate
corroborates
contradicts
supersedes
derived_from
```

Do not force the entire platform into a graph database prematurely. Start with typed relational objects/edges in PostgreSQL; evaluate specialized graph infrastructure only if measured queries justify it.

---

# 8. IncidentWatch — follow cases, not only feeds

Opening a Humanitarian incident creates a bounded `IncidentWatch`.

Watch profile:

```text
incident_id
source thread/item IDs
coordinates + uncertainty
named places
people-count range
vessel description
route/departure/destination
case type
NGO/authority names
known internal vessel identities
keywords/entities
language variants
created_at
priority
next_run_at
expires/degrades policy
```

The watch invokes eligible connectors/search adapters and emits new `SourceObservation`s. It never directly mutates the incident.

Cadence by state:

```text
ACTIVE / REOPENED    highest priority
NEEDS_REVIEW         high priority + analyst queue
UNRESOLVED_STALE     targeted searches, lower cadence, outcome unknown
RESOLVED 0–24h       high follow-up for confirmation/corrections
RESOLVED 1–7d        periodic follow-up
7–30d                 low-frequency enrichment
ARCHIVED              no dedicated polling by default; global ingestion may still revise/reopen
```

Follow-up targets include:

```text
rescue confirmation
interception/return
disembarkation
people-count correction
missing/deaths
rescuing vessel/authority
port/outcome
location correction
later NGO/authority statements
news investigation / follow-up
```

Budget watches by priority/source cost. Prevent duplicate queries and retry storms.

**Exit:** labelled replay shows later updates attach to existing cases and can resolve/reopen/correct them without creating duplicate operational incidents.

---

# 9. Review and case-management subsystem

Automation must route uncertainty instead of hiding it.

Review reasons:

```text
AMBIGUOUS_DUPLICATE
CONFLICTING_LOCATION
CONFLICTING_OUTCOME
RESOLUTION_LOW_CONFIDENCE
REOPEN_AFTER_RESOLUTION
PEOPLE_COUNT_DIVERGENCE
OCR_VS_IMAGE_COORDINATE_CONFLICT
STALE_ACTIVE_CASE
SOURCE_THREAD_BROKEN
CIRCULAR_REPORTING_RISK
PUBLICATION_PRIVACY_REVIEW
ENTITY_IDENTITY_CONFLICT
HYPOTHESIS_PUBLICATION_REVIEW
```

Persist `ReviewDecision`:

```text
review_id
object_type/object_id
reason
input evidence ids
decision
notes/code
reviewer id where applicable
created_at
method/version
```

Review queues need:

```text
priority
age
incident severity/operational state
reason
blocking/non-blocking status
```

A review action itself becomes replayable provenance.

---

# 10. Geospatial evidence foundation

This begins only after the first Humanitarian vertical is canonical.

## P3.1 — PostGIS foundation

Introduce:

```text
PostgreSQL + PostGIS
GeoAlchemy2
Shapely
PyProj
```

Canonical geometry roles:

```text
reported_geometry
  directly supplied by source/sensor

derived_geometry
  calculated/inferred from evidence

uncertainty_geometry
  plausible area/trajectory uncertainty

public_geometry
  publication/privacy projection
```

Original source geometry is immutable.

Migrate one vertical slice at a time; scalar lat/lon remain temporary projection compatibility only.

## P3.2 — Spatial candidate retrieval

Move bounded candidate retrieval to PostGIS:

```text
nearby observations/incidents
bbox/time
point-in-zone
track/area intersection
vessel proximity
infrastructure proximity
nearest-object
Drift/event intersection
correlation shortlist
```

The DB finds plausible candidates; domain logic determines semantic meaning.

Require query plans/benchmarks before indexes.

## P3.3 — Humanitarian geolocation V2

Evidence types:

```text
reported coordinate
OCR coordinate
map screenshot coordinate/map pin candidate
named place
relative location phrase
named region
operator-reviewed position
land humanitarian location
unpositioned
```

Do not invent precision. A vague region remains an area/uncertainty geometry.

Replay corpus must include Alarm Phone text coordinates, screenshots, contradictory claims, land/sea ambiguity, invalid OCR, coordinate updates and no-position negatives.

---

# 11. Maritime Intelligence vertical

Humanitarian and Maritime share evidence primitives but have different publication semantics.

Canonical flow:

```text
AIS / registries / sanctions lists / notices / news / infrastructure data
        ↓
SourceObservation + vessel/entity identity evidence
        ↓
normalized features
        ↓
VesselSubject
        ↓
bounded MaritimeEpisode
        ↓
EvidenceLinks + contradictions
        ↓
InvestigationHypothesis
        ↓
review / publication gate
```

Distinguish:

```text
FACT
  vessel appears on list X

OBSERVATION
  AIS transmission gap observed during interval

DERIVED FEATURE
  gap is isolated relative to coverage baseline

EPISODE
  bounded cluster of related features

HYPOTHESIS
  evidence supports candidate interpretation

ALLEGATION/PUBLIC CLAIM
  requires publication/review gate
```

Never convert sanctions-list membership into sanctions-evasion behaviour without independent behavioural evidence.

Maintain hypothesis states and audit transitions separately from raw facts.

---

# 12. AI evidence-enrichment layer

AI is a capability layer behind typed contracts.

Provider-neutral capabilities:

```text
structured text extraction
classification
multimodal/image extraction
embeddings
reranking
bounded correlation/reasoning
optional transcription
```

Provider adapters may include NVIDIA NIM, Groq, Gemini, OpenRouter or later providers, but domain services depend only on capability contracts.

Persist each invocation/result:

```text
provider
model/revision
capability
schema version
prompt/instruction version
input observation IDs
request timestamp
latency
status/error class
usage metadata
structured result
validation status
```

Promotion ladder:

```text
DISABLED
  ↓
SHADOW
  ↓
ASSISTIVE
  ↓
BOUNDED_AUTHORITATIVE
```

No capability skips the ladder.

## P4.1 — Shadow extraction

Run model extraction beside deterministic extraction and return deterministic result.

Measure divergence on labelled corpus.

## P4.2 — Multimodal Alarm Phone image evidence

Compare:

```text
OCR
caption/thread text
VLM structured extraction
map labels/pin plausibility
land/sea validity
```

Model coordinates are `derived_candidate`, never `reported_geometry`.

Metrics:

```text
coordinate detection precision/recall
numeric error
false-precision rate
correct null/no-position rate
OCR/VLM agreement
privacy compliance
```

## P4.3 — Semantic correlation/reranking

Use only after deterministic spatiotemporal/identity shortlist.

Measure:

```text
SAME_INCIDENT precision/recall/F1
NEW_INCIDENT precision/recall/F1
false-merge rate
UNCERTAIN calibration
```

False-merge threshold is an explicit release gate.

All AI-off operation must remain safe and functional.

---

# 13. External datasets and GIS tooling

## P5.1 — Versioned geodata ingestion

Use GDAL/OGR only when justified for reproducible import of:

```text
SAR regions
EEZ / territorial waters
coastlines
ports
subsea cables/pipelines
offshore infrastructure
protected areas/AOIs
```

Persist:

```text
source/version
licence/terms
retrieved_at
checksum
original/canonical CRS
transform/tool version
feature count
validation result
```

Unknown CRS is rejection/quarantine, never guessed EPSG:4326.

## P5.2 — QGIS analyst QA

QGIS is read-only QA/analysis tooling, not runtime authority.

Expose separable layers for:

```text
reported geometry
derived geometry
uncertainty geometry
public geometry
Humanitarian incidents
AIS tracks/episodes
Drift trajectories/cones
reference zones/infrastructure
AI-derived candidates with provenance
```

Sensitive exact Humanitarian locations require role-restricted access.

## P5.3 — H3 only if measured

Use H3 only for justified aggregation/privacy/statistics/cache use cases. Geometry remains authoritative.

## P5.4 — Vector tiles only if measured

Move from bulk GeoJSON to vector tiles only when profiling shows a material map-delivery problem. Public/private attributes must be separated before tile generation.

---

# 14. Platform observability and data-quality console

Operational metrics:

```text
connector success/error/rate-limit
source last successful fetch
source staleness
collection latency
observation ingestion rate
parse/extraction failures
unpositioned rate by method
correlation decisions by class
false-merge labelled rate
single-source incident rate
independent corroboration rate
unresolved-stale rate
report -> ingestion latency
report -> Live latency
update -> incident attachment latency
resolution evidence -> resolved latency
location correction rate
outcome-known rate
historical revision rate
coverage changes over time
current/stale Drift count
Drift-after-resolution count
review queue size/age
edge/VM projection divergence
AI invocation/error/latency/divergence where enabled
```

Expose an internal data-health endpoint/dashboard without raw sensitive text in metric labels.

A source returning zero items is not equivalent to a healthy source with zero events. Health and content are separate signals.

---

# 15. Import/export and interoperability

The platform should support stable machine-readable exchange without coupling internals to one external standard.

First-class exports:

```text
GeoJSON
JSON/JSONL canonical observation/incident export
CSV for bounded analysis
GeoPackage when geospatial analyst use justifies it
```

Evaluate mappings to relevant standards/formats only when interoperability requires them. MISP/STIX/OpenCTI concepts are architectural references, not mandatory schemas for Humanitarian maritime incidents.

Every export:

- applies publication/privacy policy;
- includes stable IDs and revision/provenance references;
- never exports restricted raw Humanitarian artifacts by default;
- declares schema version.

---

# 16. Scale and infrastructure

Start simple and measured.

## AIS/time-series

Use native PostgreSQL/PostGIS indexes and partitioning first. Benchmark:

```text
track by MMSI/time
bbox/time
nearby vessels
zone crossing
rendezvous candidates
infrastructure proximity
multi-MMSI recent history
```

Evaluate TimescaleDB only after measured bottlenecks.

## Deployment

Make VM deployment reproducible with Docker/Ansible or equivalent minimal automation only when production closure is stable.

Prove:

```text
clean host -> operational stack
idempotent redeploy
migration
backup
restore
worker restart
DB reconnect
source connector degradation
all-AI-disabled operation
```

Do not introduce Kubernetes, GeoServer, standalone vector DB, graph DB or self-hosted GPU cluster without an ADR and measured requirement.

---

# 17. Milestone / packet dependency graph

```text
fixes.md CLOSED
      ↓
P0.1 production Humanitarian truth-table audit
      ↓
P0.2 SourceObservation/provenance
      ↓
P0.3 HumanitarianIncident
      ↓
P0.4 claims/assessments
      ↓
P0.5 lifecycle
      ↓
P0.6 timer contract
      ↓
P0.7 current Drift ownership
      ↓
P1.1 Source Registry
      ↓
P1.2 Coverage Matrix
      ↓
P1.3 coverage-change integrity
      ↓
Connector contracts + bounded source adapters
      ↓
P2.1 correlation decisions
      ↓
P2.2 circular-reporting lineage
      ↓
P2.3 entity/relationship graph
      ↓
IncidentWatch + review queue
      ↓
P3.1 PostGIS foundation
      ↓
P3.2 spatial candidate retrieval
      ↓
P3.3 Humanitarian geolocation V2
      ↓
Maritime Intelligence vertical hardening
      ↓
P4.1 AI shadow extraction
      ↓
P4.2 multimodal evidence
      ↓
P4.3 semantic reranking
      ↓
external geodata / QGIS / optional H3 / optional tiles
      ↓
scale + reproducible infrastructure
      ↓
final legacy deletion + production qualification
```

Parallel work is allowed only when packets do not modify the same canonical schema/authority and have independent tests.

---

# 18. Packet acceptance template

No packet is DONE without all applicable evidence:

```text
[ ] failing test existed before implementation
[ ] production/redacted regression fixture added when relevant
[ ] canonical schema/object documented
[ ] migration up/down/re-up green
[ ] targeted tests green
[ ] relevant backend full suite green
[ ] web lint/typecheck/tests/build green when contract/UI changed
[ ] deterministic replay green
[ ] privacy/publication tests green
[ ] edge/VM parity checked when public projection changed
[ ] source outage/invalid input behavior tested when connector changed
[ ] observability added
[ ] duplicate authoritative path removed or deletion packet named
[ ] exact main/head SHA recorded
[ ] known limitations explicit
```

If one required box cannot be checked, the PR must state why and the packet remains open.

---

# 19. Final legacy deletion

After parity is proven, remove:

```text
post-as-incident assumptions
stored ingestion-era lifecycle shortcuts
arbitrary completed-Drift lookup
legacy area_geojson authority
spatial dual-write authority
custom geometry helpers superseded by canonical spatial layer
duplicate correlation logic
provider-specific AI bypasses
obsolete prompt/schema active routing
per-source domain logic that belongs in connectors
unbounded fallback source scans
duplicate publication policy paths
```

Repository-wide audit:

```text
legacy
deprecated
compat
fallback
old_
remove after
TODO migration
dual write
```

Every remaining occurrence is justified or removed.

---

# 20. Production qualification

Qualification runs on the exact release-candidate SHA.

## Humanitarian replay

Cover at least:

```text
new Alarm Phone distress
thread update remains same incident
location update supersedes old position/Drift
ambiguous update -> needs_review
positive rescue evidence -> resolved
silence -> unresolved_stale, not resolved
later contradiction revises assessment
resolved case receives later correction
reopened case
circular media copies do not multiply corroboration
source outage does not imply no incidents
out-of-order update preserves chronology
```

## Maritime replay

Cover:

```text
common AIS outage vs isolated gap
separate episodes days apart
continuing episode stays one
list membership remains fact
single signal cannot become public allegation
multi-evidence hypothesis retains EvidenceLinks
review/publication transition is exercised
```

## Privacy

Prove:

```text
no public MMSI/IMO/tracker dossier in Humanitarian projection
no restricted raw Humanitarian text/media leak
no unreviewed precise derived Humanitarian location leak
no Maritime hypothesis published outside policy gate
```

## Failure/degradation

Prove:

```text
source 429/5xx/timeout
parser/schema failure
DB reconnect
worker restart
AI provider timeout/429/5xx/malformed output
all AI disabled
coverage source down
edge/VM mismatch detection
```

## Metrics

Report before/after baseline for:

```text
Live correctness anomaly count
stale Drift count
resolution latency
update attachment latency
duplicate rate
false-merge rate
positioned-event rate by method
source coverage/health
query latency
map payload/load where changed
AI divergence/latency only where enabled
```

---

# 21. Definition of DONE

SeaCommons qualifies as the target maritime OSINT platform only when:

1. every public Humanitarian item traces to immutable source observations and a stable canonical incident;
2. updates, corrections, resolutions and reopens modify incident history rather than creating feed duplicates;
3. claims and assessments are separate, contradiction-preserving and provenance-backed;
4. lifecycle is evidence-based and silence never becomes resolution;
5. Live timers use typed chronology;
6. exactly zero or one current operational Drift exists per eligible incident;
7. the Source Registry and Coverage Matrix make observable gaps/outages/source-mix changes explicit;
8. connectors are bounded, idempotent, replayable and source failures are observable;
9. IncidentWatch continues targeted collection after an initial report and through bounded post-resolution enrichment;
10. correlation decisions and source-independence/circular-reporting logic are persisted and testable;
11. entity/relationship evidence is provenance-bearing;
12. PostGIS is the canonical spatial query layer once spatial migration completes;
13. reported/derived/uncertainty/public geometry remain distinct;
14. Humanitarian privacy and Maritime allegation gates are enforced at publication boundaries;
15. Maritime facts, episodes, hypotheses and public allegations remain distinct;
16. AI is provider-neutral, evaluable, disable-able and cannot bypass evidence/publication policy;
17. source/geodata/model provenance is sufficient for deterministic replay;
18. observability exposes collection quality, incident quality, review debt and projection drift;
19. legacy duplicate authorities introduced during migration are deleted;
20. the exact release SHA passes Humanitarian + Maritime replay, privacy, failure/degradation and production verification gates.

The end state is not a map with more feeds. It is a maritime OSINT platform whose collection scope, evidence, uncertainty, correlation, chronology, analysis and publication decisions are explicit, inspectable and reproducible.
---

# 22. 2026-09-05 Live / Play / Satellite cutover

Public surfaces now have separate temporal responsibilities:

```text
live.seacommons.org  = operational awareness, rolling <=24h
play.seacommons.org  = historical temporal reconstruction, >24h or terminal
```

`archived` is no longer a public incident outcome. Canonical incident status is
`active`, `needs_review`, `resolved`, or `outcome_unknown`; legacy archived rows
map to `outcome_unknown`. Silence never becomes resolution. A 15-minute
reconciler persists stale active incidents as `outcome_unknown` after 24 hours.

Live publishes only operational incidents inside the 24-hour window. Resolved
incidents leave Live immediately. Needs-review incidents retain their real
status but also retire from Live at the 24-hour surface boundary. Historical
records remain available to Play rather than an archive bucket in the Live UI.

Drift authority remains incident-owned:

```text
IntelEvent -> HumanitarianIncident -> current_drift_id -> DriftResult
```

No public code rediscovers an arbitrary completed job as the current Drift.
Legacy deploys must first create missing canonical Humanitarian incidents and
only then repair `current_drift_id`. Resolved/outcome-unknown incidents cannot
regain an operational Drift pointer.

Play exposes an incident-centric API:

```text
GET /api/v1/play/incidents
GET /api/v1/play/incidents/{incident_id}/timeline
```

The timeline combines privacy-safe source reports/updates, lifecycle
transitions, historical Drift products and persisted SatelliteObservations.
The public Play frontend is a dedicated MapLibre build entry; Cesium/Unreal are
not part of the `play.html` dependency graph.

Satellite evidence is provider-agnostic and metadata-first. The free resolver
currently supports Copernicus Data Space STAC (Sentinel-1/2/3) and dated NASA
GIBS VIIRS context. Each significant geolocated event can collect
`reverse`, `nearest`, and `forward` observations. A bounded 30-minute job
checks at most six recent incident-level events per run and degrades safely
when an external provider is unavailable. Satellite observations are evidence,
never automatic vessel identity proof.

Production rollout order is mandatory:

```text
1. database backup
2. alembic upgrade head
3. humanitarian incident backfill -- dry-run, then apply
4. current drift pointer backfill -- dry-run, then apply
5. coordinated API / edge publisher / worker restart
6. local API + Live + Play smoke tests
7. frontend deploy
8. verify live/play production asset hashes against merged build
```

Do not run the second backfill before the first. Keep the pre-deploy database
backup until Live and Play have both been visually and operationally verified.
