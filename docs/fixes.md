# SeaCommons Post-#65 Evidence Engine Fixes Roadmap

> **For agentic workers:** execute this document task-by-task. Do not skip exit gates, do not broaden scope, and do not reopen already-stabilized Humanitarian OCR/Drift work unless a regression test fails.

**Goal:** move SeaCommons from a mixed collection of event heuristics into a selective, explainable evidence engine with one canonical Humanitarian pipeline and one canonical Maritime pipeline, while preserving the stable production behaviour reached through PRs #59–#65.

**Audited baseline:** `main` after PR #65 (`f51a2471f70880fadce1d49225c4d76d19348338`), 2026-09-03.

**Verified test baseline:** `581 passed`, `ruff check` clean.

**Status vocabulary used below:**

- `DONE` — implementation exists, is wired into the relevant runtime path, and is covered by regression tests.
- `PARTIAL` — a primitive exists but is not yet authoritative, fully wired, or fully represented in UI/storage.
- `BROKEN` — current behaviour contradicts the target semantics or reintroduces a known invariant violation.
- `PLANNED` — architecture or feature not yet implemented.

---

# 0. Non-negotiable product invariants

These are release constraints, not suggestions.

1. SeaCommons classifies and explains evidence; it does not present a synthetic risk score as truth.
2. Humanitarian, Maritime Safety, Maritime Intelligence, and Environmental are positive classifications. Unknown never falls into another compartment by complement.
3. A self-reported AIS navigational status is an observation, not proof of mechanical failure and never proof of suspicious intent.
4. `not_under_command`, `aground`, and `restricted_manoeuvrability` belong to `service=maritime`, `lane=safety`.
5. Maritime Safety observations are never cargo-Drift eligible.
6. Alarm Phone / Humanitarian drift remains a separate humanitarian-only model. Maritime Intelligence must not reuse humanitarian drift semantics.
7. A rendezvous is not a sanctions event. An AIS gap is not proof that AIS was deliberately disabled. An unmatched SAR detection is not a confirmed dark vessel.
8. Public allegations require explicit evidence and review. Direct official-list matches may publish as list facts without implying evasive behaviour.
9. Public Humanitarian views must not expose MMSI, IMO, MarineTraffic dossier links, or professional-vessel identity blocks.
10. Vessel class is context, never an investigation category or a substitute for evidence.
11. Raw observations, derived features, correlations, hypotheses, and public projections must remain distinguishable.
12. The current ARM production VM (~12 GB RAM) remains the deployment target. Heavy SAR inference must be optional, bounded, and isolated from the API process.
13. No source may be scraped in violation of licence/terms. GFW remains research/benchmark-only unless a compatible licence is obtained. OpenSanctions is optional enrichment; official OFAC/EU/UN facts remain canonical.
14. Preserve prohibitions on migrant interception support, border-enforcement targeting, military targeting, and commercial surveillance aggregation.

---

# 1. Baseline: what is already DONE

The following work landed before or through PR #65 and must be treated as regression-protected infrastructure, not reopened by default.

## 1.1 Humanitarian ingestion / Alarm Phone

`DONE`

- Alarm Phone translated reposts fold onto one incident.
- Real extracted OCR coordinates replace stale region polygons.
- A real machine-extracted maritime point can originate Humanitarian drift under the canonical gate while retaining uncertainty and review state.
- Region-only, disputed, withheld/land and invalid points cannot originate maritime drift.
- Land Humanitarian incidents remain visible as Humanitarian events without creating maritime Drift.
- Durable lookup prevents drift-gate bypass when an Intel event has fallen out of the in-memory deque.
- Alarm Phone dedup survives DB load-window truncation after restart.
- Historical Alarm Phone reprocessing/backfill exists.
- Category-based visual identity replaced severity-based Live styling.
- Browser-side automatic Alarm Phone drift was removed; backend/worker Drift is authoritative.
- Public Humanitarian cards no longer intentionally expose MMSI/IMO blocks.
- Duplicate case creation across later correlated signals is mitigated by PR #60 case relinking.

## 1.2 Phase-0 semantics from PRs #61–#65

`DONE` as primitives, with wiring caveats called out later.

