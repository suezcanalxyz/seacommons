# Free/Open AIS Fusion v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a software-only, free/open-first multi-provider AIS layer using existing AISStream plus Open Waters/aiscast, with provider/station provenance, health, reconciliation, and coverage-aware gap reasoning feeding the existing SeaCommons track and SAR analysis stack.

**Architecture:** Introduce one normalized `AISPositionObservation` contract plus a compatibility-preserving AIS event bus. Existing AISStream first emits through the bus while the bus preserves the exact legacy hook signature; only after parity tests are green does Open Waters/aiscast join as a second producer. Reconciliation happens before canonical registry/track consumers, while legacy direct-hook behaviour remains available behind a feature flag for instant rollback. Provider multiplicity is availability evidence, not automatic independent physical corroboration.

**Tech Stack:** Python 3.12, FastAPI runtime, existing websocket client stack, SQLAlchemy/PostgreSQL vessel tracks, pytest, current `source_registry` observability.

**Spec:** `docs/superpowers/specs/2026-09-06-humanitarian-evidence-pipeline-design.md`

## Global Constraints

- Core v1 must require no new hardware and no paid AIS provider.
- AISStream remains operational during the cutover; no big-bang replacement.
- Open Waters/aiscast is the first new provider adapter; v1 uses `wss://ais.openwaters.io/v1/stream` and begins with bounded subscriptions, never an unrestricted Mediterranean-wide anonymous socket.
- Provider/station IDs are provenance, not public Humanitarian output.
- Two providers observing the same AIS broadcast do not count automatically as two independent evidence lineages.
- Safety/nav-status observations never become Humanitarian or Maritime Intelligence by fallback.
- Existing `VesselRegistry`, `TrackStore`, Behavioural Baseline, episode, hypothesis, and Humanitarian privacy contracts remain authoritative.
- Every behavior change is TDD: watch RED before production code and verify GREEN after.
- No database migration in this packet unless parity proves existing `SourceObservation.provenance`, `SourceCoverageEventDB`, and `VesselTrackDB.source` cannot carry the required audit context.
- Existing neighbour-based `gap` vs `coverage_gap` logic in `core/anomaly/ais.py` remains authoritative and is extended, not duplicated.
- aiscast source/license attribution must be preserved per upstream event; provider software being MIT does not relicense upstream AIS data.

---

### Task 0: Compatibility harness and rollback boundary

**Files:**
- Create: `tests/test_ais_bus_compat.py`
- Create: `apps/api/core/vessels/ais_bus.py`
- Modify: `apps/api/core/config.py`

**Interfaces:**
- Produces: `ais_bus.register_position_hook()` with the exact existing 9-argument callback contract and `ais_bus.publish(AISPositionObservation)`.
- Compatibility: legacy `core.vessels.aisstream.register_position_hook` delegates to the bus; consumers do not move files or change signatures in this task.
- Rollback: `AIS_FUSION_ENABLED=false` keeps AISStream-only behaviour.

- [x] **Step 1: Snapshot the current hook contract in a RED parity test**

```python
def test_bus_delivers_exact_legacy_hook_shape():
    seen = []
    ais_bus.register_position_hook(lambda *args: seen.append(args))
    ais_bus.publish(_normalized_aisstream_fix())
    assert len(seen) == 1
    assert len(seen[0]) == 9
    assert seen[0][0] == "247123456"
```

Also assert repeated registration is idempotent and a broken consumer cannot stop delivery to later consumers.

- [x] **Step 2: Run RED**

Run: `pytest -q tests/test_ais_bus_compat.py tests/test_vessel_incidents.py tests/test_ais_source_observation.py`
Expected: FAIL only because `ais_bus` does not exist.

- [x] **Step 3: Implement the bus and delegation shim**

Keep `aisstream.register_position_hook()` and `position_hook_count()` as compatibility wrappers. Do not edit TrackStore, AIS anomaly, vessel incident, or SourceObservation consumer signatures yet.

- [x] **Step 4: Verify parity GREEN**

Run: `pytest -q tests/test_ais_bus_compat.py tests/test_vessel_incidents.py tests/test_ais_source_observation.py tests/test_aisstream_health.py`
Expected: PASS with the same hook count and event semantics as main.

