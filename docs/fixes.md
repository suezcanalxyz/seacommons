# SeaCommons — Final Maritime OSINT Stabilization & Execution Plan

> **For Claude/Codex agentic workers:** this file is the single source of truth for the stabilization program. Execute milestones in order, one reviewable PR at a time. Use TDD. Do not skip a gate because a later task is easier. Do not mark work DONE because unit tests are green: every milestone has an integration/replay exit gate.

**Goal:** turn SeaCommons into a production-grade, evidence-first maritime OSINT platform with two first-class operational sides — **Humanitarian** and **Maritime** — sharing one canonical data/evidence pipeline while preserving different privacy, publication and analytical rules.

**Production target:** current ARM VM (~12 GB RAM), FastAPI/Python backend, PostgreSQL production storage, React/Vite/MapLibre web app, bounded background workers for OCR/Drift/Sentinel jobs.

**Current verified baseline:** `main` at `2c3cdc28af279f8c3926a2f3adc4853203a02f2e`, 2026-09-03. M0 is closed — PRs #66 (P0.1/A-01/A-02), #67 (M0.2 EventAssessment→UI), #68 (M0.3 neutral rendezvous), #69 (M0.4 vessel-class fallbacks), #70 (M0.5 darkship cue) all merged. Backend `589 passed`, ruff clean; web lint/typecheck/build clean. Next: M1 (`docs/fixes.md` section 6, SourceObservation durable schema + adapter audit) — a materially larger architectural change (new DB tables/migrations, source-adapter rewrites) than M0's semantic fixes; start there only with explicit sign-off given the risk-profile shift.

---

# 0. Product definition

SeaCommons is not a generic vessel tracker and not a risk-scoring dashboard. It is a **maritime evidence engine**.

Every surfaced item must make five things explicit:

1. what was actually observed;
2. where that observation came from;
3. what was deterministically derived from it;
4. what interpretation/hypothesis is being investigated and why;
5. what can safely be published, to whom, and with what uncertainty.

The two product sides are:

```text
HUMANITARIAN
  distress
  missing
  rescue_update
  interception
  pushback
  resolution
  land_humanitarian
  advocacy/review

MARITIME
  safety
  intelligence
  environmental
```

Humanitarian is **people-centred and privacy-constrained**. Maritime Intelligence is **vessel/episode-centred and evidence-gated**. Maritime Safety is operational context and must never become Intelligence by fallback.

The canonical data flow is:

```text
SOURCE INPUT
  -> RAW OBSERVATION
  -> NORMALIZED OBSERVATION
  -> DETERMINISTIC FEATURE / EXTRACTION
  -> CORRELATION
  -> INCIDENT or EPISODE
  -> ASSESSMENT / HYPOTHESIS
  -> REVIEW + PUBLICATION DECISION
  -> PUBLIC / ANALYST PROJECTION
  -> REPLAY + OBSERVABILITY
```

No layer may silently collapse two adjacent stages into one.

---

# 1. Non-negotiable invariants

These are release blockers.

1. SeaCommons classifies and explains; it does not present a synthetic risk score as truth.
2. Unknown classifications fail closed.
3. `service` and `lane` are positive decisions, never inferred by complement.
4. `not_under_command`, `aground`, and `restricted_manoeuvrability` are `service=maritime`, `lane=safety`.
5. Safety observations are never cargo-Drift eligible.
6. Humanitarian Drift is humanitarian-only.
7. A rendezvous is not a sanctions event.
8. An AIS gap is not proof that AIS was deliberately disabled.
9. A SAR detection without a valid time/trajectory association is a candidate, not a dark-vessel confirmation.
10. Vessel class is context, never an allegation or investigation category.
11. Public Humanitarian views never expose MMSI, IMO, tracker links or professional-vessel dossiers.
12. Public Maritime allegations require evidence + review, except direct official-list facts and neutral Safety observations.
13. Raw observations, derived features, episodes, hypotheses and public projections remain distinguishable.
14. All derived outputs carry algorithm/version and input IDs.
15. External-source licence/terms are part of provenance.
16. No scraping that violates source terms.
17. No migrant interception support, border-enforcement targeting, military targeting or commercial surveillance aggregation.
18. Every production pipeline must be replayable from persisted source observations or source fixtures.
19. A green unit suite is insufficient: every milestone needs integration/replay validation.
20. No task is DONE until its exit gate is proven on the exact commit that will be merged.