- `core/intel/service_taxonomy.py` exists.
- Fail-closed `classify_service(...)` exists.
- NUC/aground/restricted manoeuvrability producer events now emit `service=maritime`, `lane=safety`, `drift_eligible=False`.
- NUC no longer auto-promotes through the removed vessel-mobility fusion rule.
- `EventAssessment` exists for NUC, aground and restricted manoeuvrability.
- Alert-recognition corpus and scorer exist.
- Humanitarian baseline FP cases found in PR #64 were fixed in PR #65.
- `is_distress()` currently scores 1.00 precision / 1.00 recall / 1.00 F1 on the small committed Humanitarian corpus.

## 1.3 Current baseline warning

The 1.00 Humanitarian metric is **not production validation**. The corpus is still small and synthetic. Treat it as a regression suite, not as proof that the classifier is complete.

---

# 2. Audit findings after PR #65

This section is the authoritative defect inventory for the current release line.

| ID | Status | Current code | Problem | Required outcome |
|---|---|---|---|---|
| A-01 | `BROKEN` | `core/live/feed.py` still routes with `compartment_for_domain(event.maritime_domain())` | `service/lane` exists but is not the routing authority | one canonical service/lane classifier drives feed compartment selection |
| A-02 | `BROKEN` | `core/live/projection.py` legacy `is_vessel_mobility_incident()` compatibility sets `drift_eligible=True` and cargo vessel type | can reintroduce the exact Safety→cargo-Drift behaviour removed in #62 | legacy projection may never upgrade Safety to Drift eligibility |
| A-03 | `PARTIAL` | `core/intel/assessment.py` exists; `ConePanel.jsx` still renders `descriptionOf(props.type)` as Interpretation | EventAssessment is not visible or transported as the real assessment | backend assessment fields are projected and UI consumes them |
| A-04 | `BROKEN` | `core/live/vessel_episodes.py` groups all vessel signals by MMSI | vessel identity is used as an episode boundary | stable subject + bounded episodes separated by time/behaviour |
| A-05 | `BROKEN` | vessel episode output rewrites domain as `sanctions` if match else `grey_zone` | Safety/identity/context distinctions are flattened | episode preserves service/lane + observation types + hypothesis state |
| A-06 | `BROKEN` | `core/mda/watch.py::_emit_rendezvous()` writes `maritime_domain="sanctions"` for all STS pairs | observation is born as an allegation-shaped domain | neutral rendezvous observation; sanctions hypothesis only after evidence gate |
| A-07 | `BROKEN` | `scan_gaps()` excludes pleasure/passenger/fishing/tug classes | class blacklist substitutes for coverage/context modelling | all classes evaluated; coverage and operational context determine confidence |
| A-08 | `BROKEN` | spoofing path repeats class-based suppressions | vessel role is treated as evidence for/against spoofing | feature/context baseline replaces class exemption logic |
| A-09 | `BROKEN` | `core/mda/darkship_cue.py` says unmatched SAR target is “likely the dark vessel” | correlation strength is overstated | candidate wording + time-aligned association score + uncertainty |
| A-10 | `BROKEN` | `darkship_cue.py` uses old Copernicus catalogue STAC endpoint | stale external contract | current Copernicus Data Space STAC endpoint |
| A-11 | `PARTIAL` | `tests/fixtures/alert_recognition/ais_behaviour.jsonl` and `ais_integrity.jsonl` exist but scorer reports NOT YET SCORED | no baseline for the detectors that most need tuning | deterministic replay/scoring adapters and real metrics |
| A-12 | `PARTIAL` | Humanitarian case metadata is regex-based and mostly one-dimensional (`people_reported`) | cannot represent aboard/rescued/missing/dead/injured simultaneously | structured HumanitarianAssessment with independent quantities/evidence |
| A-13 | `BROKEN` | frontend keeps `Other signal`, `Other vessel` and vessel-class-driven fallback semantics | unknown/context becomes analytical meaning | unknown is internal/unclassified; vessel class rendered only as optional context |
| A-14 | `PARTIAL` | `IntelEventDB.meta` still carries much of the semantics | observation, feature, episode, hypothesis and review state are flattened | durable evidence entities with typed relations |
| A-15 | `PARTIAL` | severity remains in DB/public contract and some detector logic | old scoring vocabulary can continue to influence semantics | keep compatibility field temporarily, but no routing/publication/evidence decision may depend on it |
| A-16 | `PARTIAL` | edge and VM now share projection primitives | parity improved, but any projection semantic bug propagates to both | contract tests must validate service/lane/publication parity explicitly |
| A-17 | `PARTIAL` | identity anomalies live in sanctions-shaped pathways | identity inconsistency is not designation | separate identity-integrity observation from official sanctions fact |
| A-18 | `PARTIAL` | infrastructure proximity produces `grey_zone` alerts | proximity is context, not interference evidence | preserve geometry/dwell observation; hypothesis requires independent corroboration |

