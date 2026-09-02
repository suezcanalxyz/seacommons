# SeaCommons Maritime OSINT Evidence Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** turn SeaCommons Maritime from a feed of loosely classified AIS events into a selective, explainable OSINT instrument for investigating suspicious vessel-movement episodes, while preserving the stabilized Humanitarian pipeline.

**Architecture:** retain raw source observations, derive reproducible behavioural features, correlate them into vessel or vessel-pair episodes, and open an investigative hypothesis only when explicit evidence gates are met. Maritime Safety remains inside the Maritime service but is kept separate from Maritime Intelligence; a self-reported navigational status is never sufficient evidence of suspicious intent.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy/Alembic, PostgreSQL in production, SQLite-compatible unit tests, existing AIS track store, Shapely, HTTPX, React/Vite/MapLibre, Copernicus Data Space STAC/Sentinel-1, optional isolated satellite worker. PostGIS is considered only after a separate deployment benchmark; it is not required by this plan.

**Spec:** this document; `docs/COMPARTMENTS.md`; `docs/OSINT_FUSION.md`; `docs/SECURITY_MODEL.md`; ADR-0002 and ADR-0003.

**Audited baseline:** `main` at `d412e927e1ee87a722acfbfedef719e23bd08700` on 2026-09-02.

## Global Constraints

- Preserve AGPL-3.0-or-later, forensic/cryptographic logging and source provenance.
- Preserve the canonical Humanitarian flow: `SOURCE → OBSERVATION → INCIDENT → GEO EVIDENCE → SEA/LAND CLASSIFICATION → PUBLICATION DECISION → HUMANITARIAN-ONLY DRIFT ELIGIBILITY → PUBLIC LIVE CONTRACT → LIVE UI`.
- Never merge observations directly into incidents without an explicit correlation record.
- Never infer `humanitarian`, `safety`, `security`, `sanctions` or public eligibility by fallback/complement; unknown values fail closed.
- `not_under_command` belongs to `service=maritime`, `lane=safety`; it is not a Maritime Intelligence hypothesis and is not cargo Drift eligible.
- Vessel class is context, never a public investigation category. Remove `Pleasure craft`, `Other vessel`, `Cargo`, `Fishing` and equivalent buckets from case taxonomy.
- A rendezvous is not a sanctions event. An AIS gap is not proof of intentional disabling. A SAR detection without an AIS match is a candidate, not a confirmed dark vessel.
- Public allegations require human review unless they are a direct official-list match or a neutral safety observation.
- Public Humanitarian views never expose raw MMSI/IMO, embedded vessel trackers or a standalone professional-vessel-identity block.
- Preserve explicit prohibitions on migrant interception, border-enforcement integration, military targeting and commercial surveillance aggregation.
- Production target remains the current ARM VM with 12 GB RAM. Heavy SAR inference must be optional, bounded and isolated from the API process.
- No production dependency may rely on scraping websites or violating source terms. Every connector records its licence class and attribution requirements.
- GFW APIs are research/benchmark-only unless SeaCommons obtains a compatible commercial licence.
- OpenSanctions is optional enrichment and requires a business licence for commercial use; official OFAC/EU/UN sources remain canonical.

---

# 1. Current-state audit

The earlier roadmap correctly focused on Alarm Phone OCR, Humanitarian Drift safety, lifecycle, durable storage and VM/edge parity. Those changes landed before or in `d412e927` and remain mandatory regressions. The current release problem is different: Maritime promotes low-level AIS states and heuristic detections into user-facing cases before sufficient evidence exists.

## 1.1 Humanitarian regressions to preserve

- disputed OCR cannot originate Drift;
- a real OCR point is not hidden behind a stale region polygon;
- land/region-only observations cannot originate maritime Drift;
- translated Alarm Phone posts update one incident;
- VM and edge expose identical public semantics;
- stale/offline NGO vessels do not appear as live positions;
- map padding accounts for both panels;
- WebSocket/edge updates refresh marker and card without reload;
- correlated observations do not create duplicate cards;
- media ingestion remains allowlisted, SSRF-safe, bounded and durable;
- exact coordinates retain uncertainty and review state;
- production bootstrap verifies Alembic availability and schema head.

## 1.2 Confirmed Maritime defects

