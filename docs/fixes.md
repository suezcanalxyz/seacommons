# SeaCommons Final Maritime OSINT Stabilization Plan

> **For Claude/Codex agentic workers:** this file is the single execution source of truth. Work in small PRs, in order, with TDD and explicit exit gates. Do not skip ahead because a later task looks easier. Do not reopen a DONE invariant unless a regression test proves it broke.

**Goal:** stabilize SeaCommons as a production-grade, evidence-first maritime OSINT platform with two first-class operational sides — Humanitarian and Maritime — sharing one canonical data/evidence pipeline while preserving different publication, privacy and analytical rules.

**Architecture:** all external inputs become immutable observations. Deterministic processors derive structured features. Correlation groups observations/features into bounded episodes. Episodes may open hypotheses only through explicit evidence gates. Humanitarian incidents and Maritime Intelligence hypotheses remain distinct products but share provenance, storage, review, replay, observability and public-projection infrastructure.

**Production target:** current ARM VM (~12 GB RAM), FastAPI/Python backend, PostgreSQL production storage, React/Vite/MapLibre web app, optional isolated workers for OCR/Drift/Sentinel processing.

**Current verified baseline:** `main` after PR #65 (`f51a2471f70880fadce1d49225c4d76d19348338`), `581 passed`, ruff clean. PR #66 is open and mergeable with `584 passed`; it fixes authoritative Safety routing and Safety→Drift resurrection and is the first gate in this plan.

---

# 0. Product definition

SeaCommons is not a generic vessel tracker and not a risk-scoring dashboard. It is a maritime evidence engine.

The system must answer five questions for every surfaced item:

1. **What was actually observed?**
2. **Where did that observation come from?**
3. **What was deterministically derived from it?**
4. **What interpretation is being investigated, and why?**
5. **What can safely be published, to whom, and with what uncertainty?**

The two product sides are:

```text
HUMANITARIAN
  distress
  missing
  rescue/update
  interception
  pushback
  resolution
  land_humanitarian

MARITIME
  safety
  intelligence
  environmental
```

Humanitarian is people-centred and privacy-constrained. Maritime Intelligence is vessel/episode-centred and evidence-gated. Safety is operational context, never Intelligence by fallback.

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
20. No task is DONE until the exit gate below it is proven by tests.

---

# 2. Execution loop for Claude

Claude should run continuously using this exact loop.

```text
READ docs/fixes.md
↓
READ current main + open PRs
↓
SELECT first unchecked task whose dependencies are DONE
↓
WRITE failing regression/integration test
↓
IMPLEMENT smallest coherent change
↓
RUN targeted tests
↓
RUN full backend suite + ruff
↓
RUN web tests/lint/build if frontend touched
↓
RUN replay/smoke gate for the affected pipeline
↓
OPEN PR with root cause + invariants + before/after evidence
↓
STOP at PR boundary unless CI is green
↓
AFTER MERGE: update task status in docs/fixes.md and continue
```

Rules for the loop:

- one semantic concern per PR unless two fixes share the same root-cause boundary;
- never hide a discovered root cause behind a downstream workaround;
- if a committed test encodes the wrong behaviour, fix the test and explain why;
- never tune AIS thresholds before a replay/scorer exists for that detector;
- never call synthetic fixtures “production validation”;
- every PR body must state what remains out of scope;
- every migration must be reversible and SQLite-test-compatible;
- if a new bug invalidates an earlier assumption, update this file before continuing.

---

# 3. Current state matrix

## DONE / protected

- Alarm Phone multilingual dedup and case relinking.
- Humanitarian OCR → point/area logic.
- land/region/disputed points cannot originate maritime Drift.
- backend persisted Drift is authoritative.
- category-based public styling replaces severity-based styling.
- Humanitarian cards intentionally hide vessel identity blocks.
- `service_taxonomy.py` exists and fails closed.
- NUC/aground/restricted manoeuvrability producers emit Safety metadata.
- old NUC mobility fusion escalation was removed.
- `EventAssessment` exists for core Safety events.
- alert-recognition corpus/scorer exists.
- Humanitarian keyword baseline false positives from PR #64 were fixed in PR #65.