---

# 2. Canonical taxonomy

## 2.1 Service / lane

```text
service=humanitarian
  lane=distress
  lane=missing
  lane=rescue_update
  lane=interception
  lane=pushback
  lane=resolution
  lane=land_humanitarian
  lane=advocacy
  lane=review

service=maritime
  lane=safety
  lane=intelligence
  lane=environmental
```

`maritime_domain` is compatibility metadata during migration only. It must not remain the authoritative router.

## 2.2 Observation types

Humanitarian examples:

```text
source_post
source_image
reported_coordinate
ocr_coordinate
reported_people_count
reported_missing_count
reported_dead_count
reported_rescued_count
reported_interception
reported_pushback
reported_resolution
```

Maritime examples:

```text
ais_position
ais_nav_status
ais_identity
ais_gap
position_jump
course_change
speed_change
loitering
rendezvous
port_call
sanctions_list_match
navwarning
sar_detection
infrastructure_proximity
pollution_detection
```

Observation type describes what was received or measured. It is never the same thing as an investigative hypothesis.

## 2.3 Maritime Intelligence hypothesis types

```text
dark_transit
concealed_port_call
covert_rendezvous
identity_deception
position_spoofing
route_deception
sanctions_evasion_pattern
infrastructure_pattern
```

## 2.4 Evidence ladder

```text
observed       direct source/sensor fact
derived        reproducible calculation from observations
corroborated   independent observations/modalities agree
assessed       analyst judgement recorded
confirmed      authoritative/documentary confirmation
```

A detector threshold cannot directly create `confirmed`. A single AIS field cannot create an allegation. Every assessment carries supporting evidence, contradictory evidence and caveats.

---

# 3. Canonical durable data model

`IntelEventDB` remains a compatibility/public projection envelope during migration. It must stop being the only semantic datastore.

Create durable typed entities:

```text
SourceObservation
  observation_id
  service
  lane
  observation_type
  source_name
  source_policy
  source_url / source_id
  observed_at
  received_at
  raw_payload_hash
  raw_payload_ref
  geometry
  location_precision
  uncertainty_m
  subject_refs[]
  provenance
  schema_version

VesselSubject
  subject_id
  current_name
  current_mmsi
  current_imo
  identity_confidence

VesselIdentityAlias
  alias_id
  subject_id
  identity_type
  value
  valid_from
  valid_to
  source_observation_id

BehaviourFeature
  feature_id
  feature_type
  subject_id / subject_ids[]
  start_at
  end_at
  geometry
  values
  algorithm
  algorithm_version
  parameters
  input_observation_ids[]
  evidence_stage=derived

HumanitarianIncident
  incident_id
  case_type
  lifecycle
  location_status
  people_counts
  needs
  source_observation_ids[]
  geo_evidence_ids[]
  publication_status
  confidence
  confidence_basis[]

MaritimeEpisode
  episode_id
  episode_type
  subject_ids[]
  start_at
  end_at
  geometry
  observation_ids[]
  feature_ids[]
  status

InvestigationHypothesis
  hypothesis_id
  episode_id
  hypothesis_type
  state
  evidence_stage
  reason_codes[]
  counter_indicators[]
  confidence
  assessment
  publication_status
  reviewed_by
  reviewed_at

EvidenceLink
  evidence_link_id
  from_type / from_id
  to_type / to_id
  relationship
  weight_semantics
  created_at

CoverageBaseline
  baseline_id
  source
  aoi_id
  time_bucket
  expected_message_rate
  observed_message_rate
  receiver_health
  jamming_context
  congestion_context
  version
```

Every migration must be SQLite-test compatible and PostgreSQL-safe. Every new table gets indexes based on actual query paths, not speculative indexing.

---

# 4. Claude execution loop — mandatory

Claude must execute this plan as a continuous senior engineering loop.

For every milestone:

```text
1. sync main
2. read docs/fixes.md
3. identify first unchecked milestone whose dependencies are DONE
4. inspect all listed code paths before editing
5. write/adjust failing tests first
6. implement the smallest coherent vertical slice
7. run targeted tests
8. run full backend suite + ruff
9. if web touched: lint + typecheck + node tests + vite build
10. if DB touched: migration upgrade/downgrade test + SQLite compatibility test
11. if pipeline touched: deterministic replay test
12. if public projection touched: VM/edge/public privacy contract tests
13. self-review diff against this file's invariants
14. open one PR with exact test evidence and known limitations
15. STOP at PR boundary unless CI is green and PR is mergeable
16. merge only after green gate
17. update main and start the next unchecked milestone
```

Claude must never:

- stack unrelated semantic changes in one PR;
- change detector thresholds without a baseline/replay metric;
- make a public claim stronger than the evidence stage;
- weaken privacy to simplify joins;
- silently preserve legacy behaviour because an old test expects it;
- modify a failing test to accept incorrect semantics without documenting the old behaviour and the new invariant;
- mark a milestone DONE from local tests if CI/replay disagrees.

Recommended PR size: one semantic change, usually 1–8 production files plus focused tests.

---

# 5. M0 — close current semantic defects

**Goal:** make the already-built taxonomy and assessment primitives authoritative before building more intelligence.

## M0.1 — merge PR #66: authoritative Safety routing

Current PR: `#66`, head `ec71079f525ed57cb52a26b20e12437b1bfb1223`.

It must remain responsible for:

- explicit `metadata.maritime_domain` winning in `IntelEvent.maritime_domain()`;
- genuinely legacy records only using fallback correction;
- no legacy Safety→cargo Drift resurrection in projection;
- `mode=safety` as a separate Live bucket;
- Safety excluded from humanitarian-only edge feed;
- VM/edge parity.

Exit gate:

```text
pytest full backend: green (>=584 baseline)
ruff: green
Vercel/web checks: green
NUC -> maritime/safety end-to-end
NUC -> drift_eligible=false end-to-end
Safety never appears in humanitarian or security bucket
```

After merge, update the baseline at the top of this file in the same or next docs-only commit.

## M0.2 — EventAssessment -> public contract -> UI

**Files:**

- `apps/api/core/intel/assessment.py`
- `apps/api/core/live/projection.py`
- `apps/api/core/domain/live_contracts.py`
- `apps/web/src/components/ConePanel.jsx`
- assessment/projection/frontend tests

Project these fields as a nested object named `assessment`:

```json
{
  "observation": "...",
  "interpretation": "...",
  "evidence_level": "observed|derived|corroborated|assessed|confirmed",
  "confidence": 0.0,
  "confidence_basis": [],
  "supporting_evidence": [],
  "contradicting_evidence": [],
  "caveats": [],
  "recommended_action": "...",
  "rule_ids": [],
  "classification_version": "..."
}
```

Required behaviour:

- `ConePanel` must stop using `descriptionOf(props.type)` as event-specific Interpretation;
- `descriptionOf()` remains category help only;
- events with no assessor omit the assessment block rather than inventing generic prose;
- two NUC events with different evidence render different observation/interpretation text.

Exit gate: backend projection test + frontend render test + full suites green.

## M0.3 — neutral rendezvous semantics

**Files:**

- `apps/api/core/mda/watch.py`
- `apps/api/core/intel/fusion.py`
- `apps/api/core/intel/service_taxonomy.py`
- relevant tests

Raw rendezvous output must be:

```text
service=maritime
lane=intelligence
observation_type=rendezvous
publication_status=internal
evidence_stage=observed|derived
hypothesis_type absent
```

Never write `maritime_domain=sanctions` merely because two vessels were in sustained proximity.

A sanctions-evasion hypothesis may only emerge later from the evidence engine when independent factors exist, such as official-list match + encounter + gap/identity/port/draught evidence.

Exit gate: one neutral STS fixture remains internal and cannot create a sanctions allegation by itself.

## M0.4 — remove vessel-class-as-analysis

**Files:**

- `apps/web/src/features/intel/categories.js`
- `apps/web/src/components/ConePanel.jsx`
- event presentation helpers/tests

Required:

- remove `Other vessel` as an analytical outcome;
- vessel type may appear only in a clearly labelled context row;
- unknown type means omit/context unknown, not category inference;
- `Other signal` is not a public semantic category; unknown public classifications fail closed or appear only in an analyst review lane.

Exit gate: UI tests prove vessel type never changes evidence category/hypothesis.

## M0.5 — darkship cue semantic + endpoint correction

**Files:**

- `apps/api/core/mda/darkship_cue.py`
- tests

Required:

- use current Copernicus Data Space STAC endpoint `https://stac.dataspace.copernicus.eu/v1/`;
- unmatched SAR detection wording = candidate only;
- association requires acquisition time, propagated AIS/reachable area, uncertainty and distance;
- recommendation must expose why association exists and what remains unknown.

Exit gate: test proves an unmatched detection cannot produce text equivalent to “likely/confirmed dark vessel” without a stronger association stage.

---

# 6. M1 — canonical observation ingestion layer

**Goal:** every source becomes a lossless, immutable, replayable observation before classification.

## M1.1 — SourceObservation schema + persistence

Create focused model/service modules; do not overload `models.py` with business logic.

Required write path:

```text
source adapter -> normalize envelope -> SourceObservationDB -> downstream subscribers
```

`SourceObservation` must preserve:

- original source identifier;
- source timestamp and receive timestamp;
- raw payload hash;
- raw payload reference or safe persisted payload;
- source policy/licence class;
- geometry and uncertainty separately;
- subject references without making identity conclusions;
- ingestion schema version.

Every connector must be idempotent by a source-stable delivery key.

Exit gate: replaying the same raw fixture twice produces one observation and identical normalized output.

## M1.2 — adapter audit

Audit and route the existing inbound sources through the canonical envelope:

- AISStream/live AIS;
- Alarm Phone / tracked social feeds;
- NGO/SAR updates;
- IOM/humanitarian aggregate source where applicable;
- GDACS/navigation context;
- official sanctions sources;
- operator/manual reports;
- image/media attachments.

Do not delete old write paths until parity tests prove the new observation is equivalent or intentionally different.

Exit gate: source-by-source fixture matrix with ingest idempotency and provenance assertions.

---

# 7. M2 — Humanitarian Recognition V2

**Goal:** replace binary/flat humanitarian classification with structured incident assessment while preserving the stable distress prefilter.

Keep `is_distress()` as compatibility/ingestion prefilter where needed. Do not turn it into the full semantic classifier.

Create `core/intel/humanitarian_recognition.py` with a typed `HumanitarianAssessment`.

Required output:

```text
case_type
lifecycle
is_operational
publication_recommendation
confidence
confidence_basis[]
rule_ids[]
caveats[]

people:
  aboard
  rescued
  missing
  dead
  injured
  intercepted
  returned

vessel:
  type_reported
  condition
  engine_status

needs[]
actors[]
location_claims[]
temporal_claims[]
resolution_evidence[]
```

Rules:

- multiple quantities in one post remain separate;
- “50 aboard, 20 rescued, 3 missing” must not become one `persons=50` semantic field;
- retrospective/memorial content remains non-operational;
- source identity such as “SOS Mediterranee” never creates distress by name alone;
- lifecycle must distinguish active, needs_review, resolved, archived;
- resolution updates attach to existing incidents rather than fork new incidents when evidence supports relinking.

## M2.1 — real/sanitized corpus

Expand `tests/fixtures/alert_recognition/humanitarian.jsonl` with sanitized historical examples where repository/data access allows.

Every fixture carries:

```text
id
provenance_kind = synthetic|sanitized_real
input
expected_case_type
expected_lifecycle
expected_counts
expected_publication
notes
```

Never label synthetic fixtures as real.

Exit gate: scorer reports per-class precision/recall/F1 plus publication/lifecycle/count accuracy, and keeps hard negatives locked.

---

# 8. M3 — Humanitarian geo evidence and Drift pipeline

**Goal:** make location provenance explicit and keep Drift physically/semantically safe.

Create/standardize `LocationEvidence`:

```text
location_evidence_id
source_observation_id
method = text_reported|ocr|pin_fit|landmark_fit|region_fallback|operator
lat/lon or area geometry
uncertainty_m
review_status
engine_results[]
consensus
land_sea_class
algorithm_version
```