| ID | Code evidence | Why it is wrong | Required outcome |
|---|---|---|---|
| M-01 | `apps/api/core/mda/watch.py::_emit_rendezvous()` writes `maritime_domain="sanctions"` for every pair | legitimate STS/proximity is not sanctions evasion | neutral encounter observation; hypothesis only after correlation |
| M-02 | `scan_gaps()` starts at one hour and suppresses pleasure, passenger, fishing and tug classes | coverage/context matter more than class blacklists | evaluate every class against a coverage baseline |
| M-03 | `scan_spoofing()` repeats class exemptions | normal movement and spoofing are conflated | class/AOI baseline plus preserved reason features |
| M-04 | `apps/api/core/intel/vessel_incident_monitor.py` maps NUC to `grey_zone` and `drift_eligible=True` | status 2 is a safety report, not suspicious intent/cargo drift | Maritime Safety; no hypothesis; no Drift |
| M-05 | `apps/api/core/live/vessel_episodes.py` groups all vessel signals by MMSI into one security episode | subject identity is not an episode boundary | stable subject plus bounded episodes |
| M-06 | `ConePanel.jsx::shipTypeLabel()` falls back to `Other vessel` and displays `Pleasure craft` | vessel type is presented as an analytical result | show hypothesis and evidence; type only as context |
| M-07 | `ConePanel.jsx` can render MMSI and MarineTraffic links in public report flows | residual identity block violates privacy/product intent | one disclosure policy before every identifier render |
| M-08 | `darkship_cue.py` calls an unmatched GFW target “likely the dark vessel” | a growing reachable area cannot establish attribution | time-aligned association and candidate wording |
| M-09 | `darkship_cue.py` calls the deprecated Copernicus STAC endpoint | contract will degrade or fail | use `https://stac.dataspace.copernicus.eu/v1/` |
| M-10 | `apps/web/src/features/intel/categories.js` retains generic `other` fallbacks | unknown becomes visible semantics | internal `unclassified`; public fail-closed |
| M-11 | `/api/v1/vessels/nearest` has no freshness/radius gate | distant/stale vessels look relevant | required distance and age limits |
| M-12 | identity anomalies/duplicate MMSI enter sanctions-oriented domains | identity inconsistency is not a designation | separate identity integrity from sanctions |

---

# 2. Maritime OSINT research translated into rules

## 2.1 Operational conclusions

1. **AIS is incomplete self-reported telemetry.** Store raw status, destination and draught with timestamps; never translate one field directly into intent.
2. **Gaps must be coverage-aware.** Evaluate receiver availability, preceding message density, coast distance, congestion, jamming, source mix and expected reporting behaviour.
3. **STS is a sequence.** Correlate approach, sustained low relative speed, aligned headings, geography, vessel roles, draught changes, gaps, identity history and satellite evidence.
4. **Anomaly is contextual deviation.** Global speed/course/duration thresholds fail in ports, anchorages, fishing grounds, TSS and service areas.
5. **SAR matching is acquisition-time matching.** Propagate AIS positions to the exact image time and retain uncertainty before assigning detections.
6. **Language follows evidence.** Use `observed`, `derived`, `corroborated`, `assessed`; reserve `confirmed` for authoritative/documentary confirmation.
7. **Review is part of the engine.** Reviewed episodes form the calibration corpus; machine ranking cannot publish an allegation.

## 2.2 Source/licensing matrix

| Source | Use | Decision |
|---|---|---|
| Existing AISStream ingestion | live observations and own coverage history | production after current terms are recorded |
| Global Fishing Watch Events/SAR | benchmark gaps, encounters and SAR candidates | CC BY-NC; research only without written commercial licence |
| Copernicus Data Space Sentinel-1 | scene discovery and SAR vessel detection | production-capable open data with quotas/attribution |
| xView3 | detector evaluation and fixtures | R&D baseline; verify model/code licences separately |
| Official OFAC, EU and UN lists | designated-vessel/entity facts | canonical production sources |
| OpenSanctions maritime | entity-resolution accelerator | optional licensed adapter for commercial use |
| Equasis / PSC portals | ship/company/safety verification | manual analyst links; no scraping |
| IHO S-124 / NAVAREA-NAVTEX | active navigation warnings | Maritime Safety context and detector counter-evidence |
| EMODnet Human Activities | ports, density, cables, pipelines, installations | AOI baseline and infrastructure context |
| Copernicus Marine/weather | currents, waves, wind | context only; never evidence of intent |

## 2.3 Primary references

- USCG NAVCEN AIS Class A status fields: <https://www.navcen.uscg.gov/ais-class-a-reports>
- Price Cap Coalition AIS/STS recommendations: <https://home.treasury.gov/news/press-releases/jy1797>
- OFAC maritime guidance: <https://ofac.treasury.gov/media/37751/download>
- GFW Events API: <https://globalfishingwatch.org/our-apis/documentation/docs/v3/events>
- GFW data caveats and coverage-aware gap rules: <https://api-doc.globalfishingwatch.org/our-apis/documentation/docs/v3/general-api-doc/data-caveats>
- GFW licence and rate limits: <https://globalfishingwatch.org/our-apis/documentation/docs/license-rate-limits>
- Copernicus current STAC API: <https://documentation.dataspace.copernicus.eu/APIs/STAC.html>
- Copernicus open/downstream use: <https://www.copernicus.eu/en/terms-use/how-access-data>
- Copernicus Sentinel-1 products: <https://documentation.dataspace.copernicus.eu/Data/Sentinel1.html>
- xView3 dark-vessel SAR challenge: <https://iuu.xview.us/>
- EMSA Integrated Maritime Services: <https://emsa.europa.eu/we-do/digitalisation/maritime-monitoring.html>
- EMSA CleanSeaNet cross-sensor pattern: <https://www.emsa.europa.eu/csn-menu.html>
- IHO S-124 navigational warnings: <https://registry.iho.int/productspec/view.do?category=product_ID&domainS=ALL&idx=218&product_ID=S-124&statusS=5>
- EMODnet Human Activities: <https://www.emodnet-humanactivities.eu/>
- MovingPandas trajectory primitives: <https://movingpandas.org/>
- AIS anomaly-detection review: <https://doi.org/10.3390/jmse11051010>

