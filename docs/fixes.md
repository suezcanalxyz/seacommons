# SeaCommons Live Stabilization / `fixes.md`

> **Status:** canonical implementation roadmap after the 1 Sep 2026 deep audit.
>
> **Operational baseline:** parent code around `7d0bb2235a35b95bf979adc7b3c87d86b4bea88f`; previous roadmap commit `86a51131ee26379f7132a19b3088cd21f4cde8d8`.
>
> **Primary goal:** stabilize the current Live release before adding new features. Humanitarian and maritime-security signals must be correctly ingested, stored, classified, geolocated, correlated, projected and rendered without turning uncertain evidence into false precision.
>
> **Implementation status (branch `fix/p0-drift-evidence-gate`):** all 16 commit boundaries in section 6 landed, one commit each with its own regression tests. Full backend + web suites green. Alembic is the schema authority (`0001`-`0003`); the runtime DDL backfills stay for one compatibility release. Remaining before the release gate can be signed off: production schema stamp, the production-like smoke run on real current data, and the operator-facing diagnostics/metrics surfaces (roadmap items beyond section 6).

## Non-negotiable invariants

These rules are the acceptance boundary for every phase:

```text
source credibility != location credibility
coordinate extracted != coordinate verified
coordinate verified != maritime-operational coordinate
maritime-operational coordinate != automatic Drift eligibility
Alarm Phone source != active SAR incident
transport path (VM / edge) != product semantics
AIS offline != vessel absent from SAR registry
HTTP failure != empty dataset
geometry=null != generic "position unavailable"
```

A reliable source does not automatically make an OCR coordinate reliable. A reliable coordinate does not automatically make a post an active maritime distress. An active maritime distress does not automatically authorize Drift.

---

# 1. Deep-audit findings

Each finding is classified as **CONFIRMED BUG**, **STRUCTURAL RISK**, **DOCUMENTATION MISMATCH**, or **RECOMMENDED HARDENING**.

## F-01 — disputed OCR can still trigger Drift

**Classification:** CONFIRMED BUG  
**Priority:** P0 / critical

**Code:** `apps/api/core/intel/twikit_monitor.py`, `_apply_media_ocr()` and `_auto_drift_if_live()`; current audited range approximately `557-655`.

Current behavior:

```python
elif method == "easyocr_text_disputed":
    coordinate_source = "media_ocr_text"
    uncertainty_m = 3500
    review_status = "machine_ocr_disputed_needs_review"
...
upgraded = intel_store.enrich_location(...)
...
intel_store.update_metadata(event_id, metadata={"drift_status": "superseded"})
self._auto_drift_if_live(event_id, force=True)
```

`_auto_drift_if_live()` currently checks that auto-Drift is enabled, that `lat/lon` exist and that an existing run is not already complete. It does **not** check `coordinate_review_status`, `location_uncertainty_m`, semantic event type or whether the point is safe for operational modelling.

**Consequence:** an EasyOCR/Tesseract disagreement can become a model origin. `force=True` currently bypasses the existing drift-status dedup and therefore makes the upgrade path especially dangerous.

**Required fix:** introduce a single `is_auto_drift_eligible(event)` gate. `force=True` may bypass recomputation/dedup, never evidence-quality policy.

Minimum allow-list:

```python
AUTO_DRIFT_LOCATION_STATES = {
    "reported_exact",
    "machine_ocr_consensus_verified",
    "human_verified",
}
```

Minimum reject conditions:

```text
coordinate_review_status contains disputed / needs_review
location_status != positioned
uncertainty above configured maximum
non-SAR maritime domain
non-operational humanitarian case
resolved / archived incident
land / non-maritime event
```

**Regression proof:** a fixture with `machine_ocr_disputed_needs_review` must persist the evidence but produce exactly zero Drift requests.

---

## F-02 — OCR work is serialized but queueing is still unbounded

**Classification:** CONFIRMED BUG / STRUCTURAL RISK  
**Priority:** P0 / critical

**Code:** `apps/api/core/intel/twikit_monitor.py::_schedule_media_ocr()`.

Current code:

```python
threading.Thread(
    target=self._apply_media_ocr,
    args=(event_id, urls),
    daemon=True,
    name=f"intel-x-ocr-{tweet_id[-8:]}",
).start()
```

The recent `_TESSERACT_LOCK` correctly prevents concurrent Tesseract execution, but a burst still creates one waiting daemon thread per event.

**Consequence:** thread count and memory can grow during media bursts even though Tesseract itself is serialized. This can again degrade Uvicorn/Live latency.

**Required fix:** replace per-event threads with a bounded queue / fixed executor. Initial VM-safe target:

```env
MEDIA_OCR_WORKERS=1
MEDIA_OCR_QUEUE_MAXSIZE=16
```

Jobs must deduplicate by event/post/media identity. Queue-full must become an explicit recoverable `deferred_queue_full` state, not silent loss.

---

## F-03 — OCR consensus is measured in degrees but presented in metres

**Classification:** CONFIRMED BUG  
**Priority:** P0/P1 / critical correctness

**Code:** `apps/api/core/intel/x_media_utils.py`.

Current code:

```python
cluster = _largest_agreeing_cluster(candidates, tol=0.03)
```

and EasyOCR/Tesseract cross-check:

```python
agree = (
    abs(cross_check[0] - easy_coordinate[0]) <= 0.03
    and abs(cross_check[1] - easy_coordinate[1]) <= 0.03
)
```

The caller then assigns:

```text
machine_ocr_consensus_verified
location_uncertainty_m = 400
```

`0.03°` is kilometre-scale, and longitude degrees vary with latitude.

**Required fix:** compare candidates with haversine/geodesic distance in metres. Persist `ocr_interengine_distance_m` and the threshold used. Initial conservative threshold may be 400-500 m, then calibrated against the regression corpus.

Never assign an uncertainty smaller than the evidence supports.

---

## F-04 — source-only location ranking can promote lower-quality evidence

**Classification:** STRUCTURAL RISK  
**Priority:** P1

**Code:** `apps/api/core/intel/store.py`.

Current ranking:

```python
_COORDINATE_SOURCE_RANK = {
    "none": 0,
    "place_centroid": 1,
    "relative_place_offset": 2,
    "media_pin_landmark": 3,
    "media_ocr_consensus": 4,
    "media_ocr_text": 4,
    "post_text": 5,
}
```

`enrich_location()` compares only source rank:

```python
if new_rank <= previous_rank:
    return False
```

The comparison does not incorporate review status, uncertainty, inter-engine disagreement or human verification.

**Consequence:** two `media_ocr_*` observations with very different evidence quality are effectively peers; future ranking changes can also promote a disputed coordinate over better evidence.

**Required fix:** introduce a first-class `LocationEvidence` quality comparator based on review status + uncertainty + source. A disputed coordinate can be stored for review but must never supersede a verified coordinate.

---

## F-05 — the historical Alarm Phone backfill has already diverged from live OCR semantics

**Classification:** CONFIRMED BUG / DOCUMENTATION MISMATCH  
**Priority:** P0 before any production backfill

**Code:** `apps/api/core/intel/backfill_alarm_phone.py`.

Current backfill interprets the OCR method using string heuristics:

```python
is_text = method.endswith("text")
ocr_engine = "easyocr" if method.startswith("easyocr") else "tesseract"
uncertainty = 1500 if is_text else 4000
...
"coordinate_review_status": "machine_ocr_unverified"
```

This is no longer equivalent to the live path because methods now include `easyocr_tesseract_consensus` and `easyocr_text_disputed`.

Worse, `run(..., with_drift=True)` can call:

```python
schedule_intel_drift(..., force=True, background=False)
```

without applying the review-quality gate.

**Immediate rule:** do not run `python -m core.intel.backfill_alarm_phone --apply --drift` until Phase 1 is merged.

**Required fix:** live ingestion and backfill must consume the same `LocationEvidence` object and the same Drift eligibility function.

---

## F-06 — edge humanitarian semantics differ from VM humanitarian semantics

**Classification:** CONFIRMED BUG / STRUCTURAL RISK  
**Priority:** P0

**Code:** `apps/web/src/hooks/useLiveFeed.js`, `apps/api/core/live/feed.py`, edge publisher/normalizer.

The public browser still applies an Alarm-Phone-only policy to edge/cache humanitarian snapshots:

```js
return isPublicLiveHost && liveMode === 'humanitarian'
  ? alarmPhoneOnly(normalized)
  : normalized;
```

and:

```js
const features = alarmPhoneOnly(edgeSnapshotToFeatures(snapshot));
```

while the VM feed builds humanitarian/security from public policy/domain eligibility.

**Consequence:** what counts as "Humanitarian Live" depends on transport. A valid non-Alarm-Phone humanitarian source can disappear only because the browser is using edge.

**Required fix:** canonical eligibility must live in backend policy. VM and edge publish the same product semantics; browser normalization must not implement a second source policy.

**Acceptance proof:** for a fixed fixture set and timestamp window:

```text
humanitarian incident IDs from VM == humanitarian incident IDs from edge
```

---

## F-07 — `else humanitarian` misclassifies maritime domains

**Classification:** CONFIRMED BUG  
**Priority:** P1

**Code:** `apps/api/core/live/feed.py`.

Current code:

```python
event_mode = (
    "security"
    if event.maritime_domain() in SECURITY_MARITIME_DOMAINS
    else "humanitarian"
)
```

The public default domain set includes `piracy`, while `SECURITY_MARITIME_DOMAINS` does not currently include piracy. Therefore "not in security set" becomes "humanitarian".

**Required fix:** positive allow-lists for both compartments. Never infer humanitarian by complement.

Target:

```text
sar -> humanitarian
piracy -> security
sanctions -> security
grey_zone -> security
iuu_fishing -> security
smuggling -> security
safety -> explicit decision, no fallback
environmental -> explicit decision, no fallback
unknown -> no operational compartment
```

---

## F-08 — current `IntelEvent` type/domain taxonomy is too implicit for long-term storage

**Classification:** STRUCTURAL RISK  
**Priority:** P1

**Code:** `apps/api/core/intel/store.py::IntelEvent`.

Current primary fields are generic:

```text
type
severity
source
lat/lon
linked_mmsi
metadata JSON
```

`tier()` is derived from type + `metadata.is_distress`; `maritime_domain()` is partly derived from type/anomaly and partly stored in metadata. Humanitarian case subtype, lifecycle, location status and review quality are mostly metadata.

