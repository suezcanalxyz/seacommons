# Changelog

All notable changes to SeaCommons are documented here. The project follows the
Keep a Changelog structure; releases are identified by Git tags when published.

## Unreleased

### Added

- OSINT cross-source fusion engine (`core/intel/fusion.py`): every intel event
  now fans out through a new `intel_store.subscribe` hook to a correlation
  engine that runs rules over the recent-event window. A rule that fires emits
  a `correlated_alert` intel event (so it reaches the map / feed / WebSocket /
  DB), auto-opens a case linking the contributing events via the new
  `case_intel_events` bridge, and fires a rate-limited notification
  (`notify_alert`). v1 rules: multi-source SAR corroboration (folds in
  `triangulation.evaluate`), dark-fleet / AIS spoofing (two distinct anomalies,
  one MMSI, one window → `sanctions`), grey-zone infrastructure proximity (AIS
  gap/loiter near an offshore platform or subsea corridor → `grey_zone`), and
  single-source vessel-casualty / GDACS-hazard triggers (`safety`). The
  operator console gains an **Alert rail**, a dedicated pulsing `correlated_alert`
  map layer coloured by domain, a togglable AIS-anomaly layer (previously hidden
  outright), a banner + chime on new critical alerts, and per-source OSINT
  icons. `CorrelationEngine` (physical sensor fusion) is no longer a discarded
  instance — its `on_threat` now surfaces a `correlated_alert`. New config:
  `FUSION_ENABLED`, `FUSION_*` windows/radii, `FUSION_NOTIFY_COOLDOWN_S`.
  `open_case()` extracted to `core/cases/service.py` so the route and the engine
  share one path. `GET /api/v1/cases/{id}` now returns linked `intel_events`.
- Maritime-domain compartments (phase 1): every intel event now carries a
  `maritime_domain` tag (`sar` · `sanctions` · `grey_zone` · `iuu_fishing` ·
  `piracy` · `smuggling` · `environmental` · `safety`), inferred from event
  type / AIS-anomaly subtype so legacy events resolve to `sar`. The operator
  console gains a compartment filter. Public Live is unchanged: only `sar`
  (and `piracy`) are eligible without an explicit publish, configurable via
  `PUBLIC_MARITIME_DOMAINS`. New `case_type` values `sanctions_watch`,
  `dark_rendezvous`, `subsea_infrastructure`, `piracy_incident`. See
  `docs/COMPARTMENTS.md`.
- `GET /api/v1/ops/data-status` — one place to see what real data SeaCommons
  has flowing in and what it costs to run: ingestion sources, intel volume
  by type/source, vessel counts, drift job load, and the single-slot drift
  engine bottleneck. Documented in `docs/OPERATIONS_OVERVIEW.md`.
- `python -m core.intel.backfill_alarm_phone` re-processes historical (and
  archived) Alarm Phone events with the current OCR / pin-from-landmarks
  pipeline: it re-fetches the tweet images from the public syndication CDN,
  extracts a real position, writes it back, and can queue a drift for the
  event's own moment. Dry-run by default. New ingests also persist the
  media URLs so a re-process never has to resolve the tweet again.

## 0.6.0 - 2026-08-27

### Added

- Realistic operational drift (Phase 15): per-object-class OpenDrift model
  selection, wave-driven Stokes drift, a real coastline landmask,
  probability-of-containment search ellipses, ensembles seeded over the
  report's real position uncertainty, multi-object shipwreck debris fields,
  and `GET /api/v1/drift/history` for prediction history. See the individual
  entries below.
- Vessel incidents and anomalies from the live AIS feed: SART/MOB/EPIRB
  beacons, sustained aground / not-under-command, and operator-only signals
  for impossible speed, dark-zone entry, OFAC-SDN match and AIS silence.
- Case taxonomy (`case_type`) with an additive-column backfill.
- `/api/v1/ops/summary` reports `backend.image_ocr` (tesseract + Pillow
  availability); the console shows an "Image OCR" service row. A missing
  tesseract silently loses every Alarm Phone map-screenshot coordinate, so
  it is now visible.
- Vessel incidents from the live AIS feed: AIS-SART/MOB/EPIRB beacons
  (immediate distress), sustained aground (operational incident) and
  sustained not-under-command (operator review). Runs off the existing
  AISStream connection; incidents flow through the Live map and drift.
- AIS anomaly signals (operator-only): impossible speed, dark-zone entry,
  OFAC-SDN vessel match, and prolonged AIS silence for a vessel last seen
  underway. Previously implemented but never wired; now driven off the
  shared AIS feed and persisted as `ais_anomaly` intel events.