---

# 3. Target product model

## 3.1 Service taxonomy

```text
service=humanitarian
  lane=distress | missing | interception | pushback | resolution | land_humanitarian

service=maritime
  lane=safety
    not_under_command | aground | restricted_manoeuvrability | navwarning
  lane=intelligence
    dark_transit | concealed_port_call | covert_rendezvous
    identity_deception | position_spoofing | route_deception
    sanctions_evasion_pattern | infrastructure_pattern
  lane=environmental
    pollution_candidate | pollution_confirmed
```

`service` chooses the product surface. `lane` chooses workflow. `observation_type` states what was received. `hypothesis_type` states what is being investigated. `vessel_type` remains descriptive context only. `maritime_domain` survives during migration but cannot remain the sole routing field.

## 3.2 Evidence ladder

| Stage | Meaning | Public rule |
|---|---|---|
| `observed` | direct source/sensor fact | neutral wording |
| `derived` | reproducible calculation | internal/review by default |
| `corroborated` | independent sources/modalities agree | review-ready |
| `assessed` | recorded analyst judgement | publishable with caveats |
| `confirmed` | authoritative/documentary confirmation | publishable with source |

No external severity score. Internal prioritisation uses explicit reason codes, counter-indicators and evidence completeness.

## 3.3 Durable entities

```text
VesselSubject          stable subject_id plus dated aliases
MaritimeObservation    immutable sourced fact, geometry and uncertainty
BehaviourFeature       algorithm/version/parameters plus input ids
MaritimeEpisode        bounded window with one or more subjects
InvestigationHypothesis type, state, evidence stage, reasons/counter-indicators
EvidenceLink           typed graph edge between records
CoverageBaseline       AOI/time/source/profile reception expectations
```

`IntelEventDB` remains the compatibility/public projection envelope. New entities must not be flattened into JSON metadata before persistence.

## 3.4 Hypothesis lifecycle

```text
candidate → collecting → review_ready → assessed → published
    └──────────────→ rejected / expired
```

Every transition records actor, timestamp, reason and evidence snapshot hash. New evidence updates the episode/hypothesis rather than creating another public marker.

## 3.5 Publication gate

```python
def may_publish_maritime_hypothesis(hypothesis) -> bool:
    if hypothesis.state not in {"assessed", "published"}:
        return False
    if hypothesis.evidence_stage not in {"corroborated", "assessed", "confirmed"}:
        return False
    if not hypothesis.reason_codes or not hypothesis.evidence_links:
        return False
    if hypothesis.has_unresolved_identity_conflict:
        return False
    return True
```

An official sanctions match may publish as a list fact without implying deceptive behaviour. A sanctions-evasion hypothesis still requires movement evidence and review.

---

# 4. Phased implementation

## Phase 0 — immediate semantic correctness

**Exit gate:** Live distinguishes Humanitarian, Maritime Safety and Maritime Intelligence; no raw MMSI block remains in public Humanitarian; NUC/rendezvous no longer imply Intelligence/sanctions.

### Task 0.1: Explicit service/lane routing

**Files:**
- Create: `apps/api/core/intel/service_taxonomy.py`
- Modify: `apps/api/core/intel/public_policy.py`
- Modify: `apps/api/core/live/feed.py`
- Modify: `apps/api/core/live/projection.py`
- Create: `tests/test_service_taxonomy.py`
- Test: `tests/test_live_compartments.py`

**Produces:** `classify_service(event) -> ServiceClassification(service, lane, publishable, reason)`.

- [ ] Write table-driven failing tests for every service/lane and unknown fail-closed behaviour.
- [ ] Implement frozen string enums and one classifier.
- [ ] Replace complement/fallback classification in policy and feed projection.
- [ ] Run `python -m pytest -q tests/test_service_taxonomy.py tests/test_live_compartments.py tests/test_public_policy.py`.
- [ ] Commit `fix(taxonomy): separate maritime safety from intelligence`.

### Task 0.2: Reclassify navigational incidents

**Files:**
- Modify: `apps/api/core/intel/vessel_incident_monitor.py`
- Modify: `apps/api/core/live/vessel_episodes.py`
- Modify: `apps/web/src/features/intel/categories.js`
- Test: `tests/test_vessel_incidents.py`
- Test: `tests/test_live_vessel_episodes.py`