This is flexible but makes migrations, analytics, indexes and historical reprocessing harder. It also permits source/type/domain/lifecycle semantics to drift between ingestion paths.

**Required fix:** keep the flexible metadata envelope, but make the canonical classification fields explicit and schema-versioned. See Phase 2.

---

## F-09 — `enrich_location()` snaps any candidate toward sea before evidence validation

**Classification:** STRUCTURAL RISK  
**Priority:** P1

**Code:** `apps/api/core/intel/store.py::enrich_location()`.

Current behavior calls:

```python
lat, lon = nearest_sea_point(float(lat), float(lon))
```

before storing an enriched point.

This is useful for small coastline errors in maritime reports, but is unsafe as a generic location-enrichment behavior because the same humanitarian source can report land incidents (Evros, Lesvos beach/forest cases, reception centres, pushbacks).

**Required fix:** land-to-sea snapping must be conditional on semantic event class + evidence type. Preserve the raw extracted coordinate separately. A terrestrial humanitarian event must never be transformed into a maritime boat marker merely because it came from Alarm Phone.

---

## F-10 — screenshot provenance is not strong enough for an operational trust boundary

**Classification:** RECOMMENDED HARDENING with P1 safety value

Current OCR metadata records method/engine/count, but the operational chain should bind extracted coordinates to the exact source media and source post.

**Required fields:**

```text
source_post_id
source_post_url
media_url
media_sha256
media_index
ocr_candidate_raw_text / bounded raw span
ocr_candidate_parser
ocr_engine
ocr_pass_id / layout
ocr_coordinate_raw
ocr_coordinate_normalized
ocr_interengine_distance_m
coordinate_review_status
location_uncertainty_m
location_observed_at
```

Do not store excessive/private content; raw OCR provenance should be bounded to the coordinate span or forensic packet.

This prevents a coordinate from an old/quoted screenshot being silently attributed to the wrong current incident.

---

## F-11 — pin-only screenshots must not become fake exact positions

**Classification:** RECOMMENDED HARDENING  
**Priority:** P1

Alarm Phone examples include maps with a pin but no printed coordinates. `map_pin_geolocate.py` can estimate a location from the pin and visible map labels.

That is useful evidence but is not equivalent to DMS/DMM text.

**Required policy:**

```text
printed coordinate + validated parser + quality pass -> exact/derived point
pin + map landmark fit -> approximate point/area with conservative uncertainty
region text only -> region polygon/area
pin without adequate calibration -> unpositioned/needs_review
```

A pin-only result cannot be labelled as exact and cannot auto-Drift unless a separate quality threshold specifically validates it.

---

## F-12 — frontend hides event time and collapses all missing locations

**Classification:** CONFIRMED BUG  
**Priority:** P1

**Code:** `apps/web/src/components/IntelDashboard.jsx::renderEvent()`.

Current rendering derives:

```js
const position = Array.isArray(coords) && coords.length >= 2
  ? `${Number(coords[1]).toFixed(4)}, ${Number(coords[0]).toFixed(4)}`
  : 'position unavailable';
```

The timestamp is currently mainly available as a button `title` tooltip. This is effectively hidden on touch devices.

**Required fix:** timestamp must be visible in every humanitarian row; null geometry must map to a semantic status (`OCR PROCESSING`, `OCR DISPUTED`, `REGION ONLY`, `NOT EXTRACTED`, `WITHHELD`).

---

## F-13 — NGO registry state is destroyed before the UI can show offline vessels

**Classification:** CONFIRMED BUG  
**Priority:** P1

**Code:** `apps/web/src/main.jsx`, NGO fetch effect.

Current frontend filters to positioned vessels before storing state:

```js
const positioned = {
  ...data,
  features: data.features.filter((f) => f.geometry?.coordinates),
};
setNgoVessels(positioned);
```

Backend `ngo_vessel_geojson()` intentionally returns registered but currently offline vessels with `geometry:null` and metadata including `org`, `role`, `operator_type`, `vessel_class`.

**Required fix:** preserve full `sarFleet`; derive `sarMapFeatures` only at the map-source boundary.

---

## F-14 — DB indexes were repaired, but runtime DDL is not a migration strategy

**Classification:** CONFIRMED HISTORICAL BUG + STRUCTURAL RISK  
**Priority:** P1

The production `intel_events` table previously had no physical indexes despite ORM `index=True`; startup `_ensure_indexes()` was added as emergency repair. Keep it during stabilization, but introduce Alembic before the next schema evolution.

Composite indexes must be justified by the actual `persisted_events()` workload, especially recent `source + timestamp` and `type + timestamp` queries.

---

# 2. Alarm Phone screenshot trust boundary

The attached real-world examples define the minimum regression corpus. The pipeline must handle all of these without assuming that every Alarm Phone post is an active maritime distress.

## Coordinate-bearing images

Representative formats:

```text
N 34° 13'   E 012° 53'
N 34° 16.292'   E 011° 56.538'
37°18'31.3"N   27°09'51.1"E
N 33°52.664'   E 013°10.555'
41°33'09.1"N   26°31'37.1"E
```

Required parsing tests:

- DMS, DMM, decimal degrees;
- hemisphere prefix/suffix;
- spaces/no spaces;
- Unicode/ascii degree/minute/second marks;
- OCR `O/0`, `I/1`, punctuation confusion only when correction is unambiguous;
- coordinate order and sign;
- valid geographic ranges;
- expected operational region;
- consistency with textual region when the post names Central Med / Malta SAR / Farmakonisi / Lesvos / Evros.