- [x] **Step 5: Commit**

```bash
git add apps/api/core/vessels/ais_bus.py apps/api/core/vessels/aisstream.py apps/api/core/config.py tests/test_ais_bus_compat.py
git commit -m "refactor: add compatibility preserving AIS event bus"
```


**Execution:** RED failed on missing `core.vessels.ais_bus`; GREEN: `21 passed` across bus compatibility, vessel incidents, SourceObservation sampling, and AISStream health. Preserved the private `_position_hooks` alias because an existing regression/tooling contract resets it directly.

### Task 1: Normalized AIS provider contract

**Files:**
- Create: `apps/api/core/vessels/ais_provider.py`
- Test: `tests/test_ais_provider.py`

**Interfaces:**
- Produces: `AISPositionObservation`, `AISProviderHealth`, `AISProviderAdapter` protocol, `normalize_provider_name()`.
- Consumes: no runtime provider implementation yet.

- [x] **Step 1: Write the failing contract tests**

```python
from datetime import datetime, timezone
from core.vessels.ais_provider import AISPositionObservation


def test_position_observation_keeps_provider_and_station_provenance():
    obs = AISPositionObservation(
        mmsi="247123456", ship_name="TEST", lat=35.0, lon=15.0,
        sog=8.2, cog=91.0, heading=90.0, nav_status=0,
        observed_at=datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc),
        received_at=datetime(2026, 9, 6, 10, 0, 2, tzinfo=timezone.utc),
        provider="aiscast", upstream_source="volunteer", station_id="station-42",
        source_terms="CC0-1.0", raw_message_id="abc",
    )
    assert obs.provider == "aiscast"
    assert obs.station_id == "station-42"
    assert obs.mmsi == "247123456"
```

- [x] **Step 2: Run test to verify RED**

Run: `pytest -q tests/test_ais_provider.py`
Expected: FAIL because `core.vessels.ais_provider` does not exist.
- [x] **Step 3: Implement the minimal immutable contract**

```python
@dataclass(frozen=True)
class AISPositionObservation:
    mmsi: str
    ship_name: str
    lat: float
    lon: float
    sog: float | None
    cog: float | None
    heading: float | None
    nav_status: int | None
    observed_at: datetime
    received_at: datetime
    provider: str  # transport/adapter: aisstream | aiscast
    upstream_source: str | None = None  # aiscast source: volunteer | aishub | aisstream | ...
    station_id: str | None = None
    source_terms: str | None = None
    raw_message_id: str | None = None

@dataclass(frozen=True)
class AISProviderHealth:
    provider: str
    connected: bool
    last_message_at: datetime | None
    messages_received: int
    error: str | None = None
```

Define an `AISProviderAdapter` protocol with `start()`, `stop()`, `health()`, and a callback accepting `AISPositionObservation`.

- [x] **Step 4: Run tests GREEN**

Run: `pytest -q tests/test_ais_provider.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add apps/api/core/vessels/ais_provider.py tests/test_ais_provider.py
git commit -m "feat: add normalized AIS provider contract"
```

**Execution:** RED failed on missing `core.vessels.ais_provider`; GREEN: `4 passed`. Contract is frozen/immutable and preserves transport provider, upstream source, station, terms, and raw message identity.

### Task 2: Wrap AISStream behind the provider contract

**Files:**
- Modify: `apps/api/core/vessels/aisstream.py`
- Modify: `tests/test_aisstream_health.py`
- Modify: `tests/test_vessel_incidents.py`

**Interfaces:**
- Consumes: `AISPositionObservation` and provider callback from Task 1.
- Produces: AISStream observations tagged `provider="aisstream"`; preserves current start/stop behavior and source health.

- [x] **Step 1: Write RED tests that AISStream emits the normalized contract once per PositionReport**

```python
def test_aisstream_position_report_emits_provider_observation(monkeypatch):
    seen = []
    client = AISStreamClient("key", on_observation=seen.append)
    client._handle(_position_message(mmsi="247123456", lat=35.1, lon=15.2), _Registry())
    assert len(seen) == 1
    assert seen[0].provider == "aisstream"
    assert seen[0].mmsi == "247123456"
```