## IN FLIGHT

### PR #66 — Safety authority + projection consistency

Must merge before new work.

Covers:

- explicit `metadata.maritime_domain` wins in `IntelEvent.maritime_domain()`;
- legacy Safety cannot resurrect cargo Drift;
- `mode=safety` exists as a distinct VM feed bucket;
- Safety is excluded from humanitarian edge feed;
- tests updated from incorrect legacy behaviour.

**Exit gate:** `584/584`, ruff clean, CI green, merge.

---

# 4. Milestone M0 — semantic correctness

**Objective:** eliminate every remaining place where the same event acquires different meaning depending on which consumer reads it.

## M0.1 Merge and regression-lock PR #66

- [ ] merge #66 only after green CI;
- [ ] add a regression fixture representing a legacy NUC row and a current explicit Safety row;
- [ ] prove producer → DB object → projection → feed preserves Safety and `drift_eligible=False`.

**Exit gate:** Safety cannot become Humanitarian, Intelligence, grey-zone or Drift through any current read/projection path.

## M0.2 EventAssessment end-to-end

**Files:** `core/intel/assessment.py`, `core/live/projection.py`, `core/domain/live_contracts.py`, `ConePanel.jsx`, panel tests.

Project:

```text
assessment_observation
assessment_interpretation
assessment_evidence_level
assessment_confidence
assessment_confidence_basis[]
assessment_supporting_evidence[]
assessment_contradicting_evidence[]
assessment_caveats[]
assessment_recommended_action
assessment_rule_ids[]
assessment_classification_version
```

- [ ] `ConePanel` stops using `descriptionOf(props.type)` as event interpretation;
- [ ] `descriptionOf()` remains category help only;
- [ ] events with no assessor show no invented interpretation;
- [ ] Safety reports visibly explain self-report/corroboration limitations.

**Exit gate:** two events of the same type with different evidence render different assessments.

## M0.3 Neutral rendezvous observation

**Files:** `core/mda/watch.py`, `core/intel/fusion.py`, taxonomy + tests.

Raw STS event:

```text
service=maritime
lane=intelligence
observation_type=rendezvous
evidence_level=derived
publication_status=internal
hypothesis_type=None
```

- [ ] remove unconditional `maritime_domain=sanctions` from `_emit_rendezvous()`;
- [ ] sanctions fact is separate from rendezvous observation;
- [ ] sanctions-evasion hypothesis requires additional evidence;
- [ ] STS-zone presence is context, not proof.

**Exit gate:** a normal offshore rendezvous never appears as sanctions/evasion by itself.

## M0.4 Remove vessel-class-as-analysis

- [ ] eliminate `Other vessel` as analytical fallback;
- [ ] vessel type may appear under Context only;
- [ ] remove class-based category titles from investigation output;
- [ ] public unknown classification fails closed rather than becoming “other”.

**Exit gate:** vessel class can influence baseline/context, never the event/hypothesis label.

## M0.5 Darkship cue language + current STAC

- [ ] migrate to current Copernicus Data Space STAC API;
- [ ] replace “likely the dark vessel” with candidate wording;
- [ ] persist acquisition timestamp, scene ID, detection timestamp and reachable-area uncertainty;
- [ ] no association unless observation times overlap the reachable-state interval.

**Exit gate:** darkship output never claims attribution from spatial containment alone.

---

# 5. Milestone M1 — canonical observation layer

**Objective:** stop using `IntelEvent.meta` as the universal semantic datastore.

Create durable entities and migrations:

```text
MaritimeObservation
BehaviourFeature
VesselSubject
EvidenceLink
SourceRecord
```

Minimum `MaritimeObservation` fields:

```text
observation_id
service
lane
observation_type
source_id
source_kind
source_timestamp_utc
received_at
geometry
location_uncertainty_m
subject_ids[]
payload_hash
verification_status
publication_status
schema_version
created_at
```

Minimum `BehaviourFeature` fields:

```text
feature_id
feature_type
algorithm
algorithm_version
parameters
input_observation_ids[]
value_json
geometry
started_at
ended_at
created_at
```

Tasks:

- [ ] migrations + ORM models;
- [ ] adapters from existing IntelEvent producers;
- [ ] dual-write for one release;
- [ ] no destructive migration of current `intel_events`;
- [ ] evidence links connect old compatibility events to new observation IDs;
- [ ] deterministic content identity for replay/idempotency.

**Exit gate:** a new AIS observation and a new Humanitarian observation can be reconstructed without reading opaque free-form metadata.

---

# 6. Milestone M2 — Humanitarian Recognition V2

**Objective:** turn Humanitarian from distress keyword detection into structured incident recognition without losing the stable Alarm Phone pipeline.

Keep `is_distress()` as a cheap prefilter only.

Create `HumanitarianAssessment`:

```text
incident_type
lifecycle
people.aboard
people.rescued
people.missing
people.dead
people.injured
people.precision
vessel.condition
vessel.description
needs[]
actors[]
location_evidence[]
temporal_evidence[]
source_evidence[]
confidence
uncertainty_reasons[]
rule_ids[]
classification_version
```

Recognize at minimum:

```text
distress
missing
rescue_update
shipwreck
medical_emergency
interception
pushback
resolution
retrospective
advocacy
land_humanitarian
unknown_humanitarian
```

Tasks:

- [ ] separate recognition from publication decision;
- [ ] lifecycle derived from event/thread evidence, not one keyword;
- [ ] multiple people counts can coexist in one incident;
- [ ] distinguish “50 aboard, 40 rescued, 10 missing” correctly;
- [ ] preserve original and translated source text internally;
- [ ] public projection remains privacy-filtered;
- [ ] expand corpus with sanitized real historical Alarm Phone/SAR examples;
- [ ] retain synthetic hard negatives as regression fixtures;
- [ ] scorer reports per-class precision/recall/F1 + lifecycle accuracy + people-field accuracy.

**Exit gate:** Humanitarian classification is evaluated on a mixed real/synthetic corpus and can replay historical incidents deterministically.

---

# 7. Milestone M3 — location evidence and image pipeline

**Objective:** make every Humanitarian coordinate auditable.

Canonical result:

```text
LocationEvidence
  method
  lat/lon or area
  uncertainty_m
  review_status
  source_asset_id
  extracted_text
  anchors[]
  engine_votes[]
  diagnostics
```

Tasks:

- [ ] unify text coordinates, OCR coordinates, map-pin inference and place-region fallback under one resolver;
- [ ] keep ROI/preprocessing/OCR-engine outputs separately;
- [ ] coordinate consensus requires explicit engine votes/tolerance;
- [ ] pin geolocation stores anchors and residual error;
- [ ] region-only always produces area geometry, never a fake precise point;
- [ ] land/sea classification happens after coordinate resolution;
- [ ] backfill/replay tool reruns historical media using versioned algorithms;
- [ ] benchmark old vs new resolver on labelled screenshots.

**Exit gate:** every displayed point/area can explain where the coordinate came from and why its uncertainty/review state is what it is.

---

# 8. Milestone M4 — AIS replayable feature engine

**Objective:** stop tuning stateful AIS detectors against live intuition.

Build a deterministic replay adapter for:

```text
gap
long_gap
sudden_stop
loiter
dwell
rendezvous
position_jump
impossible_speed
frozen_position
circular_pattern
mmsi_duplicate
identity_change
```

Tasks:

- [ ] pure feature extraction from ordered track samples;
- [ ] all detector parameters serialized with the feature;
- [ ] `ais_behaviour.jsonl` scorer becomes executable;
- [ ] `ais_integrity.jsonl` scorer becomes executable;
- [ ] generate negative fixtures for port, anchorage, ferry, tug, fishing, leisure and receiver outage behaviour;
- [ ] CI fails when detector metrics regress beyond declared tolerances.

**Exit gate:** no AIS threshold change is accepted without before/after replay metrics.

---

# 9. Milestone M5 — coverage-aware AIS gaps

**Objective:** replace vessel-class blacklists with reception/context evidence.