A parser correction must preserve the raw OCR span so reviewers can see what was changed.

## Pin-only image

Example: Malta SAR screenshot with a visible yellow pin and no readable numeric coordinate.

Expected result:

```text
location_status = region_only / approximate / needs_review
NOT exact solely because a pin is visible
NO automatic Drift unless the landmark-fit quality gate explicitly passes
```

## Lifecycle follow-up

Examples:

```text
"the people have been found and taken to a reception centre"
"the people have arrived in the reception camp on Lesvos"
```

These must update the same incident rather than create a second active marker.

## Humanitarian but not active maritime distress

Examples in the attached feed include:

- advocacy / memorial posts;
- missing-person route alerts;
- interception / pushback reports;
- land incidents near Evros;
- rescue/resolution follow-ups;
- posts referring to an NGO vessel such as Humanity 1;
- translated/near-duplicate posts.

`source=Alarm Phone` must therefore be separate from `humanitarian_case_type` and `lifecycle`.

---

# 3. Canonical data model after stabilization

The database must not rely on one overloaded `type` plus ad-hoc metadata to answer operational questions.

## 3.1 Preserve existing event envelope

Keep the current durable fields for compatibility:

```text
id
timestamp_utc
type
severity
lat
lon
title
text
url
source
linked_mmsi
meta
```

## 3.2 Add canonical classification fields through migration

Recommended schema additions, after inventorying production:

```text
source_timestamp_utc     timestamp with timezone
received_at              timestamp with timezone
maritime_domain          enum/string, indexed
operational_tier         enum/string, indexed
humanitarian_case_type   enum/string nullable, indexed
incident_lifecycle       enum/string nullable, indexed
location_status          enum/string nullable
coordinate_review_status enum/string nullable
location_uncertainty_m   float nullable
schema_version           integer/not-null
```

Do not remove the JSON metadata envelope; it remains the provenance/extension area.

## 3.3 Canonical humanitarian case taxonomy

Initial taxonomy must be finite and explicit:

```text
distress              active/urgent maritime distress
missing               people overdue / no contact
interception          interception/return event
pushback              pushback allegation/report
rescue_update         rescue operation update, non-originating incident
resolution            follow-up that resolves an existing incident
land_humanitarian     land/border humanitarian case
advocacy              non-operational public communication
unknown_humanitarian  review lane, never auto-Drift
```

This is distinct from source and from `maritime_domain`.

## 3.4 Example canonical row

```json
{
  "source": "alarm_phone",
  "type": "distress",
  "humanitarian_case_type": "distress",
  "maritime_domain": "sar",
  "operational_tier": "operational",
  "incident_lifecycle": "active",
  "source_timestamp_utc": "2026-08-21T03:31:00Z",
  "received_at": "2026-08-21T03:33:14Z",
  "location_status": "positioned",
  "coordinate_review_status": "machine_ocr_consensus_verified",
  "location_uncertainty_m": 430,
  "lat": 34.27153,
  "lon": 11.94230
}
```

A land Evros case may instead be:

```json
{
  "source": "alarm_phone",
  "humanitarian_case_type": "land_humanitarian",
  "maritime_domain": null,
  "operational_tier": "news",
  "incident_lifecycle": "active",
  "location_status": "withheld_from_maritime_map",
  "lat": 41.55253,
  "lon": 26.52703
}
```

It remains a humanitarian record without becoming a boat/Drift origin.

---

# 4. Phased implementation

## Phase 0 — freeze unsafe behavior and stabilize runtime

**Must complete before historical reprocessing.**

### P0.1 Drift evidence gate

Files:

```text
apps/api/core/intel/twikit_monitor.py
apps/api/core/intel/drift_service.py or shared policy module
apps/api/core/intel/store.py
```

Implement `is_auto_drift_eligible(event)` once and call it from every auto/backfill Drift path.

Required tests:

```text
disputed OCR -> persist, no Drift
unverified OCR -> no automatic Drift
region-only -> no Drift
land humanitarian -> no Drift
resolved incident -> no Drift
verified SAR exact point -> Drift allowed
force=True -> cannot bypass evidence gate
```

Suggested commit:

`fix(humanitarian): gate auto drift on verified location evidence`

### P0.2 bounded OCR queue

Replace `_schedule_media_ocr()` per-event `threading.Thread()` with one bounded queue/executor.

Required metrics:

```text
ocr_queue_depth
ocr_queue_oldest_job_seconds
ocr_queue_rejected_total
ocr_job_duration_seconds
ocr_consensus_total
ocr_disputed_total
ocr_no_coordinate_total
ocr_drift_rejected_total
```

Suggested commit:

`fix(perf): bound humanitarian media OCR work`

### P0.3 Live transport semantics

Unify public eligibility in backend policy. Edge and VM must project the same humanitarian incident set. Remove `alarmPhoneOnly()` from the browser only after edge publisher parity is proven.

Suggested commit:

`fix(live): make edge and vm share humanitarian eligibility`

### P0.4 explicit feed connection state

Frontend state must distinguish:

```text
loading
live
stale
retrying
offline
empty
```