---

# 3. Target architecture

## 3.1 Canonical service/lane taxonomy

```text
service=humanitarian
  lane=distress
  lane=missing
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

Within Maritime Intelligence, `hypothesis_type` is separate from `lane`:

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

Within Maritime Safety, `observation_type` is separate from `lane`:

```text
not_under_command
aground
restricted_manoeuvrability
navwarning
distress_beacon
```

`maritime_domain` remains a compatibility field during migration only. It must not remain the authoritative product-router.

## 3.2 Evidence ladder

```text
observed      direct sensor/source fact
derived       reproducible calculation from observations
corroborated  independent observations/modalities agree
assessed      human/operator interpretation recorded
confirmed     authoritative/documentary confirmation
```

Rules:

- no detector threshold can directly create `confirmed`;
- a single AIS field can be `observed`, never `assessed` by itself;
- a derived anomaly may become `corroborated` only with independent evidence;
- public allegations require at least `corroborated` plus review, except direct official-list facts;
- every assessment carries caveats and contradictory evidence when available.

## 3.3 Durable evidence model

Target entities:

```text
VesselSubject
  stable subject_id
  dated identity aliases / source

MaritimeObservation
  immutable sourced fact
  observation_type
  time / geometry / uncertainty
  source / provenance

BehaviourFeature
  algorithm + version + parameters
  input observation ids
  reproducible values

MaritimeEpisode
  bounded time window
  one or more subjects
  observation + feature membership

InvestigationHypothesis
  hypothesis_type
  lifecycle
  evidence_stage
  reason_codes
  counter_indicators

EvidenceLink
  typed relationship between observations/features/episodes/hypotheses

CoverageBaseline
  source/AOI/time receiver expectations
  density / jamming / coast / known blind-zone context
```

`IntelEventDB` remains the compatibility envelope used by existing feeds and public projections. It must stop being the only semantic datastore.

## 3.4 Hypothesis lifecycle

```text
candidate → collecting → review_ready → assessed → published
          ↘ rejected
          ↘ expired