```python
assert event.metadata["service"] == "maritime"
assert event.metadata["lane"] == "safety"
assert event.metadata["drift_eligible"] is False
assert event.metadata.get("hypothesis_type") is None
```

- [ ] Make the current NUC test fail against `grey_zone + drift_eligible`.
- [ ] Map NUC/aground/restricted manoeuvrability to Maritime Safety.
- [ ] Keep AIS-SART/MOB/EPIRB in Humanitarian distress.
- [ ] Stop Safety observations from creating security episodes.
- [ ] Run both test files and commit `fix(maritime): keep navigation status in safety lane`.

### Task 0.3: Remove residual MMSI/type presentation

**Files:**
- Create: `apps/web/src/features/live/identityDisclosure.js`
- Create: `apps/web/src/features/live/identityDisclosure.test.js`
- Modify: `apps/web/src/components/ConePanel.jsx`
- Modify: `apps/web/src/features/live/eventPresentation.js`
- Modify: `apps/web/src/features/intel/categories.js`

**Produces:** `identityDisclosurePolicy(properties, publicMode)`.

```text
public Humanitarian: no MMSI, IMO, MarineTraffic embed/link or dossier
public Maritime: identifier may appear as cited evidence, not category/title
analyst Maritime: full dated identity dossier
unknown vessel type: omit row; never “Other vessel”
```

- [ ] Test Alarm Phone with linked MMSI and unknown vessel type.
- [ ] Route every identity render through the helper.
- [ ] Remove `Other vessel`/`Pleasure craft` from case labels.
- [ ] Run `cd apps/web && npm test && npm run build`.
- [ ] Commit `fix(web): enforce identity disclosure and remove vessel buckets`.

### Task 0.4: Neutralise current MDA claims

**Files:**
- Modify: `apps/api/core/mda/watch.py`
- Modify: `apps/web/src/features/intel/mdaCategories.js`
- Test: `tests/test_mda_watch.py`

- [ ] Rendezvous expects `observation_type=close_approach`, no sanctions domain/public publication.
- [ ] Duplicate MMSI expects `identity_integrity`, not sanctions.
- [ ] Replace asserted actions with neutral observation labels.
- [ ] Keep `unclassified` internal and emit a taxonomy metric.
- [ ] Run MDA/identity tests and commit `fix(mda): keep single-signal detections neutral`.

### Task 0.5: Fail closed on source licences

**Files:**
- Modify: `apps/api/core/config.py`
- Modify: `apps/api/core/intel/gfw_monitor.py`
- Modify: `apps/api/core/mda/darkship_cue.py`
- Modify: `.env.example`
- Create: `tests/test_source_runtime_policy.py`

- [ ] Add an explicit `SEACOMMONS_DEPLOYMENT_PURPOSE=public_interest|commercial` setting with no permissive unknown fallback.
- [ ] In commercial mode, disable GFW runtime requests unless a configured licence record explicitly permits them.
- [ ] Keep GFW fixture comparisons available in tests/research mode with required attribution metadata.
- [ ] Make the source-disabled state visible in diagnostics instead of returning an apparent empty dataset.
- [ ] Commit `fix(sources): fail closed on noncommercial runtime data`.

## Phase 1 — Observation, Episode and Hypothesis persistence

**Exit gate:** one subject can have multiple bounded episodes; provenance survives restart and projection.

### Task 1.1: Schema and models

**Files:**
- Create: `apps/api/core/db/migrations/versions/0005_maritime_evidence_engine.py`
- Modify: `apps/api/core/db/models.py`
- Create: `apps/api/core/mda/models.py`
- Test: `tests/test_alembic_migrations.py`
- Create: `tests/test_maritime_models.py`

**Tables:** `maritime_subjects`, `maritime_subject_aliases`, `maritime_observations`, `maritime_features`, `maritime_episodes`, `maritime_episode_subjects`, `maritime_hypotheses`, `maritime_evidence_links`, `coverage_baselines`.

- [ ] Test upgrade/downgrade, uniqueness, timezone-aware timestamps and immutability.
- [ ] Store algorithm/version/parameters/input ids for derived features.
- [ ] Index subject-time, episode-relation, state-update and AOI baseline lookups.
- [ ] Run migration/model/schema tests.
- [ ] Commit `feat(mda): persist observations episodes and hypotheses`.

### Task 1.2: Repository and provenance

**Files:**
- Create: `apps/api/core/mda/repository.py`
- Create: `apps/api/core/mda/provenance.py`
- Create: `tests/test_mda_repository.py`
- Create: `tests/test_mda_provenance.py`

**Interfaces:**

```python
record_observation(input: ObservationInput) -> MaritimeObservation
record_feature(input: FeatureInput) -> BehaviourFeature
upsert_episode(key: EpisodeKey, evidence_ids: list[str]) -> MaritimeEpisode
transition_hypothesis(id, target_state, actor, reason) -> InvestigationHypothesis
```

