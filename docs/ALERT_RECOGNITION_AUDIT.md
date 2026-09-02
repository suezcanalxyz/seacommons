# Alert recognition & interpretation audit

> **Status:** baseline trace of SeaCommons alert recognition, classification,
> publication and interpretation as it stands on `main` at `d412e92`, written
> before any threshold change (per `docs/prompt.md` Phase 0). Companion to
> `docs/ALARM_PHONE_IMAGE_PIPELINE_AUDIT.md` (image side) and
> `docs/COMPARTMENTS.md` (domain model).

## 0. Objectives (from the prompt)

1. Replace generic per-type "Interpretation" text with case-specific,
   evidence-based interpretation.
2. Humanitarian Recognition V2 — a real extraction pipeline, not more regexes.
3. Restore **AIS nav status 2 / not_under_command** to public Live as
   *safety context*, not a distress alert and not operator-only.
4. Re-audit and recalibrate AIS spike / anomaly detection and taxonomy.

---

## 1. Decision pipeline trace

### 1.1 Alarm Phone distress report

```
twikit tweet → TwikitMonitor._ingest
  → is_direct_distress_call(caption+quote)           geoextract.py
  → humanitarian_case_metadata()                     humanitarian.py  (_PEOPLE regex, _case_type)
  → coordinate: text → OCR → relative → place → area
  → IntelEvent(type="twitter", severity=classify_severity(),
       metadata: is_distress, publication_status="published" if distress,
                 maritime_domain implicit via IntelEvent.maritime_domain(),
                 humanitarian_case_type, coordinate_review_status, …)
  → intel_store.add(dedup_key="x:<id>")
  → public feed: public_signal_collection(mode)      core/live/feed.py
       → compartment_for_domain(event.maritime_domain())   public_policy.py
       → _public_intel_feature(event, allowed_domains)      projection.py
       → lifecycle.distress_lifecycle()                     lifecycle.py
       → visual_category_fields()                           visual_category.py
  → frontend: classifyEventVisual() → colour; ConePanel → "Interpretation"
```

### 1.2 AIS nav status 2 (not_under_command)

```
aisstream PositionReport → VesselIncidentMonitor.on_position     vessel_incident_monitor.py
  → _INCIDENT_STATUS[2] = ("not_under_command","medium",
                           is_distress=False, auto_publish=False,
                           min_reports=3, min_span_s=600)
  → sustained (≥3 reports AND ≥600 s) → _emit
  → IntelEvent(type="vessel_incident", severity="medium",
       metadata: publication_status="internal",     ← operator-only
                 maritime_domain="grey_zone",        ← ★ misclassified
                 verification_status="ais_transponder",
                 is_distress=False,
                 ais_nav_status_kind="not_under_command",
                 drift_eligible=True, drift_vessel_type="cargo")
  → public feed: compartment_for_domain("grey_zone") → "security"
       → appears only in mode=security, NOT humanitarian
       → _public_intel_feature also gates on publication_status → "internal" drops it
```

**Net:** nav status 2 is invisible on Humanitarian Live and only reaches
Security Live if an operator publishes it. The prompt wants it visible as
**safety context** in Humanitarian mode with an explicit caveat.

### 1.3 AIS nav status 6 (aground)

```
_INCIDENT_STATUS[6] = ("aground","high", is_distress=True, auto_publish=True, 2, 180)
  → IntelEvent(type="distress", maritime_domain="safety", publication_status="published")
  → compartment_for_domain("safety") → None  ← ★ dropped from BOTH modes
```

Aground is auto-published as a distress but its domain (`safety`) has **no
compartment**, so `public_signal_collection` skips it at
`if event_mode is None: continue`. A published distress that never appears.

### 1.4 AIS spike rules — `AISSpikeDetector._scan` (ais_spike_detector.py)

| Rule | Fires when | Confidence | Publication |
| --- | --- | --- | --- |
| `sudden_stop` | `prev.speed ≥ 3.0` and `cur.speed ≤ 0.4` and not in a `PORT_ZONES` bbox | severity `high` if in `SAR_HOTSPOTS` or NGO, else `medium` | `type="ais_spike"` → `_to_intel_event`? no — `IntelEvent(type="ais_spike")` added directly; `ais_spike` is **not** in `_PUBLIC_DURABLE_TYPES` nor a public compartment → operator-only |
| `vessel_loiter` | stopped (`≤0.4 kn`) outside port for `≥ LOITER_MIN_S` (45 min) **and** in a hotspot | `medium` | operator-only |
| `ngo_search_pattern` | known NGO, `bearing Δ ≥ 60°` at `0.4–5 kn`, **or** `_ngo_circular_pattern` ring fit | `high` | operator-only |
| `rescue_cluster` | ≥2 vessels within `3.0 nm`, at least one NGO/CG | `critical` if hotspot else `high` | operator-only |

All four, if within 30 nm of an active distress, get `possible_response_to`
metadata and severity bumped to `critical` (non-causal framing — correct).