```

Every transition stores:

- actor;
- timestamp;
- reason;
- evidence snapshot IDs/hash;
- previous state;
- new state.

---

# 4. P0 — restore semantic consistency after #65

**Priority:** immediate.

**Exit gate:** the newly introduced taxonomy and assessment primitives are actually authoritative in runtime paths, and no legacy compatibility path can reintroduce Safety→Intelligence or Safety→Drift behaviour.

## Task P0.1 — make `classify_service()` authoritative

**Files**

- Modify: `apps/api/core/intel/service_taxonomy.py`
- Modify: `apps/api/core/intel/public_policy.py`
- Modify: `apps/api/core/live/feed.py`
- Modify: `apps/api/core/live/projection.py`
- Modify: `apps/api/core/live_edge_publisher.py`
- Test: `tests/test_service_taxonomy.py`
- Test: `tests/test_live_compartments.py`
- Test: `tests/test_public_policy.py`
- Test: edge parity tests

**Required behaviour**

- [ ] Humanitarian/Safety/Intelligence/Environmental routing calls one canonical classifier.
- [ ] `compartment_for_domain()` becomes compatibility-only or is removed after all callers migrate.
- [ ] unknown service/lane fails closed.
- [ ] a stale `maritime_domain=grey_zone` cannot override `ais_nav_status_kind=not_under_command`.
- [ ] a bare `maritime_domain=sar` path is explicitly mapped only where the event is actually Humanitarian; no fallback-by-domain guessing.
- [ ] VM and edge produce the same routing result from the same event.

**Acceptance tests**

```python
assert classify_service(nuc_event).service == "maritime"
assert classify_service(nuc_event).lane == "safety"
assert classify_service(unknown_event).publishable is False
```

Add a feed integration test proving Safety survives routing without becoming Humanitarian or Intelligence.

## Task P0.2 — remove legacy Safety Drift resurrection

**Files**

- Modify: `apps/api/core/live/projection.py`
- Modify: `apps/api/core/live/vessel_episodes.py`
- Test: `tests/test_live_projection.py`
- Test: `tests/test_live_vessel_episodes.py`
- Test: `tests/test_vessel_incidents.py`

**Required behaviour**

- [ ] remove the compatibility path that sets `drift_eligible=True` for legacy vessel mobility incidents.
- [ ] never infer `drift_vessel_type="cargo"` from a Safety incident.
- [ ] coalescing may preserve an existing explicit eligible Intelligence modelling product, but cannot invent eligibility.
- [ ] NUC/aground/restricted manoeuvrability remain `drift_eligible=False` through producer → DB → projection → episode → UI.

**Regression case**

Create one legacy-style NUC event with the old event shape and prove projection cannot upgrade it to Drift eligibility.

## Task P0.3 — wire EventAssessment into projection and UI

**Files**

- Modify: `apps/api/core/intel/assessment.py`
- Modify: `apps/api/core/live/projection.py`
- Modify: `apps/api/core/domain/live_contracts.py`
- Modify: `apps/web/src/components/ConePanel.jsx`
- Test: `tests/test_assessment.py`
- Test: public projection tests
- Test: web panel tests

**Projected fields**

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

**Required behaviour**

- [ ] `ConePanel` no longer uses `descriptionOf(props.type)` as the event-specific Interpretation.
- [ ] `descriptionOf()` remains category help text only.
- [ ] events without an assessor show “Assessment not available” or omit the section; they never receive generic generated interpretation.
- [ ] two NUC events with different evidence continue to produce different interpretation/observation content.

## Task P0.4 — neutral rendezvous semantics

**Files**

- Modify: `apps/api/core/mda/watch.py`
- Modify: `apps/api/core/intel/fusion.py`
- Modify: `apps/api/core/intel/service_taxonomy.py`
- Test: `tests/test_mda_watch.py`
- Test: `tests/test_fusion.py`

**Required behaviour**

Raw STS/rendezvous observation:

```text
service=maritime
lane=intelligence
observation_type=rendezvous
publication_status=internal
evidence_level=observed/derived
hypothesis_type absent
```

A direct STS observation must **not** be stored as `maritime_domain=sanctions` solely because two vessels were close for N minutes.

Sanctions-evasion hypotheses may be opened only when additional evidence exists, for example:

- official sanctions-list match;
- gap before/after encounter;
- dark counterpart;
- meaningful draught change;
- concealed/irregular port call;
- repeated encounter sequence;
- reviewed satellite association.

Known STS-zone presence alone is context, not designation.

## Task P0.5 — remove vessel-class analytical fallbacks

**Files**

- Modify: `apps/web/src/components/ConePanel.jsx`
- Modify: `apps/web/src/features/intel/categories.js`
- Create or complete: `apps/web/src/features/live/identityDisclosure.js`
- Test: corresponding web unit tests

**Required behaviour**

- [ ] unknown ship type → omit row, never `Other vessel`.
- [ ] `Pleasure craft`, `Cargo ship`, `Fishing`, etc. may appear in an analyst-only context row when sourced from AIS registry metadata.
- [ ] vessel type never becomes a case category, evidence level, hypothesis type or title fallback.
- [ ] public Humanitarian path never shows MMSI, IMO, MarineTraffic link, or professional identity dossier.
- [ ] public Maritime identifiers appear only where the product policy explicitly allows them and never as allegation/category.

## Task P0.6 — darkship cue correctness

**Files**

- Modify: `apps/api/core/mda/darkship_cue.py`
- Test: `tests/test_darkship_cue.py`

**Required changes**

- [ ] use current Copernicus Data Space STAC API (`https://stac.dataspace.copernicus.eu/v1/`).
- [ ] replace “likely the dark vessel” with “unmatched SAR candidate inside the reachable area”.
- [ ] store acquisition timestamp, AIS propagation timestamp, temporal offset, spatial distance and association uncertainty.
- [ ] never assign a detection to a vessel solely because it lies inside a growing reachable polygon.
- [ ] preserve source/licensing metadata for GFW/Sentinel-derived evidence.