- [ ] Test source-id/hash idempotency and immutability.
- [ ] Bind features to algorithm and input hashes.
- [ ] Append state transitions to the forensic chain.
- [ ] Commit `feat(mda): add auditable evidence repository`.

### Task 1.3: Replace MMSI-only coalescing

**Files:**
- Create: `apps/api/core/mda/episode_builder.py`
- Modify: `apps/api/core/live/vessel_episodes.py`
- Create: `tests/test_mda_episode_builder.py`
- Modify: `tests/test_live_vessel_episodes.py`

- [ ] Key single-vessel episodes by subject + kind + bounded window.
- [ ] Key pair episodes by sorted subjects + kind + bounded window.
- [ ] Test NUC then unrelated gap as two episodes.
- [ ] Test repeat scans update one episode.
- [ ] Project only reviewable/published hypotheses.
- [ ] Commit `refactor(mda): build bounded evidence episodes`.

## Phase 2 — AIS quality and contextual baselines

**Exit gate:** gaps/movements are judged against source, AOI, time and operational context without class blacklists.

### Task 2.1: Receiver/source coverage

**Files:**
- Modify: `apps/api/core/vessels/track_store.py`
- Modify: `apps/api/core/vessels/aisstream.py`
- Create: `apps/api/core/mda/coverage.py`
- Create: `tests/test_mda_coverage.py`
- Modify: `tests/test_track_store.py`

```text
source_id, cell_id, hour_bucket
unique_vessels, message_count, median_interval_s
expected_messages, coverage_ratio, source_mode
congestion_indicator, jamming_context, sample_size
```

- [ ] Test healthy, low-coverage and congested coastal cells.
- [ ] Record asynchronously without blocking ingestion.
- [ ] Add bounded daily aggregation/retention.
- [ ] Commit `feat(ais): learn reception coverage baselines`.

### Task 2.2: Behavioural baselines

**Files:**
- Create: `apps/api/core/mda/baselines.py`
- Create: `apps/api/core/mda/trajectory_features.py`
- Create: `tests/test_mda_baselines.py`
- Create: `tests/test_mda_trajectory_features.py`

Minimum features: speed quantiles, stop duration, course-change rate, route-corridor distance, port/anchorage proximity, relative speed/heading, message interval and draught change.

- [ ] Use robust medians/quantiles; no ML dependency.
- [ ] Separate by AOI, operational context and broad vessel profile.
- [ ] Return `insufficient_baseline` instead of guessing.
- [ ] Version baseline/training interval.
- [ ] Commit `feat(mda): add contextual trajectory baselines`.

### Task 2.3: Replace vessel-type early returns

**Files:**
- Modify: `apps/api/core/mda/watch.py`
- Modify: `tests/test_mda_watch.py`

- [ ] Convert pleasure/ferry/fishing/tug exclusions to counter-indicators.
- [ ] Prove a normal anchored small craft stays closed because context fits.
- [ ] Prove the same class remains analysable with sufficient evidence.
- [ ] Commit `refactor(mda): evaluate behaviour instead of vessel class`.

## Phase 3 — evidence-gated hypotheses

**Exit gate:** detectors produce observations/features; only the hypothesis engine creates reviewable cases.

### Task 3.1: Coverage-aware dark transit

**Files:**
- Create: `apps/api/core/mda/detectors/gap.py`
- Create: `apps/api/core/mda/hypotheses/dark_transit.py`
- Modify: `apps/api/core/mda/watch.py`
- Create: `tests/test_mda_gap_detector.py`
- Create: `tests/test_mda_dark_transit_hypothesis.py`

Positive reasons: healthy coverage, underway state, sufficient prior messages, route-sensitive context, unexplained reappearance, route discontinuity, independent SAR candidate.

Counter-indicators: poor coverage, congestion, jamming, port arrival, class-B cadence, safety explanation, insufficient history.

- [ ] Record analytical gaps as internal observations.
- [ ] Open `dark_transit` only after counter-indicators.
- [ ] Reserve intentional-disabling language for assessment.
- [ ] Commit `feat(mda): detect coverage-aware dark transit`.

### Task 3.2: Covert rendezvous / possible STS

**Files:**
- Create: `apps/api/core/mda/detectors/encounter.py`
- Create: `apps/api/core/mda/hypotheses/covert_rendezvous.py`
- Create: `tests/test_mda_encounter_detector.py`
- Create: `tests/test_mda_covert_rendezvous.py`

Features: minimum separation, duration, relative speed, heading alignment, paired track shape, port/anchorage context, role compatibility, draught delta, adjacent gaps and official identity context.

- [ ] Normal port meeting remains an observation.
- [ ] Offshore tanker pair does not automatically become sanctions.
- [ ] `sanctions_evasion_pattern` requires official match plus behaviour.
- [ ] Keep `possible STS` until visual/documentary confirmation.
- [ ] Commit `feat(mda): correlate covert rendezvous evidence`.

### Task 3.3: Identity/position deception