### 1.5 AIS anomaly rules — `AISAnomalyDetector` (anomaly/ais.py)

| Rule | Fires when | Confidence |
| --- | --- | --- |
| `gap` | silence 900 s–6 h, last speed `≥ 1.0 kn`, not in a `_DARK_ZONES` rectangle | `min(0.85, 0.4 + silent_s/7200)` |
| `impossible_speed` | computed kts `> _MAX_SPEED[type]` **and** `> 55` | `min(0.9, 0.5 + …)` |
| `dark_zone_entry` | enters one of 2 hard-coded rectangles | `0.65` |
| `sdn_match` | MMSI in OFAC SDN cache | `0.95` |
| `mmsi_duplicate` | *declared in the docstring, not implemented* | — |

All persisted as `type="ais_anomaly"`, `publication_status="internal"`,
`maritime_domain="grey_zone"` (or `sanctions` for SDN).

### 1.6 Interpretation rendering — frontend

```
ConePanel.jsx:
  line 641  non-humanitarian "Why this was flagged":
            props.detection_reason || props.detail || descriptionOf(props.type)
  line 826  "Interpretation" Row:  descriptionOf(props.type)          ← ★ always generic
descriptionOf(type)  → categories.js  → SIGNAL_CATEGORIES[categoryOf(type)].description
  → one fixed string per category. Every "vessel_incident" event shows the
    same sentence; every "ais_spike"/"ais_anomaly" shows the same sentence.
```

`detection_reason` exists for `vessel_incident` (the rule + counts) and for
`ais_anomaly` (a templated sentence), and `detail` exists for `ais_spike`.
But the **"Interpretation" Row** ignores both and uses `descriptionOf`
unconditionally, and none of the three is a structured, evidence-referencing
assessment.

---

## 2. Findings

### 2.1 Generic interpretation

| ID | Finding | Detail |
| --- | --- | --- |
| IN-1 | **`descriptionOf(props.type)` is a category explainer used as the case interpretation** | ConePanel "Interpretation" Row (826) and the non-humanitarian note (641 fallback) render a fixed per-category sentence. Two `not_under_command` events 12 h and 4 reports apart read identically. |
| IN-2 | **No `EventAssessment` structure** | There is no `observation` / `interpretation` / `evidence_level` / `confidence_basis` / `supporting_evidence` / `contradicting_evidence` / `caveats` / `recommended_action` / `rule_ids` model on the backend or a frontend adapter. `detection_reason` (a single string) is the closest artefact. |
| IN-3 | **`detection_reason` is templated, not evidential** | `vessel_incident_monitor._emit` builds `"Flagged after N reports over Ns (rule: …)"`. Good raw material, but it is prose, not fields, and it is not produced for `ais_spike` or Alarm Phone. |
| IN-4 | **Confidence is ad hoc** | `AISAnomalyEvent.confidence` is a per-rule formula; `ais_spike` has only a severity string; Alarm Phone has `verification_level`. No shared, traceable confidence with named components (`source_reliability`, `observation_freshness`, `rule_strength`, `persistence`, `location_precision`, `independent_corroboration`, `coverage_quality`, `context_support`, `contradicting_evidence`). |

### 2.2 Humanitarian recognition

| ID | Finding | Detail |
| --- | --- | --- |
| HR-1 | **`humanitarian.py` is shallow** | `humanitarian_case_metadata` = one `_PEOPLE` regex (single count only) + `_case_type` (a chain of `re.search` over the caption). No separate `aboard` / `rescued` / `missing` / `dead` / `injured` / `children` / `women`. "45 aboard, 12 rescued, 3 missing" → `people_reported = 45`, the rest lost. |
| HR-2 | **`_case_type` order is fragile** | First matching branch wins: `pushback` → `interception` → `missing` → `land` → `resolution` → `rescue_update` → `distress` → `advocacy` → distress-keywords → `unknown`. "rescued but pushback" relies on `pushback` being checked first; "medical emergency during interception" collapses to `interception`. No `shipwreck` / `medical_emergency` / `disembarkation` / `arrival` / `death_report` / `retrospective_incident` as first-class types (the prompt lists them). |
| HR-3 | **No vessel / needs / actors extraction** | `vessel.condition` (engine failure, taking water, capsized, overcrowded), `needs` (rescue, medical, food/water, fuel, disembarkation), `actors` (authorities contacted, rescue actor, interception actor) are not extracted at all. |
| HR-4 | **`rescued` ≠ resolved handled only in `geoextract`** | `_RESOLUTION_OVERRIDE_RE` / `_ONGOING_INCIDENT_PATTERNS` in `geoextract.py` do distinguish "rescued + pushback" from a clean resolution — but only for the lifecycle string, not for a structured `HumanitarianAssessment` with `rescued + denied_disembarkation → lifecycle=ongoing`. |
| HR-5 | **Language coverage partial** | `_PEOPLE` regex covers EN/FR/IT/ES/DE nouns. `_case_type` keywords are English-only (`pushback`, `intercepted`, `missing`, `reception centre`, `rescued`). A French/Italian-only Alarm Phone post mis-types unless an English twin exists. The prompt requires EN/IT/FR deterministic normalisation. |
| HR-6 | **Temporal fields absent** | No `report_time` vs `incident_time` vs `last_contact_time`, no `retrospective` flag. A mourning/anniversary post ("one year ago…") is caught by the `advocacy` keyword branch only. |
| HR-7 | **No evidence spans** | Extracted values keep no source string. F-10 / prompt §9 both require the OCR/text evidence string per extracted value. |