`empty` means a successful canonical response with zero events. Timeout/network failure must preserve last-good snapshot and show degradation.

Suggested commit:

`fix(live): distinguish empty feed from transport failure`

### P0.5 DB query proof

Keep emergency physical indexes. Capture `EXPLAIN (ANALYZE, BUFFERS)` for real `persisted_events()` shapes before adding composites.

Candidates:

```sql
(source, timestamp_utc DESC)
(type, timestamp_utc DESC)
```

Do not delete single-column indexes until real query plans justify it.

---

## Phase 1 — make screenshot geolocation evidence-safe

### P1.1 `LocationEvidence`

Create one shared model for live ingestion and backfill.

Suggested fields:

```python
@dataclass(frozen=True)
class LocationEvidence:
    lat: float | None
    lon: float | None
    source: str
    review_status: str
    uncertainty_m: float | None
    raw_coordinate_text: str | None
    normalized_coordinate_text: str | None
    engine: str | None
    pass_id: str | None
    media_sha256: str | None
    source_post_id: str | None
    media_index: int | None
    interengine_distance_m: float | None
```

Suggested commit:

`refactor(humanitarian): centralize location evidence semantics`

### P1.2 geodesic OCR consensus

Replace every `0.03°` agreement test with metric distance. Store distance + threshold. Add DMS/DMM regression fixtures from the attached Alarm Phone patterns.

Suggested commit:

`fix(ocr): validate coordinate consensus in metres`

### P1.3 evidence-aware upgrade comparator

Replace source-only `_COORDINATE_SOURCE_RANK` decisions with a comparator that includes review status and uncertainty.

Rules:

```text
human_verified > reported_exact > OCR consensus > OCR unverified > OCR disputed > pin estimate > region
verified can replace disputed
disputed cannot replace verified
same quality only replaces if evidence is demonstrably better/newer
```

### P1.4 semantic land/sea handling

Preserve the raw extracted coordinate. Only apply `nearest_sea_point()` when the case is explicitly maritime and the displacement is within a conservative threshold.

Never sea-snap Evros/land-humanitarian incidents.

### P1.5 pin-only state

Pin/landmark estimation is approximate evidence with explicit uncertainty. If calibration cannot meet the threshold, return `needs_review` / region-only rather than an exact public point.

---

## Phase 2 — canonical taxonomy + database migration

### P2.1 freeze enums/taxonomy in one module

Define canonical enums for:

```text
MaritimeDomain
HumanitarianCaseType
IncidentLifecycle
OperationalTier
LocationStatus
CoordinateReviewStatus
VerificationStatus
```

No ingestion path may invent ad-hoc alternative values.

Suggested commit:

`refactor(domain): centralize live humanitarian taxonomy`

### P2.2 introduce Alembic

Inventory production first. Create a non-destructive baseline, stamp production only after schema equivalence is checked, then add canonical fields and composite indexes in explicit migrations.

Keep `_ensure_indexes()` for one compatibility release, then retire runtime DDL after every environment is at migration head.

Suggested commits:

```text
build(db): introduce alembic current-schema baseline
migrate(db): add canonical live classification fields
migrate(db): add recent-event composite indexes
```

### P2.3 dual-write then backfill

For one release, write canonical fields both to explicit columns and metadata where existing consumers require metadata. Do not migrate historical rows until new ingestion tests pass.

### P2.4 storage acceptance

A SQL query must be able to answer without parsing arbitrary JSON:

```text
all active humanitarian distress cases
all interception cases
all land humanitarian cases
all security piracy cases
all events with disputed location
all resolved Alarm Phone incidents
all events by source time window
```

---

## Phase 3 — incident lifecycle, duplicates and correlation

### P3.1 source != incident

Alarm Phone is a source. The classifier must distinguish distress, missing, interception, pushback, land humanitarian, resolution and advocacy.

### P3.2 thread linkage first

Strong linkage order:

```text
direct reply / quoted tracked incident / explicit tweet ID
> stable canonical source+URL identity
> strong incident correlation
> weak spatial/text similarity
```

Do not merge two groups merely because they are both in Central Med on the same day.

### P3.3 lifecycle regression corpus

Tests must include:

```text
"found and taken to a reception centre" -> resolves parent
"arrived in the reception camp" -> resolves parent or explicit review state
"still drifting / boat sinking" -> remains/reopens active
resolved reply followed by newer danger update -> reopen if same incident
advocacy/memorial -> no operational incident
Evros land pushback -> humanitarian record, no maritime marker/Drift
translated duplicate -> one canonical incident
```

### P3.4 interception/responder context

Humanity 1 / Mare Jonio / coastguard proximity may be stored as contextual evidence. Do not claim `responding`, `rescuing` or causal involvement unless an authoritative source says so.

Suggested commit:

`fix(humanitarian): harden case typing lifecycle and thread correlation`

---

## Phase 4 — Live UI and Civil SAR fleet

### P4.1 humanitarian event presentation

Create a dedicated distress/humanitarian presentation path instead of rendering Alarm Phone through a vessel-oriented row.

Minimum visible mobile card:

```text
ALARM PHONE · ACTIVE                 20:04 CEST
8 min ago

~37 PEOPLE IN URGENT DISTRESS
Central Mediterranean

POSITION · 34.2715, 11.9423 · ±430 m
SOURCE · Alarm Phone / X
```