Keep the existing hook-count regression: one AISStream socket must not multiply per downstream consumer.

- [x] **Step 2: Run the focused tests and watch RED**

Run: `pytest -q tests/test_aisstream_health.py tests/test_vessel_incidents.py`
Expected: FAIL because `AISStreamClient` does not yet accept/emit the normalized callback.

- [x] **Step 3: Implement adapter emission without changing subscription semantics**

`AISStreamClient._handle()` should build one `AISPositionObservation` using provider=`aisstream`, station_id=None, observed_at=received_at when upstream message time is unavailable. Keep ShipStaticData registry updates as-is for v1.

- [x] **Step 4: Verify GREEN**

Run: `pytest -q tests/test_aisstream_health.py tests/test_vessel_incidents.py tests/test_ais_provider.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add apps/api/core/vessels/aisstream.py tests/test_aisstream_health.py tests/test_vessel_incidents.py
git commit -m "refactor: emit normalized AISStream observations"
```

**Execution:** RED failed because `AISStreamClient` lacked `on_observation`; GREEN: `16 passed`. AISStream now emits one normalized observation per PositionReport and the same observation is fanned out through the legacy-compatible bus; registry/static-data semantics remain unchanged.

### Task 3: Add the Open Waters/aiscast adapter

**Files:**
- Create: `apps/api/core/vessels/aiscast.py`
- Create: `tests/test_aiscast.py`
- Modify: `apps/api/core/config.py`

**Interfaces:**
- Consumes: `AISPositionObservation` and `AISProviderHealth` from Task 1.
- Produces: `AiscastClient(on_observation=...)` with reconnect/backoff, provider health, and station provenance when exposed upstream.

- [x] **Step 1: Write RED parser and reconnect tests using captured fixture payloads**

```python
def test_aiscast_message_preserves_station_provenance():
    obs = parse_aiscast_message({
        "mmsi": 247123456, "lat": 35.2, "lon": 15.3,
        "sog": 7.4, "cog": 182.0, "source": "volunteer", "station": "mt-01",
        "terms": "CC0-1.0", "timestamp": "2026-09-06T10:05:00Z",
    }, received_at=_NOW)
    assert obs.provider == "aiscast"
    assert obs.upstream_source == "volunteer"
    assert obs.station_id == "mt-01"
    assert obs.mmsi == "247123456"
```

Add contrastive tests for malformed MMSI, missing coordinates, invalid latitude/longitude, missing optional station ID, and disconnect -> degraded health -> reconnect.

- [x] **Step 2: Run and verify RED**

Run: `pytest -q tests/test_aiscast.py`
Expected: FAIL because module/config do not exist.

- [x] **Step 3: Implement the minimal client**

Use the verified native endpoint `wss://ais.openwaters.io/v1/stream`, bounded reconnect backoff, and no credential requirement in the default anonymous path. Start with a small configured bbox plus the known NGO MMSI set because the anonymous tier is bounded. Parse and preserve upstream `source`, `station`, event id/time, and source/license attribution metadata when present. Do not copy provider-specific JSON past `parse_aiscast_message()`.

Config fields:
```python
AISCAST_ENABLED: bool = False
AISCAST_WS_URL: str = "wss://ais.openwaters.io/v1/stream"
AISCAST_BBOX: str = ""  # bounded bbox; anonymous API allows at most 100 square degrees
AISCAST_NGO_MMSI_LIMIT: int = 10  # anonymous tier limit per subscription
```

The anonymous service currently permits 2 concurrent connections, 20 messages/s, 100 square degrees, and 10 MMSIs per subscription. V1 must therefore be useful with one bounded Central-Mediterranean coverage subscription and/or one NGO-MMSI subscription; it must not assume whole-Mediterranean parity with AISStream. A token/higher tier is optional deployment policy, never a core requirement.

If the verified upstream endpoint differs at implementation time, update only the default URL and its test fixture; do not change the adapter contract.

- [x] **Step 4: Verify GREEN**

