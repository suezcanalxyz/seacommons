# Changelog

All notable changes to SeaCommons are documented here. The project follows the
Keep a Changelog structure; releases are identified by Git tags when published.

## Unreleased

### Added

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