Or, when evidence is not exact:

```text
LOCATION · OCR PROCESSING
LOCATION · OCR DISPUTED · REVIEW REQUIRED
REGION ONLY · CENTRAL MEDITERRANEAN
LOCATION · NOT EXTRACTED
LOCATION · WITHHELD
```

Remove the generic `position unavailable` path from humanitarian UI.

Suggested commit:

`fix(live): expose humanitarian time lifecycle and location quality`

### P4.2 preserve full fleet state

Use:

```text
sarFleet = complete endpoint response
sarMapFeatures = only features with geometry
```

The panel can therefore show Ocean Viking/Humanity 1/etc. even when AIS-offline without fabricating map markers.

### P4.3 Civil NGO vs State SAR

Public grouping:

```text
CIVIL SAR NGOs
STATE SAR AUTHORITIES
```

Selected vessel details must show organization + operator type. Mare Jonio should not appear as only `52 · 0 kn · MMSI`.

Suggested commit:

`feat(live): expose complete civil and state sar fleet`

### P4.4 mobile acceptance

On the iPhone-sized viewport used in the supplied screenshots:

```text
event time visible without hover
location quality visible
no exact point for disputed evidence
tap centers map only when publishable geometry exists
fleet list includes AIS-offline registry entries
selected NGO shows organization and operator class
no overlapping critical controls
```

---

## Phase 5 — safe historical repair

Only run after Phases 0-3 are deployed and tested.

Required order:

```text
Drift gate
-> shared LocationEvidence
-> geodesic consensus
-> semantic land/sea handling
-> canonical taxonomy
-> lifecycle regression
-> backfill dry-run
-> manually audit sample
-> apply without Drift
-> audit again
-> optional Drift only for events passing is_auto_drift_eligible()
```

Backfill must be idempotent and must never downgrade higher-quality evidence.

Required report:

```text
scanned
already_good
newly_positioned_exact
newly_positioned_approximate
region_only
still_unpositioned
disputed
land_humanitarian
lifecycle_changed
duplicate_merged
drift_eligible
drift_rejected
```

Suggested commit:

`feat(humanitarian): add canonical safe alarm phone reprocessing`

---

## Phase 6 — production proof, monitoring and release gate

### Required metrics

```text
live_signals_request_duration_seconds
live_signals_request_errors_total
live_signals_response_events
live_edge_snapshot_age_seconds
live_vm_edge_incident_set_mismatch
db_query_duration_seconds{query="persisted_events"}
process_threads
ocr_queue_depth
ocr_queue_oldest_job_seconds
ocr_disputed_total
ocr_drift_rejected_total
```

### Critical invariants to alert on

```text
disputed OCR -> Drift count > 0                  CRITICAL
VM/edge humanitarian incident-set mismatch       CRITICAL
thread count grows with OCR burst                 CRITICAL
public exact geometry for disputed location       CRITICAL
piracy classified humanitarian                    CRITICAL
```

### Release smoke corpus

At minimum:

1. active Alarm Phone distress + verified DMM coordinate;
2. active Alarm Phone distress + verified DMS coordinate;
3. screenshot with pin only;
4. OCR disagreement;
5. Central Med region-only text;
6. Farmakonisi-style resolution reply;
7. Lesvos-style resolution reply;
8. Evros land humanitarian coordinate;
9. interception involving a Civil SAR vessel;
10. advocacy/memorial Alarm Phone post;
11. translated/duplicate Alarm Phone post;
12. live civil NGO AIS record;
13. offline civil NGO registry record;
14. state SAR record;
15. piracy/security event;
16. restart with durable event outside the in-memory 600-event deque.

---

# 5. Counter-proof: how to know `fixes.md` actually fixed the product

This section is deliberately binary. Do not declare the roadmap complete because unit tests are green; prove the user-visible and DB outcomes.

## Question A — "Humanitarian sarà fixato?"

**YES only if all of these are true:**

```text
[ ] Alarm Phone is treated as source, not automatic active distress
[ ] humanitarian_case_type is canonical and persisted
[ ] direct replies/follow-ups attach to the same incident
[ ] advocacy does not create an active SAR marker
[ ] land humanitarian cases do not become boats
[ ] interception/pushback/missing are distinguishable from fresh distress
[ ] disputed OCR persists for review but never auto-Drifts
[ ] edge and VM return the same humanitarian eligibility
[ ] transport failure never becomes fake empty humanitarian feed
```

If any checkbox fails, Humanitarian is not considered fixed.

## Question B — "Vedrò punti precisi?"

**YES, when the source actually contains enough evidence. Not every screenshot should become a precise point.**

Expected outcomes:

```text
printed DMS/DMM + validated parser + evidence-quality pass
    -> precise public point + uncertainty

EasyOCR + Tesseract metric consensus
    -> precise/derived point + measured uncertainty

one engine only
    -> unverified / conservative point or review according to policy

engines disagree
    -> NO precise public point, REVIEW REQUIRED, NO Drift

pin only + strong landmark calibration
    -> approximate point/area + large uncertainty

pin only + weak calibration
    -> region-only / unpositioned

text says Central Med / Malta SAR only
    -> region area, never fake exact coordinate

Evros/land coordinate
    -> stored humanitarian location but not maritime marker/Drift
```