### 2.3 not_under_command / safety context

| ID | Finding | Detail |
| --- | --- | --- |
| NUC-1 | **`maritime_domain="grey_zone"` is wrong** | `vessel_incident_monitor._emit` hard-codes `grey_zone` for `not_under_command`. Grey-zone is a security compartment. Nav status 2 is a *vessel self-report of a manoeuvring limitation* — `safety`, per the prompt. |
| NUC-2 | **`publication_status="internal"`** | Even with the domain fixed, `_public_intel_feature` requires `published` (or a public-eligible type). NUC never reaches any public feed. The prompt wants it visible as context (`kind=context`), not a publish decision. |
| NUC-3 | **`safety` domain has no compartment** | `compartment_for_domain("safety") → None` → `public_signal_collection` drops it (`if event_mode is None: continue`). So even `aground` (published, `safety`) is invisible. Fixing NUC requires routing `safety` + `kind=context` into the humanitarian feed as a distinct, non-distress bucket. |
| NUC-4 | **`drift_eligible=True` for NUC** | `metadata["drift_eligible"] = kind in {"not_under_command","disabled","adrift"}` and `drift_vessel_type="cargo"`. A vessel-status observation should not, on its own, spawn a drift model. The F-01 gate (`is_auto_drift_eligible`) should already reject it (needs checking — it keys on humanitarian evidence), but the flag itself is misleading. |
| NUC-5 | **No GNSS-jamming *promotion* path** | `_emit` reads `jamming.in_jamming_zone` and appends a sentence, but the domain stays `grey_zone` regardless. The prompt wants `safety` by default and `grey_zone` **only** with independent corroboration (jamming, spoofing, impossible movement, infrastructure). Today it is always `grey_zone` and jamming only changes the text. |
| NUC-6 | **Restricted manoeuvrability (nav 3) correctly ignored** | `_INCIDENT_STATUS` has no key 3; docstring explains dredgers/cable-layers. Good — keep, and make the frontend distinguish "restricted manoeuvrability" from "not under command" (partially done in `eventAnomalyLabel`). |
| NUC-7 | **Sustained thresholds reasonable but not evaluated** | `≥3 reports`, `≥600 s`. The prompt says keep initially, make configurable, evaluate from fixtures. Currently module-level constants. |

### 2.4 Live mode policy