**Files:**
- Create: `apps/api/core/mda/hypotheses/identity_deception.py`
- Modify: `apps/api/core/mda/identity.py`
- Modify: `apps/api/core/mda/watch.py`
- Modify: `tests/test_mda_identity.py`
- Create: `tests/test_mda_identity_deception.py`

- [ ] Separate integrity observations from deception hypotheses.
- [ ] Require temporal overlap and source provenance for duplicate MMSI.
- [ ] Preserve dated aliases instead of overwriting identity.
- [ ] Correlate impossible kinematics, IMO/MID conflicts, static-data churn and official matches.
- [ ] Commit `feat(mda): build dated vessel identity evidence`.

### Task 3.4: Concealed port call and route deception

**Files:**
- Create: `apps/api/core/mda/detectors/port_call.py`
- Create: `apps/api/core/mda/detectors/route_deviation.py`
- Create: `apps/api/core/mda/hypotheses/concealed_port_call.py`
- Create: `tests/test_mda_concealed_port_call.py`
- Create: `tests/test_mda_route_deviation.py`

- [ ] Detect entry/stop/exit separately with confidence.
- [ ] Correlate gaps near approaches and changed draught/destination.
- [ ] Compare route with learned corridor.
- [ ] Treat weather diversion and safety events as counter-indicators.
- [ ] Commit `feat(mda): detect concealed port calls and route deviation`.

### Task 3.5: Infrastructure pattern

**Files:**
- Create: `apps/api/core/mda/hypotheses/infrastructure_pattern.py`
- Modify: `apps/api/core/mda/reference.py`
- Modify: `tests/test_mda_reference.py`
- Create: `tests/test_mda_infrastructure_pattern.py`

- [ ] Compare repeated pass/dwell with local density and route baselines.
- [ ] Use work warnings and authorised service roles as counter-evidence.
- [ ] Require recurrence or independent evidence before review.
- [ ] Never equate proximity with interference/surveillance/sabotage.
- [ ] Commit `feat(mda): assess repeated infrastructure activity`.

## Phase 4 — source governance and authoritative enrichment

**Exit gate:** every external fact has origin, retrieval time, version, licence and staleness; no scraping/non-commercial production dependency.

### Task 4.1: Connector licence gate

**Files:**
- Create: `apps/api/core/intel/source_licensing.py`
- Modify: `apps/api/core/intel/source_registry.py`
- Modify: `.env.example`
- Modify: `docs/CONFIGURATION.md`
- Create: `tests/test_source_licensing.py`

```text
licence_class = official_open | open_attribution | noncommercial | licensed | manual_only
runtime_role = production | research | benchmark | analyst_link
```

- [ ] Reject production connectors marked non-commercial without a licence record.
- [ ] Add attribution/freshness to enrichment payloads.
- [ ] Mark GFW research/benchmark by default.
- [ ] Mark Equasis/PSC manual-only absent an authorised API.
- [ ] Commit `feat(sources): enforce maritime data licence policy`.

### Task 4.2: Official sanctions evidence

**Files:**
- Create: `apps/api/core/mda/sources/ofac.py`
- Create: `apps/api/core/mda/sources/eu_sanctions.py`
- Create: `apps/api/core/mda/sources/un_sanctions.py`
- Modify: `apps/api/core/mda/identity.py`
- Create: `tests/test_mda_official_sanctions.py`

- [ ] Store source record id, list version/retrieval time, identifiers and official URL.
- [ ] Match IMO exactly before fuzzy names; name alone cannot auto-confirm.
- [ ] Distinguish designated vessel, owner/operator match and association.
- [ ] Keep OpenSanctions behind optional licensed adapter.
- [ ] Commit `feat(mda): ingest official vessel sanctions evidence`.

### Task 4.3: Navigation/geographic context

**Files:**
- Create: `apps/api/core/mda/sources/navwarnings.py`
- Modify: `apps/api/core/mda/reference.py`
- Modify: `apps/api/core/mda/jamming.py`
- Create: `tests/test_mda_navwarnings.py`
- Modify: `tests/test_mda_reference.py`

- [ ] Normalize S-124-compatible ids, validity and geometry when available.
- [ ] Version EMODnet ports/density/cables/pipelines/installations.
- [ ] Label bundled fallback geometry approximate and dated.
- [ ] Use warnings/works/jamming as context, not accusations.
- [ ] Commit `feat(mda): add versioned navigation context`.

## Phase 5 — Sentinel-1 cross-sensor pilot

**Exit gate:** selected episodes can request scenes, run bounded detection and associate candidates without blocking the API.

### Task 5.1: Correct scene discovery

**Files:**
- Create: `apps/api/core/satellite/copernicus_stac.py`
- Modify: `apps/api/core/mda/darkship_cue.py`
- Create: `tests/test_copernicus_stac.py`
- Modify: `tests/test_mda_darkship_cue.py`