The success criterion is therefore not "every event has a dot". It is "every dot has defensible provenance and uncertainty".

## Question C — "Il database sarà ben strutturato?"

**YES only after Phase 2 migration + query proof.**

Required proof:

```text
[ ] Alembic is migration authority
[ ] production schema is at migration head
[ ] canonical classification columns exist
[ ] source timestamp and received timestamp are distinguishable
[ ] maritime_domain is explicit/indexable
[ ] humanitarian_case_type is explicit/indexable
[ ] incident_lifecycle is explicit/indexable
[ ] location/review state is queryable without decoding arbitrary JSON
[ ] provenance remains available in metadata/forensic records
[ ] query plans use appropriate indexes for recent source/type scans
[ ] restart preserves repaired classifications and locations
```

Do not remove the JSON metadata envelope; the goal is structured canonical fields plus extensible provenance.

## Question D — "Categorie e tipologie saranno correttamente storate?"

**YES only if this separation survives ingestion, DB, projection and frontend:**

```text
source                Alarm Phone / IOM / partner / AIS / etc.
event type            twitter / distress / ais_anomaly / etc. transport/domain event type
humanitarian case     distress / missing / interception / pushback / land / advocacy / resolution
maritime domain       sar / piracy / sanctions / grey_zone / iuu / smuggling / ...
operational tier      operational / news / signal
lifecycle             active / resolved / needs_review / archived
verification          public-source / partner / corroborated / derived / ...
location status       positioned / region_only / processing / disputed / withheld / unpositioned
```

A test must read the stored DB row and the public feature and prove that these meanings have not collapsed into one another.

## Question E — "Gli screenshot Alarm Phone allegati saranno coperti?"

**YES only when regression fixtures cover:**

```text
N 34° 16.292' E 011° 56.538'
37°18'31.3"N 27°09'51.1"E
N 33°52.664' E 013°10.555'
41°33'09.1"N 26°31'37.1"E
pin without coordinate text
Central Med / Malta SAR region-only text
resolution reply
interception update
land Evros case
translated duplicate
advocacy/memorial post
```

For each fixture test both classification and geolocation; a parser-only test is insufficient.

---

# 6. Commit boundaries

Do not implement all fixes in one agent pass.

Recommended order:

```text
1. fix(humanitarian): gate auto drift on verified location evidence
2. fix(perf): bound humanitarian media OCR work
3. fix(live): make edge and vm share humanitarian eligibility
4. fix(live): distinguish empty feed from transport failure
5. refactor(humanitarian): centralize location evidence semantics
6. fix(ocr): validate coordinate consensus in metres
7. fix(humanitarian): make location upgrades evidence aware
8. refactor(domain): centralize live humanitarian taxonomy
9. build(db): introduce alembic current-schema baseline
10. migrate(db): add canonical live classification fields
11. migrate(db): add recent-event composite indexes
12. fix(humanitarian): harden case typing lifecycle and thread correlation
13. fix(live): expose humanitarian time lifecycle and location quality
14. feat(live): expose complete civil and state sar fleet
15. feat(humanitarian): add canonical safe alarm phone reprocessing
16. test(live): add end-to-end stabilization smoke corpus
```

Each commit requires its own regression test and verification checkpoint.

---

# 7. Final release gate

This version is **not stable** until every item below is proven on a fresh deployment.
`[x]` = covered by an automated regression test on `fix/p0-drift-evidence-gate`;
`[ ]` = still needs the production-like smoke run / manual proof.

```text
[x] disputed OCR -> 0 auto-Drift
[x] `force=True` cannot bypass location policy
[x] OCR agreement uses geodesic metres, not degree deltas
[x] live and backfill share identical LocationEvidence semantics
[x] source-post/media provenance is persisted for OCR-derived coordinates
[x] pin-only input does not create fake exact coordinates
[x] Evros/land input creates 0 maritime Drift and 0 fake boat marker
[x] DMS/DMM Alarm Phone fixtures parse correctly
[x] follow-up resolution updates the original incident
[x] translated/duplicate posts do not create duplicate incidents
[x] advocacy does not enter the active SAR lane
[x] OCR queue/thread count remains bounded during burst
[ ] public Live remains responsive during OCR burst
[x] connection failure never renders as a legitimate zero-event state
[x] VM and edge agree on humanitarian incident eligibility
[x] browser has no independent Alarm-Phone-only product policy
[x] piracy is never humanitarian
[x] canonical taxonomy is persisted in DB
[x] Alembic owns schema evolution
[x] recent source/type queries use verified query plans/indexes
[x] event source time is visible on mobile
[x] generic `position unavailable` is absent from humanitarian UI
[x] location uncertainty/review state is visible
[x] complete Civil SAR registry survives AIS offline state
[x] map receives only fleet entries with geometry
[x] Civil NGO and State SAR identities remain distinct
[x] selected Mare Jonio/other NGO shows organization + operator class
[ ] restart preserves durable events, classifications, lifecycle and repaired locations
```

## Definition of done

A fresh mobile user must be able to open `live.seacommons.org` and answer, without reading code or guessing marker colours:

```text
What happened?
When did it happen?
What kind of humanitarian/maritime case is it?
Is it active, resolved, under review or archived?
Which source reported it?
Where is it — and how precise/reliable is that location?
If there is no point, why is it absent?
Is a displayed vessel Civil NGO, State SAR or generic AIS?
Is a trajectory/cone observed data or a model output?
```