Create `CoverageBaseline` using SeaCommons' own historical reception:

```text
cell/AOI
hour/day profile
source
expected_message_density
active_vessel_count
median_gap
p95_gap
coast_distance
port/anchorage/TSS context
jamming_context
coverage_quality
sample_count
version
```

Gap feature includes:

```text
silent_seconds
expected_gap_seconds
coverage_quality
jamming_score
coast_distance
last_speed
last_course
receiver_density
baseline_deviation
counter_indicators[]
```

- [ ] evaluate all vessel classes;
- [ ] vessel role modifies expectation but cannot suppress detection outright;
- [ ] feed-wide outage becomes coverage failure, not vessel anomaly;
- [ ] low coverage lowers evidence strength;
- [ ] gap never directly creates “dark vessel” or sanctions allegation.

**Exit gate:** known port/ferry/fishing negatives stop relying on hard-coded class exclusions.

---

# 10. Milestone M6 — bounded Maritime episodes

**Objective:** replace `one MMSI = one episode`.

Create `MaritimeEpisode`:

```text
episode_id
subject_ids[]
started_at
ended_at
state
service
lane
observation_ids[]
feature_ids[]
area
summary_facts
created_at
updated_at
```

Episode boundaries use explicit rules:

- time gap;
- return to baseline behaviour;
- location/AOI discontinuity;
- lifecycle resolution;
- new encounter counterpart;
- configurable max duration.

Tasks:

- [ ] retire semantic rewriting inside `coalesce_security_vessel_episodes()`;
- [ ] subject identity is stable across episodes;
- [ ] one vessel can have several independent episodes in a day;
- [ ] one STS episode can have two subjects;
- [ ] Safety and Intelligence episodes never merge merely because MMSI matches.

**Exit gate:** replay of a track with NUC → normal → later AIS gap yields separate Safety and Intelligence episodes.

---

# 11. Milestone M7 — hypothesis/evidence engine

**Objective:** make Maritime Intelligence an investigation layer, not an anomaly feed.

Create `InvestigationHypothesis`:

```text
hypothesis_id
hypothesis_type
episode_id
state
 evidence_stage
reason_codes[]
counter_indicators[]
evidence_link_ids[]
assessment
reviewed_by
reviewed_at
published_at
classification_version
```

Lifecycle:

```text
candidate → collecting → review_ready → assessed → published
          ↘ rejected
          ↘ expired
```

Initial hypothesis types:

```text
dark_transit
covert_rendezvous
concealed_port_call
identity_deception
position_spoofing
route_deception
sanctions_evasion_pattern
infrastructure_pattern
```

Evidence examples:

- official sanctions list match = fact, not evasion hypothesis;
- STS + sanctions match + gap around encounter can support sanctions-evasion candidate;
- infrastructure proximity alone cannot support infrastructure-threat hypothesis;
- duplicate MMSI + incompatible simultaneous positions supports identity-deception candidate;
- multiple impossible movement features + independent context can support spoofing candidate.

Publication function must fail closed.

**Exit gate:** no Maritime Intelligence public marker exists without a hypothesis record and its evidence links.

---

# 12. Milestone M8 — identity and sanctions separation

**Objective:** separate identity integrity from designation.

Create distinct observation/fact types:

```text
identity_integrity
official_sanctions_match
registry_change
flag_change
imo_mmsi_mismatch
mmsi_duplicate
name_alias
```

Tasks:

- [ ] official OFAC/EU/UN lists canonical;
- [ ] OpenSanctions optional enrichment only;
- [ ] sanctions match can publish as sourced list fact;
- [ ] sanctions match alone never implies evasion;
- [ ] duplicate MMSI/identity anomaly routes to identity-integrity, not sanctions;
- [ ] identity history is dated and source-specific.

**Exit gate:** “sanctioned vessel” and “identity anomaly” are two different evidence paths in DB, API and UI.

---

# 13. Milestone M9 — cross-sensor maritime intelligence

**Objective:** correlate AIS with independent sensors without overstating attribution.

Inputs:

- Sentinel-1 scene metadata/detections;
- GFW research-only SAR/encounter data where licensing permits;
- Copernicus Marine/weather context;
- EMODnet ports/infrastructure/AOI;
- GNSS interference layers;
- official nav warnings;
- Humanitarian events only as nearby context, never automatic causation.

Association requirements:

```text
sensor time alignment
trajectory propagation
position uncertainty
sensor detection uncertainty
candidate count
AIS-match status
counter-candidates
source licence
algorithm version
```

Tasks:

- [ ] Sentinel queries isolated from API process;
- [ ] no automatic heavy GRD inference on API worker;
- [ ] cache scene metadata;
- [ ] bounded queue/timeout/retry policy;
- [ ] candidate association returns uncertainty, never binary attribution without evidence.

**Exit gate:** a darkship cue can be reproduced from stored AIS inputs + scene metadata + association parameters.

---

# 14. Milestone M10 — public and analyst product surfaces

**Objective:** UI mirrors the evidence architecture.

Public modes:

```text
Humanitarian
Safety
Maritime Intelligence (reviewed/published only)
Environmental
```

Analyst mode additionally exposes:

```text
raw observation timeline
feature values
coverage baseline
identity history
evidence graph
hypothesis state
counter-indicators
source provenance
review actions
```

Public Humanitarian:

- no professional vessel identifiers;
- people-centred incident description;
- location uncertainty explicit;
- source/public thread updates allowed when safe;
- Drift only where canonical gate allows it.

Public Maritime:

- neutral observation wording for Safety;
- reviewed evidence-first wording for Intelligence;
- identifier may appear only as sourced vessel identity, not as the analytical conclusion;
- category color driven by semantic category, never severity.

**Exit gate:** every visible card can be traced to service/lane + assessment/hypothesis + provenance.

---

# 15. Milestone M11 — backfill and legacy cleanup

**Objective:** stop carrying compatibility heuristics indefinitely.

Tasks:

- [ ] build dry-run classifier for historical `intel_events`;
- [ ] report rows affected before migration;
- [ ] backfill canonical service/lane, case type, lifecycle, location status and observation IDs;
- [ ] remove legacy `maritime_domain()` semantic correction after backfill is proven;
- [ ] remove Safety→grey_zone compatibility branches;
- [ ] remove stale cargo Drift metadata;
- [ ] clean stuck drift rows such as historically known land/computing residues;
- [ ] deduplicate deterministic correlated alerts/cases;
- [ ] retain immutable forensic/source records.

**Exit gate:** current runtime no longer needs read-time semantic correction for historical records.

---

# 16. Milestone M12 — production observability and data quality

**Objective:** detect semantic/data degradation before the UI reveals it.

Metrics:

```text
ingest events/source/min
source freshness
unclassified rate
location resolution success
OCR disputed rate
region-only rate
Drift eligibility count/rejection reason
Safety events by type
AIS feature counts
coverage-quality distribution
episodes opened/closed
hypotheses by state
publication rejections
edge/VM parity mismatches
queue depth/retries
DB write failures
```

Add data-quality assertions:

- no Safety event with `drift_eligible=True`;
- no Humanitarian public record exposing MMSI/IMO;
- no published Intelligence record without evidence links/review;
- no region-only Humanitarian record with precise public point;
- no STS observation classified sanctions solely from rendezvous;
- no unresolved unknown classification silently routed to public.

**Exit gate:** violations are observable counters/logged errors and covered by tests.

---

# 17. Milestone M13 — evaluation and replay release gate

Every release must run four evaluation lanes.

## Humanitarian

- real + synthetic recognition corpus;
- precision/recall/F1 per incident class;
- lifecycle accuracy;
- people-field extraction accuracy;
- coordinate/location-status accuracy.

## Maritime Safety

- NUC/aground/restricted manoeuvrability replay;
- benign routine-status negatives;
- routing + publication correctness.

## Maritime Behaviour/Integrity

- gap/spoof/loiter/rendezvous replay metrics;
- port/ferry/fishing/tug/pleasure negatives;
- coverage outage negatives.