---

# 5. P1 — Humanitarian Recognition V2

**Priority:** after P0 only.

**Goal:** retain the now-stabilized `is_distress()` as a cheap pre-filter while adding structured incident understanding that can distinguish multiple humanitarian states and quantities without collapsing everything into one boolean.

**Exit gate:** a single Humanitarian assessment represents incident type, lifecycle, quantities, actors, needs, location evidence and uncertainty; public policy reads that structure instead of re-parsing text independently.

## Task P1.1 — introduce `HumanitarianAssessment`

**Create:** `apps/api/core/intel/humanitarian_recognition.py`

Target shape:

```python
@dataclass(frozen=True)
class HumanitarianAssessment:
    is_humanitarian: bool
    incident_type: str
    lifecycle: str
    people_aboard: int | None
    people_rescued: int | None
    people_missing: int | None
    people_dead: int | None
    people_injured: int | None
    vessel_condition: list[str]
    needs: list[str]
    actors: list[str]
    place_mentions: list[str]
    temporal_markers: list[str]
    evidence: list[str]
    caveats: list[str]
    confidence: float
    confidence_basis: list[str]
    classification_version: str
```

No single `people_reported` field may overwrite distinct quantities.

## Task P1.2 — canonical Humanitarian incident taxonomy

Recognize explicitly:

```text
distress
missing
rescue_update
resolution
shipwreck
interception
pushback
land_humanitarian
advocacy
unknown_humanitarian
```

Rules:

- active shipwreck reporting is not the same as retrospective shipwreck commemoration;
- rescue underway is not necessarily resolution;
- “rescued 40, 12 missing” must preserve both quantities;
- an NGO organisation name containing SOS is not a distress call;
- policy/news use of “search and rescue” is not an operational incident;
- explicit 🆘/Mayday or direct active-call language may override concluded wording only where the ongoing need is clear.

## Task P1.3 — real/sanitized evaluation corpus

**Modify:** `tests/fixtures/alert_recognition/humanitarian.jsonl`

Keep synthetic fixtures, but add sanitized historical shapes from production data with private/personally identifying content removed.

Minimum corpus categories:

- direct Alarm Phone active calls;
- later updates for same incident;
- rescue underway;
- rescue completed;
- shipwreck active;
- shipwreck retrospective/memorial;
- missing/no-contact;
- interception/pullback;
- pushback;
- land-border humanitarian;
- NGO organisational updates;
- NGO vessel routine status;
- policy/news/annual report language;
- multilingual EN/IT/FR examples;
- mixed quantity cases.

Do not claim production quality until this corpus is materially larger than the current 12 examples.

## Task P1.4 — integrate one canonical Humanitarian assessment

**Files**

- Modify: `core/intel/humanitarian.py`
- Modify: relevant Twitter/Alarm Phone ingestion
- Modify: `core/intel/lifecycle.py`
- Modify: `core/live/projection.py`
- Modify: drift eligibility gate only where it consumes classification fields

Rule: classification is computed once and persisted. Consumers read canonical fields; they do not each run their own regex interpretation.

---

# 6. P2 — make AIS behaviour and integrity measurable before tuning

**Priority:** before changing thresholds.

**Exit gate:** `ais_behaviour.jsonl` and `ais_integrity.jsonl` are scored, with precision/recall/F1 and explicit FP/FN examples. No detector threshold change is accepted without before/after metrics.

## Task P2.1 — pure/replayable feature extraction

Extract deterministic feature builders from stateful live monitors.

Target pure interfaces:

```python
extract_gap_features(track, coverage_context) -> GapFeatures
extract_spoof_features(track, vessel_context) -> SpoofFeatures
extract_rendezvous_features(track_a, track_b, context) -> RendezvousFeatures
extract_loiter_features(track, aoi_context) -> LoiterFeatures
```