| ID | Finding | Detail |
| --- | --- | --- |
| MP-1 | **No single `mode_policy` module** | Eligibility is spread across `public_policy.py` (`compartment_for_domain`, `domains_for_mode`, `SECURITY_MARITIME_DOMAINS`), `feed.py` (`public_signal_collection` bucket logic), `projection.py` (`_public_intel_feature`), `live_edge_publisher.py` (`_edge_humanitarian_eligible`). F-06 unified the *privacy-absolute* checks; the *compartment* logic is still effectively two implementations. |
| MP-2 | **Humanitarian mode has no "safety context" tier** | `public_signal_collection` has `mode_features` (distress) and `mode_context` (news/anomaly/incident) per compartment, but a `safety`-domain vessel incident has `compartment_for_domain → None` and never enters either. There is no "humanitarian primary + relevant maritime safety context" composition as the prompt describes. |
| MP-3 | **`alarmPhoneOnly()` already removed from the browser** (F-06) | `useLiveFeed.js` / `main.jsx` no longer call `alarmPhoneOnly`; the edge path uses `_edge_humanitarian_eligible` (backend). Good — the remaining work is additive (safety context), not removing frontend policy. |
| MP-4 | **VM vs edge parity is by convention** | `live_edge_publisher._edge_humanitarian_eligible` calls `domains_for_mode("humanitarian")` and re-checks `SECURITY_MARITIME_DOMAINS`, mirroring `feed.py` by hand. A shared `mode_policy.eligible_for_mode(event, mode)` used by both removes the divergence risk. Parity tests exist for the privacy rules, not for the safety-context tier (which doesn't exist yet). |

### 2.5 AIS spike detector

| ID | Finding | Detail |
| --- | --- | --- |
| SP-1 | **`rescue_cluster` ignores position freshness** | `_check_clusters(vessels)` — `vessels` is built from `registry.get_geojson()` with no per-vessel `last_seen` age filter. `CLUSTER_AGE_S = 30*60` is defined and **never referenced**. Two vessels whose last fix is hours old and stale can "cluster". |
| SP-2 | **`rescue_cluster` = proximity, not convergence** | The only test is `_haversine_nm ≤ 3.0`. No relative-movement / decreasing-distance / course / time-together / anchorage check. Two NGO vessels moored in Trapani → "rescue cluster, critical". |
| SP-3 | **`sudden_stop` is a one-sample transition** | `prev.speed ≥ 3` → `cur.speed ≤ 0.4`, single poll pair. No nav-status check (anchored / moored), no persistence, no track-displacement, no anchorage bbox (only ~10 `PORT_ZONES` points, radius 2–5 nm — misses roadstead anchorages). A vessel slowing to pick up a pilot, or entering a TSS, fires it. |
| SP-4 | **`vessel_loiter` has no nav-status evidence** | Docstring says "not applicable to anchored vessels (speed < 0.1 for > 6 h)" but the implementation only tracks `loiter_start` from speed; `on_position`'s `nav_status` is available on the AIS feed hook but `AISSpikeDetector` reads the **registry snapshot**, which may not carry nav status. So the anchored-exclusion the docstring promises is not enforced. |
| SP-5 | **`ngo_search_pattern` 2-sample bearing check** | `_bearing_delta(prev.course, cur.course) ≥ 60°` between two 5-min polls. `_ngo_circular_pattern` (track fit) mitigates but only runs at `0.4 < speed ≤ 5` and needs `≥5` fixes in 90 min. A single sharp turn at low speed (avoiding traffic, coming about) still fires the zigzag branch. |
| SP-6 | **Low-confidence results named as conclusions** | `spike_type="rescue_cluster"` regardless of evidence strength; the prompt wants `possible_rescue_cluster` when weak. Same for `sudden_stop` (should be a "cue" not a "high-confidence alert" on one sample). |
| SP-7 | **`ais_spike` not in the public taxonomy** | It is operator-only (not in `_PUBLIC_DURABLE_TYPES`, no compartment). The frontend `SIGNAL_CATEGORIES` folds `ais_spike` + `ais_anomaly` into one "AIS anomaly / spike" row — the prompt wants the subtype shown, never "spike". |

### 2.6 AIS gap / anomaly

| ID | Finding | Detail |
| --- | --- | --- |
| GP-1 | **Gap is silence-only, no coverage health** | `_silence_sweep_loop`: silent 900 s–6 h + last speed ≥ 1 kn + not in a 2-rectangle dark-zone list → `gap`. No comparison against nearby vessels, no `local_reporting_ratio`, no `feed_health`. A feed-wide AISStream reconnect makes *every* underway vessel emit a `gap`. |
| GP-2 | **Dark zones are 2 hard-coded rectangles** | Eastern Med + Libyan coast. Real reception health is dynamic and station-dependent. |
| GP-3 | **`impossible_speed` always uses `default=50`** | `_on_feed_position` passes `vessel_type=""` → `_MAX_SPEED.get("", default=50)`. Type-specific limits are dead code on the live path. And the `> 55` floor means anything 50–55 kts is never flagged regardless of type. |
| GP-4 | **`mmsi_duplicate` unimplemented** | Docstring lists it; no code. Identity/spoofing indicators (duplicate identity) live in `core/mda/watch.py` separately. |
| GP-5 | **No confidence components** | `confidence` is a scalar formula. No `coverage_quality`, `nearby_vessels_reporting_before/after`, `distance_from_known_low_coverage_area`. |

### 2.7 Taxonomy

| ID | Finding | Detail |
| --- | --- | --- |
| TX-1 | **Frontend collapses AIS signals** | `SIGNAL_CATEGORIES` "AIS anomaly / spike" = `['ais_spike','ais_anomaly']`, one colour, one description. The prompt wants: (1) AIS vessel status `vessel_incident`, (2) AIS behavioural cue `ais_spike`, (3) AIS integrity/signal anomaly `ais_anomaly`, (4) fused `correlated_alert`, (5) verified/direct humanitarian. `EVENT_VISUAL_CATEGORIES` (the newer `visual_category` taxonomy) is closer — it has `navigation_casualty` / `spoofing` / `ais_gap` / `loitering` / `rendezvous` — but the OSINT `SIGNAL_CATEGORIES` legend/panel still uses the flat one. |
| TX-2 | **"spike" surfaces as the human-facing word** | `eventAnomalyLabel` maps some subtypes; `ais_spike` title is `f"AIS: {spike_type.replace('_',' ').title()}"` → "AIS: Sudden Stop" (ok) but the legend row is "AIS anomaly / spike". |

### 2.8 Evaluation

| ID | Finding | Detail |
| --- | --- | --- |
| EV-1 | **No recognition corpus** | No `tests/fixtures/alert_recognition/*.jsonl`. `tests/test_ais_spike_detector.py`, `test_ais_anomaly.py`, `test_humanitarian_model.py` are unit tests over synthetic inputs, not a labelled precision/recall corpus with hard negatives ("SOS MEDITERRANEE annual report" ≠ distress; "moored in Valletta" ≠ sudden-stop; feed-wide outage ≠ N vessel gaps). |
| EV-2 | **No shadow-mode harness** | No `ALERT_RECOGNITION_V2` / `ALERT_RECOGNITION_V2_SHADOW` flags, no V1/V2 disagreement metrics. `config.py` has the image V2 flags only. |

---

## 3. Root causes (the prompt's Phase 13 questions)

1. **Generic Interpretation** → `ConePanel` "Interpretation" Row calls
   `descriptionOf(props.type)`, a per-*category* explainer, with no
   case-specific assessment layer to call instead. `detection_reason` /
   `detail` exist for some types but are prose, not structured evidence, and
   the Row does not even use them.

2. **Humanitarian mode behaviour** → historically `alarmPhoneOnly()` in the
   browser + edge (now removed from the browser, F-06). The *remaining*
   cause: `public_signal_collection` composes only `distress` + `context`
   per compartment and `compartment_for_domain` returns `None` for `safety`,
   so there is no "humanitarian primary + maritime safety context" tier.

3. **Missing not_under_command on Live** → `vessel_incident_monitor._emit`
   sets `maritime_domain="grey_zone"` (→ security compartment) **and**
   `publication_status="internal"`. Both must change: domain → `safety`,
   and the feed must carry `safety` + `kind=context` in humanitarian mode.

4. **AIS spike false-positive risk** → single-sample rules (`sudden_stop`),
   proximity-as-convergence (`rescue_cluster`), unused freshness constant
   (`CLUSTER_AGE_S`), registry snapshot without nav-status
   (`vessel_loiter` anchored-exclusion not enforced), silence-only gap with
   no coverage-health comparison.

---

## 4. Proposed taxonomy

Public human-facing category (drop "spike" as a label):

```
vessel_status        AIS navigational status the vessel itself broadcast
  · not_under_command   "Unable to manoeuvre — AIS reported"      domain=safety, kind=context
  · aground             "Aground — AIS reported"                  domain=safety, kind=context
  · distress_beacon     "Distress beacon"                         domain=sar,    kind=distress
behavioural_cue      a motion pattern inferred from the track (lower confidence)
  · sudden_stop / possible_sudden_stop
  · loitering / abnormal_dwell
  · possible_rescue_cluster        (rescue_cluster only with convergence proof)
  · ngo_search_pattern
signal_anomaly       AIS transponder/reception integrity
  · ais_gap  (vessel) | coverage_gap (feed/area)   ← must be distinguished
  · impossible_speed
  · dark_zone_entry
  · identity_anomaly (mmsi/imo/flag mismatch, duplicate identity)
fused_alert          correlated_alert (multi-source agreement)
direct_humanitarian  distress / humanitarian incident (Alarm Phone, IOM, partner)
```

Backend: extend `core/domain/live_contracts.py` enums; keep
`visual_category.py` (already close). Frontend: split `SIGNAL_CATEGORIES`
"AIS anomaly / spike" into `vessel_status` / `behavioural_cue` /
`signal_anomaly`; UI shows the subtype, never "spike".

---

## 5. Proposed schemas

### `EventAssessment` — `core/intel/assessment.py` (new)

```
observation: str                 # what was measured, with the numbers
interpretation: str              # what it means, evidence-referenced, caveated
evidence_level: Literal["single_observation","sustained_observation",
                        "multi_source","corroborated"]
confidence: float                # 0..1 from confidence_components
confidence_components: dict[str,float]
supporting_evidence: list[str]
contradicting_evidence: list[str]
caveats: list[str]
recommended_action: str | None
rule_ids: list[str]
classification_version: str
```

Built per event type by small pure functions (`assess_not_under_command`,
`assess_sudden_stop`, `assess_rescue_cluster`, `assess_ais_gap`,
`assess_humanitarian`). `descriptionOf()` stays as the *category* explainer;
the frontend renders `EventAssessment.interpretation` for the case.

### `HumanitarianAssessment` — `core/intel/humanitarian_recognition.py` (new)

```
incident_type: distress|shipwreck|missing_persons|interception|pushback
              |medical_emergency|rescue|disembarkation|arrival|death_report
              |retrospective_incident|humanitarian_update
lifecycle: active|ongoing|needs_review|resolved|concluded
people: {aboard,rescued,missing,dead,injured,children,women,approximate}  # each with raw span
vessel: {type,condition,engine_failure,taking_water,capsized,overcrowded}
needs: [rescue,medical,food_water,fuel,disembarkation]
actors: {reporting_source,authorities_contacted[],rescue_actor,interception_actor}
location: {source,precision,uncertainty,explicit_vs_inferred}
temporal: {report_time,incident_time,last_contact_time,retrospective}
evidence: {source_type,direct_report,corroborating_sources,confidence,uncertainty_reasons[]}
```

Deterministic EN/IT/FR normalisation first (number words, per-language
keyword tables). `rescued` never auto-sets `resolved` when
`denied_disembarkation` / `pushback_risk` / `still_missing` present.

### Confidence model — `core/intel/confidence.py` (extend)

`core/intel/confidence.py` already exists (159 lines) — extend it with the
named dimensions: `source_reliability`, `observation_freshness`,
`rule_strength`, `persistence`, `location_precision`,
`independent_corroboration`, `coverage_quality`, `context_support`,
`contradicting_evidence`. Store `confidence`, `confidence_components`,
`rule_id`, `classification_version` on every alert.

---

## 6. Files to change

| File | Change |
| --- | --- |
| `core/intel/assessment.py` *(new)* | `EventAssessment` + per-type `assess_*` |
| `core/intel/humanitarian_recognition.py` *(new)* | `HumanitarianAssessment`, EN/IT/FR extractors |
| `core/intel/humanitarian.py` | `humanitarian_case_metadata` delegates to V2 (behind flag), keeps back-compat keys |
| `core/intel/confidence.py` | named confidence dimensions + `ConfidenceComponents` |
| `core/live/mode_policy.py` *(new)* | `eligible_for_mode(event, mode)` + `SAFETY_CONTEXT_DOMAINS`; used by `feed.py` **and** `live_edge_publisher.py` |
| `core/live/feed.py` | add a `safety_context` bucket to humanitarian mode composition |
| `core/intel/public_policy.py` | `compartment_for_domain` / `domains_for_mode` learn `safety` as context (not a primary compartment) |
| `core/intel/vessel_incident_monitor.py` | NUC domain `grey_zone → safety`; `kind=context`; promote to `grey_zone` only with corroboration; drop `drift_eligible` for bare NUC; emit `EventAssessment` |
| `core/intel/ais_spike_detector.py` | enforce `CLUSTER_AGE_S` freshness; convergence test; `sudden_stop` → cue + persistence; `vessel_loiter` nav-status; rename weak `rescue_cluster` → `possible_rescue_cluster` |
| `core/anomaly/ais.py` | coverage-aware gap (`coverage_gap` vs `vessel_gap`); type-aware `impossible_speed`; confidence components |
| `core/domain/live_contracts.py` | taxonomy enums (`vessel_status` / `behavioural_cue` / `signal_anomaly`) |
| `core/domain/visual_category.py` | map new subtypes → existing visual categories |
| `core/config.py` | `ALERT_RECOGNITION_V2`, `ALERT_RECOGNITION_V2_SHADOW`, NUC/spike thresholds |
| `apps/web/src/features/intel/categories.js` | split "AIS anomaly / spike"; subtype labels |
| `apps/web/src/components/ConePanel.jsx` | render `EventAssessment` (observation / interpretation / evidence / caveats); keep `descriptionOf` as the category note |
| `tests/fixtures/alert_recognition/*.jsonl` *(new)* | humanitarian / ais_status / ais_behaviour / ais_integrity + hard negatives |
| `tests/test_assessment.py`, `test_humanitarian_recognition.py`, `test_mode_policy.py`, `test_alert_recognition_corpus.py` *(new)* | |

---

## 7. Evaluation corpus

`tests/fixtures/alert_recognition/`:

```
humanitarian.jsonl     distress / shipwreck / missing / interception / pushback
                       / medical / rescue / disembarkation / arrival / death /
                       retrospective / advocacy(negative)
ais_status.jsonl       nav 2 sustained / nav 2 brief / nav 3 dredger(negative)
                       / nav 6 aground / beacon
ais_behaviour.jsonl    sudden_stop real / pilot-boarding(negative) / moored(negative)
                       / rescue_cluster converging / NGO in port(negative)
                       / ngo_search real / single turn(negative)
ais_integrity.jsonl    vessel gap (neighbours healthy) / feed-wide outage(→coverage_gap)
                       / impossible_speed / dark_zone_entry
```

Each row: `input`, `expected_classification`, `expected_lifecycle`,
`expected_entities`, `expected_publication`, `expected_confidence_range`,
`notes`. Metrics per class: precision / recall / F1 / FP count / FN count.
Auto-public decisions optimise **precision**. No improvement claimed without
corpus evidence.

---

## 8. Ordered PR plan

| PR | Title | Risk |
| --- | --- | --- |
| 1 | `test(recognition): alert-recognition evaluation corpus + runner` | none |
| 2 | `feat(intel): EventAssessment + per-type assess_* functions` | low (additive metadata) |
| 3 | `feat(web): render EventAssessment; keep descriptionOf as category note` | low |
| 4 | `feat(intel): HumanitarianAssessment V2 (EN/IT/FR), behind ALERT_RECOGNITION_V2` | medium (shadow first) |
| 5 | `feat(live): canonical mode_policy shared by VM + edge; safety-context tier` | medium (adds features to humanitarian mode) |
| 6 | `fix(intel): restore not_under_command as safety context (domain=safety, kind=context)` | medium (new public content — precision-gated) |
| 7 | `refactor(taxonomy): split AIS vessel-status / behavioural-cue / signal-anomaly` | low (labels) |
| 8 | `fix(ais-spike): rescue_cluster freshness + convergence; weak → possible_*` | medium |
| 9 | `fix(ais-spike): sudden_stop → cue + persistence; vessel_loiter nav-status` | medium |
| 10 | `fix(ais-anomaly): coverage-aware gap detection (vessel_gap vs coverage_gap)` | medium |
| 11 | `feat(intel): traceable confidence model (named components) on every alert` | low |
| 12 | `feat(recognition): ALERT_RECOGNITION_V2 shadow-mode metrics + cutover` | gated on corpus |

Optional LLM second-stage (`docs/prompt.md` Phase 10) is **not** in this
plan — deterministic corpus must exist and pass first; it would be a later,
separate, abstention-capable, never-auto-publish addition.

### Implementation progress

| PR | State |
| --- | --- |
| 1 — evaluation corpus + runner | *this branch* — landed. `tests/fixtures/alert_recognition/{humanitarian,ais_status,ais_behaviour,ais_integrity}.jsonl` (labelled `input` / `expected` classification, lifecycle, entities, publication, confidence range, notes; hard negatives and contrastive negatives in every file) + `tests/fixtures/alert_recognition/__init__.py` (`load_corpus`, `score` → per-class precision/recall/F1/FP/FN + publication/lifecycle/confidence accuracy, `run` to score any classifier). No classifier wired yet — that is PR 2+. |
| 2 — `EventAssessment` + `assess_*` | *this branch* — landed. `core/intel/assessment.py`: `EventAssessment` (observation / interpretation / evidence_level / confidence + components / supporting + contradicting evidence / caveats / recommended_action / rule_ids / classification_version) plus pure `assess_not_under_command`, `assess_sudden_stop`, `assess_rescue_cluster`, `assess_ais_gap`, `assess_humanitarian` and an `assess(kind, facts)` dispatcher. Each interpretation is built from the event's own numbers — two same-type events with different evidence read differently. Not yet wired into the detectors (PRs 6/8/9/10) or the panel (PR 3). |
| 3 — web render `EventAssessment` | *this branch* — landed. `eventPresentation.assessmentView(properties)` normalizes `properties.event_assessment` (or returns `null`); `normalize.js` carries it across the edge transport. `ConePanel` renders the case observation / interpretation / caveats / contradicting evidence / recommended action / evidence level / confidence from the assessment when present, and keeps `descriptionOf(props.type)` only as a small "Category" note; it falls back to the old static behaviour when no assessment is attached. |
| 4 — `HumanitarianAssessment` V2 | *this branch* — landed. `core/intel/humanitarian_recognition.py`: `recognize(text, source=…)` → `HumanitarianAssessment` (incident_type over the finite 13-value set, lifecycle, per-role people counts with raw spans via `image_text_fields`, vessel condition, needs, actors, temporal, evidence, publication, confidence), deterministic EN/IT/FR. `lifecycle` never collapses "rescued" → "resolved" when the same text says people are still missing or were denied disembarkation (→ `needs_review`). Scores macro-F1 ≈ 0.96 on `humanitarian.jsonl`. `humanitarian.humanitarian_case_metadata` gained a config-gated overlay: `ALERT_RECOGNITION_V2_SHADOW` attaches `humanitarian_recognition_shadow` (V2 assessment + V1/V2 delta) and changes nothing; `ALERT_RECOGNITION_V2` additionally lets V2 own `humanitarian_case_type` / `humanitarian_incident_type` while every legacy key stays. Both flags default off. |
| 5 — canonical `mode_policy` + safety-context tier | *this branch* — landed. `core/live/mode_policy.py`: `mode_for_event`, `is_safety_context`, `eligible_for_mode`, `SAFETY_CONTEXT_DOMAINS`. `feed.py` and `live_edge_publisher._edge_humanitarian_eligible` both call it — the edge no longer re-implements the compartment check. A `safety`-domain event (a vessel's own AIS self-report) now reaches Humanitarian Live as a distinct non-distress bucket (`kind=context`, `safety_context: true`), never the pulsing distress marker and never the security feed. `compartment_for_domain` stays pure (`None` for `safety`); `mode_policy` is the layer that adds the safety-context routing. Parity test asserts VM and edge agree per domain. NUC still emits `grey_zone` until PR 6. |
| 6 — restore `not_under_command` as safety context | *this branch* — landed. `IntelEvent.maritime_domain()` no longer forces `grey_zone` for a vessel-mobility incident: it returns `safety` by default and `grey_zone` only when `_has_security_corroboration()` (GNSS jamming / spoofing / impossible movement / infrastructure). `vessel_incident_monitor._emit` sets `maritime_domain=safety` (grey_zone only in a jamming zone), `kind=context`, drops `drift_eligible` for bare NUC, and attaches the `assess_not_under_command` EventAssessment. `projection` gives a legacy NUC fusion alert a drift contract only when corroborated. With PR 5's routing a sustained NUC now appears in Humanitarian Live as non-distress safety context, never security, never a drift cone. |
| 7 — split AIS taxonomy | *this branch* — landed. Frontend `SIGNAL_CATEGORIES` "AIS anomaly / spike" is split into `behavioural_cue` ("AIS behavioural cue" — `ais_spike`), `signal_anomaly` ("AIS signal anomaly" — `ais_anomaly`) and `incident` relabelled "AIS vessel status"; `main.jsx` toggles updated. `eventAnomalyLabel` names every subtype (sudden stop / loitering / search pattern / vessel cluster / AIS coverage outage / impossible speed / …) — the word "spike" never reaches the UI. New `aisTaxonomyGroup(type)` helper. Backend: `AisTaxonomyGroup` enum + `ais_taxonomy_group()` in `live_contracts.py`; `visual_category` maps `sudden_stop` → `loitering`. Web lint/typecheck/build and both suites green. |
| 8 — `rescue_cluster` freshness + convergence | *this branch* — landed. `_check_clusters` now: (1) drops vessels whose `last_seen` is missing or older than `CLUSTER_AGE_S` — the previously-unused freshness constant is enforced (SP-1); (2) measures convergence — the group's mean pairwise distance must fall by ≥ `CLUSTER_CONVERGENCE_NM` scan-over-scan (a previous-position snapshot taken before the state-update loop) — proximity alone is no longer called a cluster (SP-2); (3) emits `rescue_cluster` only when fresh **and** converging **and** under way **and** not in a port/anchorage **and** (in a hotspot or near an active distress); everything weaker is `possible_rescue_cluster` at `medium` severity (SP-6). Metadata carries `converging`, `closing_nm`, `positions_max_age_s`, `in_port_or_anchorage`, `near_active_distress`, plus the `assess_rescue_cluster` EventAssessment. Centroid position instead of the first vessel's. |
| 9 — `sudden_stop` → cue + persistence; `vessel_loiter` nav-status | *this branch* — landed. A single-sample `was_underway → now_stopped` transition emits `possible_sudden_stop` (a `medium` cue), never `sudden_stop`; it is promoted to `sudden_stop` only once the stop has held `AIS_SUDDEN_STOP_MIN_SAMPLES` scans **and** `AIS_SUDDEN_STOP_PERSISTENCE_S` seconds without the vessel moving > `_STOP_SETTLE_DISPLACEMENT_NM` off its stop point (both config-tunable) — with the `assess_sudden_stop` EventAssessment and `stop_samples` / `stop_persistence_s` / `stop_displacement_nm` metadata (SP-6). `sudden_stop` and `vessel_loiter` are both suppressed outright when the vessel's own AIS nav status is anchored / moored / aground (`{1, 5, 6}`); when nav status is absent the loiter still emits but is marked `nav_status_known: false` in metadata and text (SP-3). Nav status now flows end-to-end: new nullable `vessels.nav_status` column (PRAGMA-guarded `ALTER TABLE` migration for existing SQLite DBs), `registry.upsert(nav_status=…)`, GeoJSON `properties.nav_status`, and `aisstream` passes `PositionReport.NavigationalStatus` through. Also fixed GP-3's latent key mismatch — the detector read `properties.last_speed` / `last_course`, which `registry.get_geojson` never emitted (it emits `speed` / `course`), so in production every speed was `0` and `sudden_stop` / `ngo_search_pattern` never fired while `vessel_loiter` over-fired; the snapshot now accepts either key. `tests/test_ais_spike_detector.py` (+6: cue vs promotion, anchored/​moored exclusion, nav-status-unknown loiter), `tests/test_vessel_registry.py` (new: nav_status round-trip, COALESCE, legacy-DB migration). Backend suite green (688 passed). |
| 10 — coverage-aware gap | pending |
| 10 — coverage-aware gap | pending |
| 11 — traceable confidence model on every alert | pending |
| 12 — `ALERT_RECOGNITION_V2` shadow-mode + cutover | gated on corpus |

---

## 9. Invariants

- NUC / aground / loiter / sudden_stop → **never** rendered as red
  humanitarian distress; `is_distress` stays `False`.
- A vessel self-report (AIS nav status) is context, never confirmation of
  mechanical failure or intent — every interpretation carries that caveat.
- Proximity is never called convergence / response / rescue without
  corroboration.
- A feed-wide reception outage never becomes N vessel-specific gaps.
- Security content (sanctions / grey-zone / IUU / smuggling / piracy) never
  enters Humanitarian mode by default.
- VM Live and Edge Live resolve mode eligibility through the **same**
  `mode_policy` function; parity tests enforce it.
- Auto-public precision is never traded for recall without corpus evidence.