Run: `pytest -q tests/test_aiscast.py tests/test_ais_provider.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add apps/api/core/vessels/aiscast.py apps/api/core/config.py tests/test_aiscast.py
git commit -m "feat: add free aiscast provider adapter"
```


**Execution:** Verified current Open Waters native v1 stream contract and anonymous limits before coding. RED failed on missing adapter; GREEN: `14 passed`. Adapter rejects unbounded/oversized anonymous subscriptions, preserves upstream source/station/terms/id, and exposes provider health.

### Task 4: Reconcile provider observations into one canonical track input

**Files:**
- Create: `apps/api/core/vessels/ais_reconcile.py`
- Create: `tests/test_ais_reconcile.py`
- Modify: `apps/api/core/vessels/track_store.py`
- Modify: `apps/api/core/vessels/registry.py`

**Interfaces:**
- Consumes: normalized `AISPositionObservation` from Tasks 2-3.
- Produces: `AISReconciler.ingest(obs) -> ReconciledAISFix | None`; only accepted reconciled fixes update registry/track history.

- [x] **Step 1: Write RED tests for duplicate and conflicting provider fixes**

```python
def test_same_broadcast_from_two_providers_emits_one_fix():
    r = AISReconciler(fallback_time_delta_s=2, fallback_distance_m=30)
    assert r.ingest(_obs("aisstream", 35.0, 15.0, second=0)) is not None
    assert r.ingest(_obs("aiscast", 35.00002, 15.00002, second=1, raw_message_id="same-1")) is None


def test_materially_new_fix_is_preserved():
    r = AISReconciler(fallback_time_delta_s=2, fallback_distance_m=30)
    r.ingest(_obs("aisstream", 35.0, 15.0, second=0, raw_message_id="a"))
    fix = r.ingest(_obs("aiscast", 35.02, 15.02, second=10, raw_message_id="b"))
    assert fix is not None
    assert fix.transport_providers == {"aiscast"}
    assert fix.upstream_sources == {"volunteer"}
```

- [x] **Step 2: Run RED**

Run: `pytest -q tests/test_ais_reconcile.py`
Expected: FAIL because reconciler does not exist.

- [x] **Step 3: Implement bounded reconciliation**

Prefer exact upstream event id/raw NMEA identity when available. Only use a conservative fallback fingerprint over MMSI + tightly quantized event time/position + navigation fields when no raw identity exists; do not suppress two legitimate high-rate AIS reports merely because they are close in space/time. Never average disagreeing coordinates. Preserve transport providers separately from `upstream_sources`, `station_ids`, `source_terms`, and selected-fix provenance. An aiscast event whose `upstream_source=aisstream` collapses to the same lineage as direct AISStream.

- [x] **Step 4: Dispatch accepted fixes through the compatibility bus**

In `shadow` mode, reconciliation is comparison-only and existing AISStream registry/hooks remain authoritative. In `fused` mode, an accepted fix updates registry once and is dispatched through the legacy hook shim so AIS anomaly and vessel-incident consumers remain unchanged. Migrate only `TrackStore` to a normalized-hook path in this task so its existing `source` column records the selected upstream source (`aisstream`, `volunteer`, `aishub`, etc.); keep `TrackStore.on_position(...)` as a compatibility wrapper for tests/internal callers.

- [x] **Step 5: Verify GREEN**

Run: `pytest -q tests/test_ais_reconcile.py tests/test_ais_spike_detector.py tests/test_replay_end_to_end.py`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add apps/api/core/vessels/ais_reconcile.py apps/api/core/vessels/track_store.py apps/api/core/vessels/registry.py tests/test_ais_reconcile.py
git commit -m "feat: reconcile multi-provider AIS fixes"
```


**Execution:** RED failed on missing reconciler/TrackStore/Registry entry points. GREEN: `30 passed` across reconciliation, AIS spike, and replay tests. Same-upstream duplicate deliveries collapse; different upstream fixes stay distinct unless exact event identity matches. Registry provenance is memory-only in v1 and no DB migration was required.

### Task 5: Make AIS gaps coverage-aware

**Files:**
- Create: `apps/api/core/vessels/ais_coverage.py`
- Create: `tests/test_ais_coverage.py`
- Modify: `apps/api/core/intel/ais_spike_detector.py`
- Modify: `apps/api/core/vessels/track_store.py`

**Interfaces:**
- Consumes: provider health, recent station/provider activity, reconciled track history.
- Produces: `CoverageAssessment(status, active_providers, active_stations, confidence, reason_codes)`.

- [ ] **Step 1: Write RED contrastive tests**

```python
def test_single_provider_outage_does_not_create_real_gap():
    c = assess_coverage(active_upstreams={"volunteer"}, degraded_upstreams={"aisstream"}, nearby_traffic_seen=True)
    assert c.status == "upstream_degraded"