The live monitor can keep state, but evaluation must replay identical inputs without live timing/thread dependencies.

## Task P2.2 — score current detector behaviour

Modify `core/intel/alert_recognition_scorer.py` so:

- `ais_behaviour.jsonl` is scored;
- `ais_integrity.jsonl` is scored;
- every class reports precision/recall/F1/FP/FN;
- unscored rows are zero at the Phase exit gate.

## Task P2.3 — coverage-aware gap baseline

Replace class blacklist logic with `CoverageBaseline` inputs.

Features should include at minimum:

```text
silent_seconds
previous_message_density
receiver/source availability
jamming_score
coast_distance
port_or_anchorage proximity
traffic density
previous SOG/COG
expected reporting profile
last-known receiver/source mix
```

Vessel class may modify expectation, but must not be a hard exemption.

## Task P2.4 — spoofing/integrity separation

Separate:

```text
position_integrity_anomaly
identity_integrity_anomaly
behavioural_anomaly
official_sanctions_fact
```

A duplicate MMSI is an identity-integrity problem, not automatically a sanctions event.

---

# 7. P3 — durable Maritime evidence model

**Priority:** after P2 metrics exist.

**Exit gate:** new Maritime observations/features/episodes/hypotheses persist outside `IntelEventDB.meta`, can be replayed/rebuilt, and project back into the current Live envelope.

## Task P3.1 — schema + Alembic migration

Create ORM models for:

- `VesselSubjectDB`
- `MaritimeObservationDB`
- `BehaviourFeatureDB`
- `MaritimeEpisodeDB`
- `InvestigationHypothesisDB`
- `EvidenceLinkDB`
- `CoverageBaselineDB`

Migration requirements:

- additive first;
- reversible;
- PostgreSQL production and SQLite test compatibility;
- indices for subject/time/type/state;
- no destructive migration until dual-write comparison passes.

## Task P3.2 — observation ingestion adapters

Current producers write immutable observations first.

Examples:

```text
AIS nav status → MaritimeObservation
AIS track gap → BehaviourFeature derived from observations
Rendezvous geometry → BehaviourFeature
Official sanctions row → MaritimeObservation(type=official_designation)
Sentinel/GFW detection → MaritimeObservation(type=sar_detection)
```

## Task P3.3 — compatibility projection

Build one adapter:

```python
project_episode_or_hypothesis_to_intel_event(...)
```

Existing Live/API paths continue functioning while the new evidence model becomes authoritative.

---

# 8. P4 — bounded Maritime episodes and hypotheses

**Priority:** after P3.

**Exit gate:** one MMSI can have multiple separate episodes; a subject is not itself an incident; a hypothesis has explicit evidence/counter-evidence and lifecycle.

## Task P4.1 — stable subject identity

Create `VesselSubject` records keyed independently from an episode.

Track dated aliases:

- MMSI;
- IMO;
- name;
- flag;
- source;
- valid-from/to where known.

Do not overwrite identity history in place.

## Task P4.2 — episode segmentation

Replace `coalesce_security_vessel_episodes()` as the semantic episode builder.

Episode boundaries use:

- time gap;
- behavioural reset;
- geographic separation;
- state transition;
- encounter counterpart change;
- hypothesis lifecycle.

Example: a vessel may have a gap Monday, a normal transit Tuesday and a separate rendezvous Friday. Those are three episodes, not one ever-growing MMSI dossier.

## Task P4.3 — evidence-gated hypothesis engine

A hypothesis must contain:

```text
hypothesis_type
state
evidence_stage
reason_codes
supporting_evidence_ids
contradicting_evidence_ids
counter_indicators
reviewer
reviewed_at
publication_decision
```

No direct detector may mark itself `published`.

## Task P4.4 — hypothesis-specific gates

### `covert_rendezvous`

Require more than proximity/dwell. Consider:

- offshore encounter geometry;
- duration and relative speed;
- course alignment;
- vessel roles;
- pre/post AIS gaps;
- repeated pattern;
- draught changes where available;
- official sanctions context;
- satellite association.

### `position_spoofing`

Require reproducible impossible movement / duplicate-location / GNSS-integrity evidence, with coverage/jamming counter-indicators.

### `sanctions_evasion_pattern`