- [ ] Use `https://stac.dataspace.copernicus.eu/v1/`.
- [ ] Filter AOI, acquisition interval, collection, GRD and polarisation.
- [ ] Store item id, acquisition time, orbit, footprint and query.
- [ ] Remove unsupported hard-coded next-pass claims.
- [ ] Commit `fix(satellite): use current Copernicus STAC contract`.

### Task 5.2: Isolated detection worker

**Files:**
- Create: `apps/api/core/satellite/jobs.py`
- Create: `apps/api/core/satellite/worker_main.py`
- Create: `apps/api/core/satellite/detector_contract.py`
- Create: `tests/test_satellite_jobs.py`
- Create: `tests/test_detector_contract.py`
- Create: `deploy/systemd/seacommons-satellite-worker.service`

Resource policy: one active job, bounded queue, AOI/download ceilings, timeout, separate process/container, API healthy when worker absent.

- [ ] Define detector-neutral JSON contract.
- [ ] Add fixture detector for CI and separately configured xView3-compatible implementation.
- [ ] Record model version/hash, preprocessing, threshold and environment.
- [ ] Keep PyTorch out of the core API image.
- [ ] Commit `feat(satellite): add bounded SAR detection worker`.

### Task 5.3: Time-aligned AIS–SAR association

**Files:**
- Create: `apps/api/core/satellite/association.py`
- Modify: `apps/api/core/mda/darkship_cue.py`
- Create: `tests/test_ais_sar_association.py`

- [ ] Propagate AIS to exact image acquisition time.
- [ ] Include time gap, motion/environment uncertainty.
- [ ] Resolve one-to-one matches deterministically; retain ambiguity.
- [ ] Label unmatched targets `unmatched_sar_candidate`.
- [ ] Commit `feat(satellite): correlate SAR detections with AIS uncertainty`.

## Phase 6 — analyst-first Maritime UI

**Exit gate:** Maritime shows a small explainable investigation queue, not every AIS state.

### Task 6.1: Investigation queue

**Files:**
- Create: `apps/web/src/features/maritime/hypothesisPresentation.js`
- Create: `apps/web/src/features/maritime/hypothesisPresentation.test.js`
- Modify: `apps/web/src/components/IntelDashboard.jsx`
- Modify: `apps/web/src/components/ConePanel.jsx`
- Modify: `apps/web/src/features/intel/categories.js`

- [ ] Group as Collecting, Ready for review, Assessed, Published, Rejected/expired.
- [ ] Remove source-channel and vessel-class case buckets.
- [ ] Show hypothesis type, interval, subjects, evidence stage and reason count.
- [ ] Keep Safety in its own Maritime lane.
- [ ] Commit `refactor(web): make maritime an investigation queue`.

### Task 6.2: Evidence/counter-evidence panel

**Files:**
- Create: `apps/web/src/components/MaritimeEvidencePanel.jsx`
- Create: `apps/web/src/components/MaritimeEvidencePanel.test.jsx`
- Modify: `apps/web/src/components/ConePanel.jsx`

- [ ] Visually separate observed AIS from modelled movement.
- [ ] Show source, time, algorithm, uncertainty and attribution.
- [ ] Show counter-indicators beside supporting reasons.
- [ ] Replace “AIS movement reconstruction” with `Observed AIS track` and `Modelled reachable area`.
- [ ] Limit coordinate precision to evidence uncertainty.
- [ ] Commit `feat(web): expose maritime evidence provenance`.

### Task 6.3: Reviewed publication workflow

**Files:**
- Create: `apps/api/core/api/routes/maritime_investigations.py`
- Modify: `apps/api/core/intel/public_policy.py`
- Modify: `apps/api/core/live/projection.py`
- Create: `tests/test_maritime_investigation_routes.py`
- Modify: `tests/test_live_contracts.py`

- [ ] Require authenticated actor/reason for assess, reject and publish.
- [ ] Persist reviewed evidence snapshot hash.
- [ ] Separate neutral public copy from analyst notes.
- [ ] Reopen review on material contradictory evidence without erasing history.
- [ ] Commit `feat(mda): add reviewed publication workflow`.

### Task 6.4: Nearest-vessel relevance

**Files:**
- Modify: `apps/api/core/api/routes/vessels.py`
- Modify: `apps/web/src/components/ConePanel.jsx`
- Create: `tests/test_nearest_vessels.py`

- [ ] Require/use `radius_nm` and `max_age_minutes`.
- [ ] Exclude stale/outside-radius records.
- [ ] Return coverage timestamp and applied filters.
- [ ] Show “No recent AIS vessel within X nm” with thresholds.
- [ ] Commit `fix(vessels): bound nearest context by distance and freshness`.

## Phase 7 — migration, calibration and production proof

**Exit gate:** legacy rows are classified/quarantined, false positives measured, CI green and a real-world smoke documented.

### Task 7.1: Legacy quarantine

**Files:**
- Create: `apps/api/core/mda/backfill_evidence_engine.py`
- Create: `tests/test_mda_backfill.py`
- Modify: `docs/LEGACY.MD`