## End-to-end public projection

Replay representative incidents through:

```text
source observation
→ persisted observation
→ feature/classification
→ episode/incident
→ assessment/hypothesis
→ publication policy
→ VM feed
→ edge feed where applicable
→ web presentation
```

**Release gate:** no stage may be mocked away in the final integration replay except external network access, which must be replaced by recorded fixtures.

---

# 18. Milestone M14 — final production stabilization

Run a production verification window and compare expected vs actual data.

Checklist:

- [ ] current Alarm Phone posts ingest and deduplicate;
- [ ] OCR/region-only/land examples render correctly;
- [ ] automatic Humanitarian Drift appears only for eligible maritime points;
- [ ] NGO/SAR context is fresh and correctly classified;
- [ ] Safety feed contains NUC/aground/restricted events and never Security-coalesces them;
- [ ] AIS anomaly volume is bounded and explainable;
- [ ] STS observations remain neutral until evidence gate;
- [ ] vessel episodes are bounded;
- [ ] hypotheses carry evidence/counter-evidence;
- [ ] published Intelligence records have review provenance;
- [ ] edge and VM Humanitarian semantics match;
- [ ] memory/CPU/DB growth remain acceptable on ARM VM;
- [ ] queues recover after restart;
- [ ] no duplicate case explosion;
- [ ] no stale public markers remain active indefinitely.

**Definition of production-stable:** seven continuous days without invariant violations, duplicate-case explosion, unexplained public classification drift, stuck mandatory jobs or feed starvation; all replay suites green from the same release commit.

---

# 19. PR order from current state

Claude should execute in this order unless a newly discovered root cause forces a documented dependency change:

```text
#66  Safety authority + no Safety Drift        [IN FLIGHT]
#67  EventAssessment → public contract/UI
#68  neutral rendezvous semantics
#69  vessel-class/context cleanup + fail-closed unknowns
#70  darkship cue semantics + current Copernicus STAC
#71  observation/evidence schema + migrations
#72  dual-write producers into observation layer
#73  HumanitarianAssessment V2
#74  real/sanitized Humanitarian corpus + scorer expansion
#75  canonical LocationEvidence/image resolver
#76  AIS deterministic replay adapters
#77  executable behaviour/integrity scorer
#78  CoverageBaseline + coverage-aware gaps
#79  bounded MaritimeEpisode model
#80  migrate Live security grouping to bounded episodes
#81  InvestigationHypothesis + evidence graph
#82  publication/review gate
#83  identity-integrity vs sanctions separation
#84  cross-sensor association model
#85  analyst/public evidence UI
#86  historical backfill + legacy semantic cleanup
#87  observability/data-quality invariant metrics
#88  full replay/e2e release gate
#89  production verification fixes only
```

PR numbers are indicative; task order is authoritative.

---

# 20. What “complete maritime OSINT platform” means

SeaCommons is complete for this release when:

1. Humanitarian incidents are structured, deduplicated, positioned with auditable uncertainty, lifecycle-aware and privacy-safe.
2. AIS observations are stored independently from derived anomalies.
3. Detector outputs are replayable and quantitatively evaluated.
4. AIS gaps are coverage-aware rather than vessel-class-filtered.
5. vessel identity, sanctions facts, behaviour anomalies and Safety states are distinct concepts.
6. vessel episodes are bounded in time/behaviour rather than grouped forever by MMSI.
7. Maritime Intelligence consists of explicit hypotheses backed by evidence and counter-evidence.
8. cross-sensor associations preserve acquisition time and uncertainty.
9. public Intelligence cannot bypass human/evidence gates.
10. every public item explains observation, interpretation, evidence level, provenance and caveats.
11. historical data has been backfilled enough that runtime semantic hacks can be removed.
12. CI + replay + production data-quality monitoring jointly guard the system.
13. the ARM production target remains stable under normal workload.
14. Claude can continue from this file alone, one PR at a time, without inventing architecture or reopening settled semantics.

When all fourteen conditions are true, the stabilization roadmap is complete. Further work becomes feature development rather than repair of the data/evidence foundation.