def test_all_providers_silent_while_area_has_traffic_is_possible_real_silence():
    c = assess_coverage(active_upstreams={"aisstream", "volunteer"}, degraded_upstreams=set(), nearby_traffic_seen=True)
    assert c.status == "coverage_present"
```

Add detector regression: a candidate silence during `upstream_degraded` may create coverage context but must not emit a `dark_transit`-eligible gap episode.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_ais_coverage.py tests/test_ais_spike_detector.py`
Expected: FAIL on missing coverage contract/gate.

- [ ] **Step 3: Implement deterministic coverage assessment**

Reason codes are limited to `UPSTREAM_DEGRADED`, `COVERAGE_PRESENT`, `COVERAGE_UNKNOWN`, `NO_NEARBY_TRAFFIC`. Transport-provider count is never evidence independence. `aiscast(source=aisstream)` must not mask a direct AISStream outage. Extend the existing neighbour-based detector and reuse `SourceCoverageEventDB`/`coverage_change_log.py`; do not create a second persistent coverage truth.

- [ ] **Step 4: Verify GREEN**

Run: `pytest -q tests/test_ais_coverage.py tests/test_ais_spike_detector.py tests/test_hypothesis_engine.py`
Expected: PASS, including no low-specificity hypothesis inflation.

- [ ] **Step 5: Commit**

```bash
git add apps/api/core/vessels/ais_coverage.py apps/api/core/intel/ais_spike_detector.py apps/api/core/vessels/track_store.py tests/test_ais_coverage.py tests/test_ais_spike_detector.py
git commit -m "feat: make AIS gap reasoning coverage aware"
```

### Task 6: Feed reconciled AIS into SAR Mission Assessment

**Files:**
- Modify: `apps/api/core/intel/ngo_response.py`
- Create: `tests/test_ngo_response_reconciled.py`

**Interfaces:**
- Consumes: reconciled registry/track data and coverage context.
- Produces: NGO response rows with `track_providers`, `coverage_status`, and motion flags derived from reconciled history.

- [ ] **Step 1: Write RED mission tests**

```python
def test_ngo_response_uses_reconciled_fix_and_reports_provider_context():
    result = analyze_ngo_response(_incident(), registry_geojson=_reconciled_registry())
    vessel = result["ngo_vessels"][0]
    assert vessel["track_providers"] == ["aiscast", "aisstream"]
    assert vessel["coverage_status"] == "coverage_present"
```

Add regression that `heading_toward + upstream_degraded` cannot be promoted beyond `possible_response`; AIS alone never yields `rescue_confirmed`.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_ngo_response.py tests/test_ngo_response_reconciled.py`
Expected: FAIL because provider/coverage context is absent.

- [ ] **Step 3: Extend the existing analysis, do not create a parallel tracker**

Read provider/coverage fields already projected by the reconciled registry/track layer. Preserve current distance, ETA, and motion-flag calculations. Do not expose Humanitarian MMSI/IMO/callsign in public projections.

- [ ] **Step 4: Verify GREEN**

Run: `pytest -q tests/test_ngo_response.py tests/test_ngo_response_reconciled.py tests/test_live_feed.py tests/test_incident_watch.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/core/intel/ngo_response.py tests/test_ngo_response_reconciled.py
git commit -m "feat: enrich SAR response analysis with reconciled AIS"
```

### Task 7: Shadow-mode bootstrap and production-safe cutover

**Files:**
- Modify: `apps/api/core/bootstrap.py`
- Modify: `apps/api/core/config.py`
- Modify: `apps/api/core/intel/engine.py`
- Modify: `apps/api/core/observability.py`
- Create: `tests/test_ais_fusion_bootstrap.py`

**Interfaces:**
- Consumes: AIS bus, AISStream adapter, aiscast adapter, reconciler, provider health.
- Produces: staged runtime modes `legacy`, `shadow`, `fused` with one-command rollback.

- [ ] **Step 1: Write RED startup-mode tests**

```python
def test_shadow_mode_never_changes_canonical_registry_or_track_store():
    runtime = _start_runtime(mode="shadow")
    runtime.aiscast.inject(_volunteer_fix())
    assert runtime.shadow_comparisons == 1
    assert runtime.canonical_writes_from_aiscast == 0