- [ ] Dry-run counts by old type/domain/anomaly with deterministic disposition.
- [ ] Convert raw signals to observations; do not manufacture historical hypotheses.
- [ ] Quarantine unknown/`other`, false sanctions-rendezvous and ambiguous identity rows.
- [ ] Never rewrite Humanitarian incidents through Maritime migration.
- [ ] Commit `migrate(mda): quarantine legacy maritime classifications`.

### Task 7.2: Reviewed calibration corpus

**Files:**
- Create: `tests/fixtures/mda_calibration/manifest.json`
- Create: `apps/api/core/mda/calibration.py`
- Create: `tests/test_mda_calibration.py`

Corpus: normal port/anchorage; fishing/working/tug; receiver outage; jamming; genuine NUC; candidate dark transit; candidate STS; duplicate MMSI; SAR ambiguity; infrastructure service work.

- [ ] Store only redistributable/synthetic fixtures in git.
- [ ] Record label, reviewer, sources, expected output and uncertainty.
- [ ] Report precision by hypothesis and false positives per 1,000 vessel-hours.
- [ ] Block threshold promotion below documented sample minimum.
- [ ] Commit `test(mda): add reviewed maritime calibration corpus`.

### Task 7.3: Observability/resource budgets

**Files:**
- Modify: `apps/api/core/observability.py`
- Modify: `docs/PRODUCTION_RUNBOOK.md`
- Create: `tests/test_mda_observability.py`

Metrics: observations/minute; episodes by state; hypotheses opened/rejected/published; detector latency; coverage quality; unknown taxonomy; stale enrichment; licence blocks; SAR queue/runtime/failures; reviewer false positives.

- [ ] Use cardinality-safe labels.
- [ ] Alert on public unreviewed hypotheses, unknown public taxonomy, production non-commercial connector and satellite-caused API starvation.
- [ ] Document CPU/RAM/disk budgets for ARM 12 GB.
- [ ] Commit `ops(mda): monitor evidence quality and resource budgets`.

### Task 7.4: Full release gate

```bash
python -m pytest -q
python -m ruff check . --output-format=github
cd apps/edge && npm test
cd ../web && npm test
npm run build
```

- [ ] Alembic production schema is at head.
- [ ] Fixture E2E covers observation → feature → episode → hypothesis → review → public projection.
- [ ] Real Maritime smoke is reviewed without publishing an unverified allegation.
- [ ] Genuine NUC appears only in Maritime Safety and has no cargo Drift.
- [ ] Ordinary rendezvous remains a neutral observation.
- [ ] Humanitarian Alarm Phone exposes no MMSI/IMO/tracker block.
- [ ] VM and edge return identical public ids/semantics.
- [ ] API remains responsive during a satellite job.
- [ ] Rollback preserves immutable evidence.

Final release commit: `release: maritime evidence engine phase 1`.

---

# 5. Commit order

| Order | Boundary | Result |
|---:|---|---|
| 1 | taxonomy + Safety correction | NUC leaves Intelligence/Drift |
| 2 | disclosure + UI buckets | MMSI block/type categories removed |
| 3 | neutral MDA output | rendezvous/identity no longer imply sanctions |
| 4 | evidence schema/repository | durable observations/hypotheses |
| 5 | episode builder | bounded episodes |
| 6 | coverage/behaviour baselines | contextual AIS quality |
| 7 | dark transit | coverage-aware gaps |
| 8 | rendezvous | evidence-gated possible STS |
| 9 | identity/route/infrastructure | remaining hypotheses |
| 10 | source governance/lists | licensable enrichment |
| 11 | Sentinel discovery/worker | bounded cross-sensor input |
| 12 | AIS–SAR association | auditable candidates |
| 13 | analyst queue/evidence UI | explainable workflow |
| 14 | publication workflow | controlled public output |
| 15 | backfill/calibration/observability | measurable release proof |

Do not implement all phases in one branch. Phase 0 is release-blocking. Phases 1–3 are the first Maritime Evidence Engine milestone. Phases 4–5 follow source/licence review. Phase 6 depends on stable API contracts. Phase 7 closes the release.

---

# 6. Definition of done

```text
NUC is Maritime Safety, not Humanitarian or Intelligence.
NUC cannot originate cargo Drift.
Public Humanitarian renders no MMSI/IMO/tracker block.
Vessel type is context, never a case category.
Unknown/other never becomes a public fallback.
Rendezvous is not automatically sanctions-related.
Gap detection uses coverage/context, not class blacklists.
Modelled movement is separate from observed AIS.
Every hypothesis exposes evidence and counter-indicators.
Every public behavioural allegation has analyst review.
Official sanctions facts remain distinct from evasion hypotheses.
GFW cannot silently become a commercial production dependency.
Satellite jobs cannot exhaust/block the ARM API VM.
Humanitarian regressions and VM/edge parity remain green.
```

Success is not alert volume. It is a smaller reviewable queue where every episode explains relevance, contradictory evidence, uncertainty and the next verification action.