Canonical priority:

```text
human_verified / reported_exact
> multi-engine OCR consensus
> single-engine OCR with bounded uncertainty
> landmark/pin derived area
> region-only area
> unpositioned
```

Rules:

- a real point supersedes stale region-only geometry;
- region-only cannot fabricate a point;
- land events remain visible but cannot originate maritime Drift;
- disputed OCR cannot originate automatic Drift;
- machine OCR at sea may originate Humanitarian Drift only through the explicit current eligibility gate;
- Drift result always records origin evidence ID and model version;
- browser never creates automatic persisted Drift.

Exit gate: end-to-end fixtures for point-at-sea, point-on-land, region-only, OCR-disputed and resolved incident.

---

# 9. M4 — deterministic AIS behaviour replay and coverage baselines

**Goal:** stop tuning maritime detectors by intuition.

## M4.1 — pure replay adapter

Expose deterministic detector entry points that accept an ordered track fixture and fixed context instead of wall-clock/network state.

Wire `ais_behaviour.jsonl` and `ais_integrity.jsonl` into the scorer.

Metrics required:

```text
precision / recall / F1 per class
FP ids
FN ids
publication decision accuracy
reason-code accuracy
```

No threshold changes before the baseline exists.

## M4.2 — coverage model

Create `CoverageBaseline` calculation from the platform's own reception history.

At minimum capture:

- source health;
- expected reporting cadence;
- local receiver/message density;
- distance to coast/reception area;
- congestion;
- known GNSS/AIS outage/jamming context;
- preceding track density;
- comparison with nearby vessels in the same time/AOI bucket.

## M4.3 — replace vessel-class exclusions

Remove hard suppression of pleasure/passenger/fishing/tug from gap/spoofing logic.

Vessel class becomes a contextual feature only.

Gap feature must emit reason components such as:

```text
gap_duration
expected_messages
coverage_ratio
neighbour_message_ratio
pre_gap_course/speed
post_gap_reappearance
coast_distance
jamming_context
```

Exit gate: synthetic/common port outage produces no intentional-dark hypothesis; genuine isolated gap fixture remains detectable independent of vessel class.

---

# 10. M5 — stable vessel subjects and bounded episodes

**Goal:** stop equating one MMSI with one lifelong episode.

## M5.1 — VesselSubject identity layer

Resolve observations onto a stable subject with dated aliases. Identity conflicts remain explicit evidence, not silent overwrites.

Official sanctions match is a fact linked to a subject/identity record, not an automatic behaviour hypothesis.

## M5.2 — bounded episode builder

Replace `coalesce_security_vessel_episodes()` semantics with an episode builder.

Episode boundary rules must consider:

- max time gap;
- spatial continuity;
- behaviour family;
- active hypothesis continuity;
- explicit resolution/reappearance;
- subject identity continuity.

A vessel can have many episodes. An episode can involve two or more subjects for encounters.

Required episode families initially:

```text
gap_episode
rendezvous_episode
identity_integrity_episode
spoofing_episode
port_call_episode
infrastructure_proximity_episode
safety_episode
```

Exit gate: two unrelated anomalies on the same MMSI days apart become two episodes; repeated updates of one continuing event remain one episode.

---

# 11. M6 — evidence graph and InvestigationHypothesis engine

**Goal:** make Maritime Intelligence a real investigative workflow instead of a detector feed.

Create hypothesis lifecycle:

```text
candidate -> collecting -> review_ready -> assessed -> published
          -> rejected
          -> expired
```

A hypothesis stores reason codes and counter-indicators, not a black-box risk number.

Initial evidence gates:

## dark_transit

Requires isolated gap feature + sufficient coverage confidence. Satellite/SAR evidence may strengthen but is not required for candidate state.

## covert_rendezvous

Requires sustained rendezvous episode plus independent irregularity before `review_ready`, e.g. gap, identity conflict, concealed movement, unusual operational context.

## identity_deception

Requires contradictory identity observations across time/source. A duplicate MMSI alone is a candidate integrity problem until contextualized.

## position_spoofing

Requires impossible/implausible movement or spatial inconsistency with reproducible inputs and counter-evidence checks.