def test_legacy_mode_starts_no_aiscast_client():
    runtime = _start_runtime(mode="legacy")
    assert runtime.aiscast_started is False
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_ais_fusion_bootstrap.py`
Expected: FAIL because runtime modes do not exist.

- [ ] **Step 3: Implement explicit staged configuration**

```python
AIS_FUSION_MODE: str = "legacy"  # legacy | shadow | fused
AISCAST_ENABLED: bool = False
```

`legacy`: production behavior identical to main. `shadow`: aiscast connects and reconciliation metrics are computed, but only AISStream writes registry/tracks/legacy hooks. `fused`: accepted reconciled fixes drive the canonical bus; direct AISStream canonical writes are disabled.

Do not start providers in both API and worker in split mode: preserve the existing `INTEL_MONITORS_ENABLED` boundary. Register each source-health name once per process.

- [ ] **Step 4: Add bounded observability**

Expose counters for received fixes by transport/upstream, dedup/collapse reason, selected canonical upstream, provider/upstream health, and shadow disagreements. Never label metrics with MMSI, station ID, or other high-cardinality identifiers.

- [ ] **Step 5: Verify GREEN**

Run: `pytest -q tests/test_ais_fusion_bootstrap.py tests/test_aisstream_health.py tests/test_observability.py tests/test_observability_health.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/core/bootstrap.py apps/api/core/config.py apps/api/core/intel/engine.py apps/api/core/observability.py tests/test_ais_fusion_bootstrap.py
git commit -m "feat: stage free AIS fusion behind shadow cutover"
```

### Task 8: Release gates and bounded live verification

**Files:**
- Modify: `docs/OPERATIONS_OVERVIEW.md`
- Modify: `docs/DATA_FLOW.md`
- Test: existing backend/web/edge suites.

- [ ] **Step 1: Run compatibility and invariant gates**

Run focused AIS, evidence-lineage, Humanitarian privacy, vessel-marker, episode/hypothesis, and SAR-response tests. Expected: all PASS and hook-count parity preserved.

- [ ] **Step 2: Run full backend and static gates**

Run: `pytest -q`, Ruff critical gate, canonical mypy, `git diff --check`. Expected: PASS with only documented pre-existing warnings.

- [ ] **Step 3: Run web/edge gates**

Run existing web tests/lint/typecheck/build plus edge tests and Wrangler dry-run. Expected: PASS.

- [ ] **Step 4: Deploy shadow mode first**

Production configuration: `AIS_FUSION_MODE=shadow`, `AISCAST_ENABLED=true`, with a bounded Central-Mediterranean bbox or NGO MMSI subscription that fits anonymous limits. Do not change public output semantics.

Verify for a bounded observation window: AISStream message rate remains stable, aiscast receives events, no extra Humanitarian items appear, no increase in low-specificity hypotheses/cases, and shadow disagreements are observable.

- [ ] **Step 5: Enable fused mode only after parity**

Switch only `AIS_FUSION_MODE=fused`; retain `legacy` as instant rollback. Verify `/ready`, Live/Play, service health, track freshness, NGO response analysis, gap/coverage metrics, and Humanitarian privacy.

- [ ] **Step 6: Document exact upstream terms**

Document that aiscast code is MIT but each event retains its upstream data terms/attribution; do not claim the aggregate is uniformly open-licensed or commercially reusable without respecting the event source terms.