- Per-object-class drift model selection (`core/drift/profiles.py`): powered
  and large hulls (cargo, container ship, tanker, motorboat, sailboat, lost
  container) now drift with OpenDrift `OceanDrift` and calibrated windage
  instead of person-in-water Leeway coefficients. SAR objects keep Leeway.
  `case_type` supplies a default object class when no `vessel_type` is given.
- Wave-driven Stokes drift in operational drift runs, from Open-Meteo wave
  height and period, enabled only when wave data is actually returned.
- A real coastline (`reader_global_landmask`) in drift runs, so particles
  beach instead of drifting across land.
- `GET /api/v1/drift/history?event_id=` — the full drift prediction history
  for an incident (model, object class, forcing quality, Stokes/landmask,
  impact point, per run), for daily analysis of how a forecast evolved.

### Changed

- AIS stream reliability: forces a reconnect after 3 minutes with an open
  socket but no PositionReports (a known AISStream failure mode), and the
  anomaly detector now prunes its per-vessel tracking so memory stays
  bounded on the small VM. `/api/v1/ops/summary` reports
  `backend.intel_monitors` (which monitors attached, and the AIS feed hook
  count) so a silent pipeline is visible.
- Alarm Phone map-screenshot coordinate extraction is more robust: Tesseract
  runs extra character-whitelisted passes, common digit/letter misreads are
  folded before parsing, and the multi-pass consensus now clusters candidates
  instead of requiring an exact pair. The pin-from-landmarks geolocation
  detects blue and amber markers (not only map red) and drops a single
  OCR-misplaced landmark before fitting.
- Drift search cones are now a 90%-probability-of-containment ellipse fitted
  to the particle cloud (outlier-trimmed), replacing the raw convex hull that
  one stray particle could inflate. Properties carry `radius_p50_m`,
  `radius_p90_m`, `semi_axes_p90_m` and `area_km2`.
- Drift ensembles are seeded over the report's actual position uncertainty
  (`location_uncertainty_m`, capped 50 km) instead of a fixed 150 m radius,
  and each particle now carries an independent current-factor (~8%) and,
  for vessels, windage (~20%) perturbation. Runs are deterministic per
  request.
- Shipwreck cases seed a multi-object Leeway debris field (persons in
  water, life rafts, wooden fragments) rather than a single object type,
  widening the search area to match how differently those objects drift.
- The drift panel shows the 90% search area, radius and ellipse axes.

### Also in 0.6.0 — foundational work

- OSINT ingestion layer: X/Twitter monitor (`twikit_monitor.py`), GDACS
  disaster-alert monitor, NGO response registry, and a source-connector
  review workflow (registry, opportunity/source review states, verified
  attachment), each with dedicated test coverage
  (`test_twikit_monitor.py`, `test_ngo_response.py`, `test_connectors.py`).
- Case taxonomy `case_type` — filterable, editable per case, additive-column
  backfill for existing databases.
- Governance routes and workflows for connector/source review.
- Canonical backend, frontend, JSON Schema and Edge contracts for Live domain
  vocabulary, lifecycle, geometry precision and publication policy.
- Realtime invariant tests for duplicate delivery, ordering, removal and restart
  recovery.
- Prometheus metrics and log escalation for split-runtime intel synchronization
  and aggregated source health.
- Canonical architecture, data-flow, security and realtime documentation.
- Dependency update automation and report-only baseline security/lint/type CI
  gates, with a blocking clean Edge dependency audit.
- Blocking critical Ruff, canonical-domain mypy, declared-project Python/npm
  dependency audits and scheduled Python/JavaScript CodeQL analysis.
- Repository ownership, contribution templates and architecture decision records.

### Changed

- Decomposed Live/Intel backend routes into services and projections.
- Extracted frontend domain, realtime and Cesium scene responsibilities from
  large entry components.
- Consolidated public/private policy and made unknown source policies fail closed.

### Security

- User-originated signals remain private by default through canonical ingestion
  models.
- Public Live publisher and Edge ingress validate payload vocabulary and reject
  private or contract-invalid events.
- Updated frontend transitive dependencies to versions without known npm
  advisories for DOMPurify, nanoid and PostCSS.

## 0.4.0 - 2026-07-15

Historical pilot baseline. Earlier changes predate the maintained changelog;
consult Git history and the dated audit documents in `docs/` for evidence.
