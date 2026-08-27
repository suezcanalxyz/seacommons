# Changelog

All notable changes to SeaCommons are documented here. The project follows the
Keep a Changelog structure; releases are identified by Git tags when published.

## Unreleased

### Added

- `/api/v1/ops/summary` reports `backend.image_ocr` (tesseract + Pillow
  availability); the console shows an "Image OCR" service row. A missing
  tesseract silently loses every Alarm Phone map-screenshot coordinate, so
  it is now visible.

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

## 0.6.0 - 2026-08-27

### Added

- OSINT ingestion layer: X/Twitter monitor (`twikit_monitor.py`), GDACS
  disaster-alert monitor, NGO response registry, and a source-connector
  review workflow (registry, opportunity/source review states, verified
  attachment), each with dedicated test coverage
  (`test_twikit_monitor.py`, `test_ngo_response.py`, `test_connectors.py`).
- Case taxonomy: an operational `case_type` (distress SAR, pushback, shipwreck,
  missing persons, interception, vessel incident, monitoring, unspecified),
  filterable in the case list and editable per case, with an additive-column
  backfill for databases created before it.
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