## sanctions_evasion_pattern

Requires an official-list/entity link plus behavioural evidence. A sanctions list match alone publishes only the official-list fact, never “evasion”.

## infrastructure_pattern

Requires more than proximity. Use dwell/route repetition + independent anomaly/corroboration before review-ready state.

Publication gate:

```python
state in {"assessed", "published"}
evidence_stage in {"corroborated", "assessed", "confirmed"}
reason_codes not empty
evidence_links not empty
no unresolved blocking identity conflict
explicit review for allegation-shaped wording
```

Every lifecycle transition enters audit history with actor, timestamp, old/new state and evidence snapshot hash.

Exit gate: no single raw AIS observation can create a published Intelligence allegation.

---

# 12. M7 — cross-sensor and satellite corroboration

**Goal:** use independent sensors to strengthen evidence without overstating attribution.

## M7.1 — Sentinel scene discovery

Current Copernicus STAC only. Cache scene metadata. Query by episode AOI and time window.

## M7.2 — SAR candidate association

Association must use acquisition time. Propagate last reliable AIS state to image time with uncertainty.

Store:

```text
scene_id
acquired_at
candidate_detection_id
distance_to_predicted_area
association_method
association_confidence
counter_candidates
algorithm_version
```

Never emit “dark vessel confirmed” from one unmatched target.

## M7.3 — optional heavy inference worker

Any CFAR/ML SAR processing must run outside the API process, with bounded queue concurrency, timeouts and memory limits appropriate to the ARM VM. If production load is too high, keep scene discovery + external detections and disable heavy inference without breaking the platform.

Exit gate: API remains responsive while satellite worker is unavailable or disabled.

---

# 13. M8 — durable migration, backfill and legacy cleanup

**Goal:** stabilize historical data so new code does not depend forever on read-time corrections.

Implement reversible migrations in stages:

1. create new typed tables;
2. dual-write new observations/features/episodes/hypotheses;
3. replay/backfill recent historical records;
4. compare legacy projection vs new projection;
5. switch reads to new model;
6. keep compatibility envelope for one release;
7. remove semantic fallback logic only after migration metrics are clean.

Specific legacy cleanup:

- backfill explicit service/lane for old NUC/aground/restricted events;
- remove need for `maritime_domain()` semantic correction after historical records are normalized;
- classify old rendezvous records as neutral observation unless evidence supports a hypothesis;
- separate identity-integrity history from sanctions facts;
- remove stale `drift_eligible` flags from Safety history;
- clean stuck/invalid Drift rows through an auditable maintenance command;
- retain immutable original values/provenance so backfill never destroys source history.

Backfill must be restartable and idempotent, with dry-run counts before writes.

Exit gate: restart/replay on a populated DB does not duplicate incidents, episodes, hypotheses or Drift jobs.

---

# 14. M9 — canonical publication and API contracts

**Goal:** one publication decision, multiple safe projections.

Create one policy layer that consumes typed incident/episode/hypothesis state and produces:

```text
analyst_private
analyst_shareable
public_humanitarian
public_safety
public_maritime_assessed
edge_humanitarian
```

Public Humanitarian:

- no MMSI/IMO/tracker dossiers;
- Alarm Phone semantic red category retained;
- location precision/uncertainty explicit;
- lifecycle explicit;
- raw private caller text excluded;
- Drift only from canonical persisted backend result.

Public Maritime:

- neutral Safety can publish without allegation;
- official sanctions facts cite the authoritative list;
- Intelligence hypotheses only after publication gate;
- observation vs interpretation visibly separated;
- evidence stage and caveats visible.

Edge parity:

The edge must consume the same projection/policy semantics, not a copied rule set. Add golden contract fixtures comparing VM and edge output for Humanitarian/Safety/Intelligence exclusion cases.

Exit gate: byte/semantic parity tests for shared safe fields and explicit expected differences only.

---

# 15. M10 — operator and public UI as an evidence interface

**Goal:** users see evidence structure, not detector noise.

Operator Maritime panel must show:

```text
Observation
Derived features
Episode timeline
Hypothesis
Evidence stage
Supporting evidence
Counter-indicators
Caveats
Identity history
Source/provenance
Review actions
```