Official sanctions fact alone is not an evasion hypothesis. Require movement/identity/encounter evidence plus review.

### `infrastructure_pattern`

Cable/pipeline proximity is context. Require repeated/dwell/anomaly/corroborating evidence before investigation-state escalation.

---

# 9. P5 — cross-sensor evidence

**Priority:** after bounded episodes/hypotheses exist.

## Task P5.1 — time-aligned Sentinel association

Association must compare at image acquisition time.

For each AIS subject:

1. propagate/interpolate AIS state to acquisition timestamp;
2. carry kinematic and receiver uncertainty;
3. compare SAR candidate distance;
4. include candidate size/heading if available;
5. preserve unmatched candidates;
6. never force one-to-one attribution when multiple candidates fit.

Output:

```text
candidate_id
acquired_at
predicted_subject_position
prediction_uncertainty_m
candidate_position
association_distance_m
association_score
association_status=candidate|plausible|reviewed_match|rejected
```

## Task P5.2 — isolate heavy SAR worker

The API process must not load heavy raster/detection models.

Use a bounded job path with:

- explicit memory gate;
- one concurrent heavy job on ARM unless benchmark proves otherwise;
- timeout;
- failure state;
- provenance/version metadata;
- no API outage when satellite processing fails.

## Task P5.3 — licensing enforcement

Persist source licence class in every cross-sensor observation.

Do not expose a GFW-derived commercial feature unless the deployment has a compatible licence flag.

---

# 10. P6 — public and analyst presentation

**Priority:** after evidence model produces stable data.

## Task P6.1 — one disclosure policy

Every frontend identifier render must call the same policy.

```text
public Humanitarian
  no MMSI / IMO / MarineTraffic / professional dossier

public Maritime
  neutral vessel identifier may appear only where product policy permits
  never present identity as allegation

analyst Maritime
  full dated identity/evidence dossier
```

## Task P6.2 — evidence-first panel

Replace category prose with:

```text
Observation
Derived features
Assessment
Evidence level
Supporting evidence
Counter-indicators
Caveats
Source provenance
Episode window
Hypothesis state (if any)
Review/publication status
```

## Task P6.3 — unknown fails closed

Frontend must not invent semantic categories:

- no `Other signal` as a meaningful public category;
- no `Other vessel` analytical row;
- unknown/unclassified remains internal or receives a neutral “Unclassified context” treatment only where explicitly allowed.

## Task P6.4 — Safety as its own product surface

Maritime Safety should be visible without appearing in Security/Intelligence.

Examples:

- NUC;
- aground;
- restricted manoeuvrability;
- navwarnings;
- distress beacons where relevant.

Safety uses neutral operational language and direct source evidence.

---

# 11. P7 — production verification and cleanup

**Priority:** release gate.

## Task P7.1 — full regression matrix

Required suites:

```text
backend full pytest
ruff
web lint
typecheck
web unit tests
live simulation tests
live API tests
map tests
vite production build
edge parity tests
Alembic upgrade from production-like snapshot
```

## Task P7.2 — runtime acceptance tests

Verify against current production-like data:

### Humanitarian

- active Alarm Phone maritime point appears once;
- translated repost updates same incident;
- region-only shows area/no fake point;
- land event shows Humanitarian marker/no drift;
- resolved/archived lifecycle behaves according to the final operator policy;
- no Humanitarian MMSI/IMO disclosure;
- drift uses event observation time and canonical gate.

### Maritime Safety

- NUC is Safety, not Intelligence;
- restricted manoeuvrability is Safety;
- aground is Safety;
- no Safety cargo Drift;
- return to normal AIS status resolves the Safety episode;
- EventAssessment reaches the UI.

### Maritime Intelligence

- neutral rendezvous is not sanctions by default;
- ordinary coverage loss does not automatically become dark activity;
- duplicate MMSI stays identity-integrity unless other evidence exists;
- infrastructure proximity alone is context;
- sanctions-list match is presented as an official-list fact, not automatic evasion;
- hypothesis publication requires evidence gate + review.

## Task P7.3 — historical data migration/backfill

After new semantics are stable:

- classify historical Safety events with service/lane;
- remove legacy Drift eligibility from Safety records;
- convert legacy rendezvous `sanctions` tagging to neutral observations where no sanctions evidence existed;
- preserve audit history of original values;
- do not silently rewrite forensic log entries.

## Task P7.4 — severity decommission stage 2

Only after all readers/writers are audited:

- remove severity from routing decisions;
- remove severity from publication decisions;
- remove severity-driven presentation;
- retain temporary compatibility serialization if old consumers still require it;
- then use a reversible Alembic migration to remove obsolete DB field only when zero active readers depend on it.

---

# 12. Test and evaluation policy

This policy applies to every future detector/classifier PR.

1. Add/identify failing fixture first.
2. Measure baseline before changing logic.
3. Make the smallest semantic change.
4. Re-run the target scorer.
5. Run full regression suite.
6. Report precision/recall/F1 and exact FP/FN IDs.
7. Do not claim an improvement when the test corpus only changed to match the implementation.
8. Synthetic examples remain valid regression fixtures, but production-quality claims require sanitized real-world examples.
9. Stateful detectors must expose deterministic replayable feature/classification functions for evaluation.
10. Any public-allegation rule needs explicit hard negatives representing routine/benign behaviour.

---

# 13. Required PR order

Do not implement later architecture before earlier semantic violations are closed.

Recommended sequence:

```text
PR A — P0.1 canonical service/lane routing
PR B — P0.2 remove legacy Safety Drift resurrection
PR C — P0.3 wire EventAssessment backend→Live→UI
PR D — P0.4 neutral rendezvous semantics
PR E — P0.5 identity/vessel-class presentation cleanup
PR F — P0.6 darkship cue endpoint + wording + association metadata
PR G — P1 HumanitarianAssessment + expanded corpus
PR H — P2 replayable AIS feature extraction + scorer
PR I — P2 coverage-aware gap/integrity baseline
PR J — P3 durable evidence schema + dual write
PR K — P4 bounded episode builder
PR L — P4 hypothesis lifecycle/publication gate
PR M — P5 cross-sensor association
PR N — P6 evidence-first UI/disclosure policy
PR O — P7 production migration/verification
```

Each PR must be reviewable independently and preserve `main` green.

---

# 14. Stop conditions for autonomous agents

An autonomous agent must stop and report instead of improvising when:

- a change would weaken Humanitarian privacy;
- a change would allow Safety to create Drift;
- a rule would publicly imply sanctions/evasion/interference from one heuristic observation;
- a migration would rewrite forensic history destructively;
- a source licence/terms decision is unknown;
- production data is needed to establish a threshold but is not available;
- a supposedly equivalent VM/edge path produces different classifications;
- tests show a regression in the stabilized Alarm Phone OCR/Drift pipeline;
- a new ML/heavy dependency would materially exceed the ARM VM resource target.

Do not “solve” these by adding a permissive fallback. Unknown and unresolved states fail closed.

---

# 15. Definition of the next stable SeaCommons release

The next stable milestone is reached only when all of the following are true:

- Humanitarian recognition is measured on a materially expanded corpus, not only the original synthetic baseline.
- `service/lane` is authoritative across producer, DB projection, feed, edge and UI.
- Maritime Safety is visible as Safety and cannot become cargo Drift or Security through a legacy fallback.
- EventAssessment is actually visible in the Live/analyst panel.
- AIS behaviour/integrity fixtures are scored, not marked `NOT YET SCORED`.
- AIS gap detection is coverage-aware rather than class-blacklist-driven.
- rendezvous is a neutral observation until independent evidence supports a hypothesis.
- one MMSI no longer equals one indefinite security episode.
- identity anomaly is separated from official sanctions designation.
- infrastructure proximity is context, not implied sabotage/interference.
- darkship/SAR association uses acquisition-time geometry and candidate wording.
- observations, derived features, episodes and hypotheses are durably distinguishable.
- public Maritime hypotheses require review/evidence gates.
- Public Humanitarian identity/privacy invariants remain intact.
- VM and edge are contract-parity tested.
- full backend/web/build/migration/runtime acceptance gates are green.

Until those conditions hold, SeaCommons should describe Maritime Intelligence outputs as **observations, derived features, candidates and reviewable hypotheses**, not as confirmed suspicious activity.
