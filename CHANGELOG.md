# Changelog

All notable changes to SeaCommons are documented here. The project follows the
Keep a Changelog structure; releases are identified by Git tags when published.

## Unreleased

### Added

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