If the UI shows a precise dot or Drift cone that cannot be traced back to defensible Location Evidence, the release fails this document even if all services are technically online.

---

# F-13 — SeaCommons classifies, it does not score (category-based visual taxonomy)

**Branch:** `fix/humanitarian-category-drift` (base `c0f526877afd`).
**Full write-up + production trace:** `docs/current_work.md`.

## New product invariant

```text
CATEGORY          -> visual identity / colour
LIFECYCLE         -> temporal / status presentation (outline, opacity, badge)
EVIDENCE QUALITY  -> confidence / uncertainty
DRIFT ELIGIBILITY -> whether modelling is allowed
severity          -> none of the above (DB-compatibility column only, Stage 1)
```

* Alarm Phone category = **red** — maritime point, land point, region area,
  drift origin and drift trajectory/cone alike. Lifecycle never changes it; a
  resolved Alarm Phone is not green.
* Land Alarm Phone = **visible** red land-humanitarian point, **no maritime
  drift**.
* Sea Alarm Phone specific point = **automatic drift**, persisted, exposed on
  `/api/v1/live/drifts`, rendered.
* Region-only Alarm Phone = **visible area, no drift**.

## Confirmed bugs fixed

| # | Bug | Fix |
| --- | --- | --- |
| F-13a | `/api/v1/live/drifts` returned `[]` for every current Alarm Phone maritime incident — `public_drift_collection` gated on `state == "active"`, but real incidents are `needs_review` / `resolved` | withhold the cone only for `resolved` / `archived`; also require `is_auto_drift_eligible()` so a stale region-only `drift_result` cannot paint a trajectory |
| F-13b | Public Live ran a second in-browser scientific drift model and threw away the persisted VM result (`setIntelDrifts({features:[]})`) | one pipeline: backend/worker computes, frontend visualizes; browser drift is now only the user-triggered simulation |
| F-13c | Land Alarm Phone incidents dropped from the map (`public_geometry_and_precision` removed any on-land coordinate) | `land_humanitarian` cases plot at their reported coordinate; maritime drift still blocked by the eligibility gate |
| F-13d | Colour driven by lifecycle (green/amber/grey) and `intel_severity` (map + drift layers); `classifyEventVisual` fell back to `severity`; `ConePanel` showed `RISK_COLOR` + `Risk level: HIGH`; context publication gated on `severity == "low"` | canonical `core.domain.visual_category` taxonomy; colour = `visual_category`; lifecycle = opacity + outline dash; panel shows measured quantities + a `Category` row; context publication is corroboration-based |
| F-13e | `sar-case-*` simulation layers in no `LAYER_GROUPS` entry — un-toggleable, outside the public allow-list | new `simulation` layer group; simulation features tagged `trajectory_kind: user_simulation` |
| F-13f | Public Live still styled OSINT markers by `severity`: `intel-cat-*` and `intel-events-layer` took `circle-stroke-width` / `circle-stroke-color` from a `['match', ['get', 'severity'], ...]` ramp; `intel-vessel-links-layer` `line-color` and `mda-anomaly-layer` `circle-stroke-width` did the same | marker outline is now a static contrast stroke (`#04131a`, width `1.1`); the correlation line inherits the linked signal's `visual_color`; MDA anomaly stroke width is constant |
| F-13g | The report panel showed a full "Professional vessel identity" block (MMSI / IMO / flag) and the feed row headlined `MMSI <n>` for a humanitarian Alarm Phone case that happened to carry a `linked_mmsi` | `ConePanel` hides the vessel-identity block for an Alarm Phone / `humanitarian_alarm_phone` signal; `IntelDashboard` never falls back to a bare MMSI headline for a humanitarian row (uses the incident title / "Distress report"). Backend still emits `linked_mmsi` for vessel-episode joins — stripping it there is a separate product call. Also removed a duplicate `Category` row in the panel header. |

## Regression tests added

`tests/test_visual_category.py`, `tests/test_public_geometry.py`
(`land_humanitarian` visible), `tests/test_live_feed.py`
(`needs_review` keeps drift; region-only does not; drift carries category not
severity; context publication ignores severity),
`apps/web/src/features/live/eventVisual.test.js` (Alarm Phone always red;
`classifyEventVisual` never falls back to severity),
`apps/web/src/simulation/liveTracking.test.js` (`needs_review` keeps the
persisted drift), `apps/edge/src/live.test.js` (edge preserves category +
origin metadata).

## Suite results on the branch

```
backend:  544 passed
web:      simulation 26 / live 26 / api 3 / map 5  (all pass)
edge:     10 passed
lint + typecheck + vite build: green
```

## Not done here (needs operator decision — see docs/current_work.md)

* Whether a **resolved** Alarm Phone stays on the public map (conflicts with
  the tested `lifecycle.is_within_live_window` invariant).
* Cleaning the stuck `drift_results` row `intel:aa91d1a0` (`status =
  computing`) — a production DB row mutation.
* Stage 2 severity removal: decouple the remaining internal ingestion /
  alerting thresholds, then remove `LiveSignalProperties.severity` and drop
  `intel_events.severity` via a reversible Alembic migration after a complete
  reader/writer audit.
* Land-coordinate privacy confirmation for border/detention cases.