Public Maritime panel shows only publication-approved subset.

Humanitarian panel shows:

```text
incident type
lifecycle
reported people counts by semantic category
location evidence/uncertainty
source updates
resolution state
Drift model provenance when applicable
```

Map design:

- semantic category controls colour;
- lifecycle controls opacity/dash/state treatment;
- confidence does not redefine category colour;
- Safety, Humanitarian and assessed Maritime Intelligence have distinct product filters;
- unknown/unclassified does not silently appear as “Other”.

Exit gate: UI snapshot/component tests plus manual smoke on representative fixtures from every lane.

---

# 16. M11 — observability and data-quality control plane

**Goal:** know when the pipeline is wrong before the UI becomes wrong.

Add metrics for:

```text
ingest events/source/min
source staleness
source parse failures
dedup rate
observation -> incident latency
observation -> episode latency
classification fail-closed count
OCR success/dispute rate
region-only vs positioned rate
Drift queued/running/completed/failed/stuck
AIS coverage by AOI/time bucket
gap detector candidate rate
hypothesis candidate/rejected/published rate
case relink vs new-case rate
edge queue depth/retries
VM-edge projection mismatch count
```

Add structured logs with stable IDs: observation_id, incident_id, subject_id, episode_id, hypothesis_id, job_id.

No raw sensitive Humanitarian text in metrics/log labels.

Create a lightweight internal `/health/data` or equivalent analyst health endpoint summarizing freshness and stuck-work conditions without leaking private content.

Exit gate: controlled source outage, stuck Drift job and edge failure are all observable without inspecting the database manually.

---

# 17. M12 — senior test pyramid and deterministic replay suite

**Goal:** every future change can prove it did not corrupt semantics.

Required layers:

## Unit

Pure classifiers, extractors, evidence gates, lifecycle, geometry, publication policy.

## Contract

Pydantic/API schemas, VM-edge parity, privacy redaction.

## Integration

DB writes, migrations, case/episode linking, worker job lifecycle.

## Replay

Committed deterministic raw/normalized fixtures exercising full pipelines.

Mandatory replay scenarios:

```text
H1 Alarm Phone at-sea OCR point -> active incident -> Drift -> Live
H2 Alarm Phone land point -> incident -> no Drift -> Live
H3 Alarm Phone region-only -> area -> no fabricated point/no Drift
H4 memorial/retrospective post -> non-operational
H5 resolution post -> existing incident resolved, no duplicate case
H6 multiple semantic people counts remain distinct

S1 NUC -> Safety -> no Intelligence/no Drift
S2 restricted manoeuvrability -> Safety with vessel-role context only
S3 port-wide AIS outage -> no isolated dark-transit hypothesis
S4 isolated coverage-supported AIS gap -> candidate dark_transit
S5 neutral rendezvous -> observation only
S6 sanctions-listed vessel + rendezvous only -> official-list fact + candidate at most, no evasion publication
S7 identity conflict -> identity-integrity episode, not sanctions by default
S8 impossible position jump -> spoofing feature with evidence
S9 two anomalies days apart on same MMSI -> two episodes
S10 SAR unmatched candidate -> candidate wording, no confirmation
```

## Property/invariant tests

Examples:

```text
Safety => drift_eligible is always false
public Humanitarian => no MMSI/IMO keys
unknown classification => publishable false
hypothesis published => evidence links and review exist
region_only => no automatic Drift
```

## Load/resource

On the ARM target, test bounded memory/CPU for normal API + workers. Heavy satellite work cannot starve Live/API.

Exit gate: one command or documented CI workflow runs the complete release replay matrix on the release commit.

---

# 18. M13 — CI/CD and production release gate

PR required checks:

```text
backend pytest
ruff
migration safety when DB touched
web lint
typecheck
web tests
web build
replay subset relevant to changed lane
privacy/publication contract when projection touched
```

Nightly/extended checks:

```text
full replay corpus
historical sanitized corpus scorer
AIS behaviour/integrity scorer
migration/backfill dry-run against sanitized DB snapshot
edge parity fixtures
worker stuck-job recovery
```

Production deploy sequence:

```text
1. backup DB / verify migration head
2. deploy code with compatibility reads
3. run migrations
4. run bounded backfill/replay checks
5. verify source freshness
6. verify Humanitarian Live representative records
7. verify Safety lane
8. verify no unreviewed Intelligence allegation is public
9. verify workers and edge queues
10. record release SHA + scorer/replay report
```

Rollback must not require deleting new evidence tables. Roll back application reads/writes while retaining append-only data for later recovery.

---

# 19. Final stabilization period

Before declaring SeaCommons stable, run a continuous **7-day production observation window** on one release line.

Release is stable only if all are true:

- no Humanitarian invariant violation;
- no Safety event promoted to Intelligence by fallback;
- no Safety-originated automatic Drift;
- no duplicate-case explosion;
- no duplicate episode explosion;
- no unreviewed allegation-shaped Maritime item published;
- no systematic feed starvation;
- no mandatory worker permanently stuck;
- source freshness alerts operate;
- edge and VM stay semantically aligned;
- replay suite remains green on the same production commit;
- database migrations/backfills are idempotent;
- operator can trace any surfaced item back to source observation and evidence chain.

---

# 20. Recommended PR sequence from current state

Execute in this exact order unless a discovered production blocker requires an explicitly documented emergency PR.

```text
#66  Safety authoritative routing + no Drift resurrection          [OPEN]
#67  EventAssessment -> projection -> ConePanel                    [NEXT]
#68  neutral rendezvous semantics                                  
#69  remove vessel-class analytical fallbacks                      
#70  darkship cue endpoint + candidate semantics                   
#71  SourceObservation durable schema + write service              
#72  canonical source adapters + idempotent ingest                 
#73  HumanitarianRecognition V2 typed classifier                   
#74  humanitarian corpus/scorer expansion                         
#75  LocationEvidence canonical pipeline                           
#76  Humanitarian Drift replay matrix                              
#77  AIS deterministic replay adapter + scored behaviour corpus    
#78  CoverageBaseline + coverage-aware gap features                
#79  remove vessel-class gap/spoof suppressions                    
#80  VesselSubject + dated identity aliases                        
#81  bounded MaritimeEpisode builder                               
#82  InvestigationHypothesis + EvidenceLink persistence            
#83  evidence gates + review lifecycle                             
#84  Sentinel/STAC association layer                               
#85  legacy dual-write/backfill + semantic cleanup                 
#86  canonical publication policy + edge parity                    
#87  evidence-first Humanitarian/Maritime UI                       
#88  observability + data-health endpoint                          
#89  complete replay/load/migration release gate                   
```

PR numbers are illustrative after #66; if GitHub assigns different numbers, preserve the order and milestone identity.

---

# 21. Definition of Done

SeaCommons reaches the target state when:

```text
RAW SOURCES
  are persisted losslessly and replayably

HUMANITARIAN
  is structured by incident type/lifecycle/counts/location evidence
  preserves privacy
  produces Drift only through the canonical humanitarian gate

MARITIME SAFETY
  is visible and useful
  never becomes Intelligence or Drift by fallback

MARITIME INTELLIGENCE
  operates on bounded vessel episodes
  uses coverage-aware/replayable behaviour features
  separates identity facts, sanctions facts and behavioural hypotheses
  requires evidence links and review before allegation publication

SATELLITE / CROSS-SENSOR
  adds corroboration without overstating attribution

DATABASE
  stores typed observations/features/incidents/episodes/hypotheses/evidence
  no longer depends on semantic read-time legacy corrections

PUBLICATION
  is one canonical policy with Humanitarian/Maritime privacy gates
  VM and edge are contract-tested

UI
  displays observation, interpretation, evidence and uncertainty separately

TESTING
  has deterministic end-to-end replay for both sides
  has measured classifier/detector baselines
  verifies migrations, privacy and publication invariants

OPERATIONS
  exposes source freshness, queue health, stuck jobs, coverage and pipeline latency
  survives restart/backfill idempotently
  passes the 7-day stabilization window on one release SHA
```

At that point SeaCommons is no longer “a Live map with many detectors”. It is a specific maritime OSINT platform whose core product is a traceable evidence chain from source observation to reviewed public conclusion.