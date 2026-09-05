# Current work — post-IncidentWatch production baseline

> **Runtime code baseline:** PR #148 merge `6e0d1057d9e7d1149a30f3d902e980e248c98d9d` (subsequent docs-only commits may advance `main`)
> **Production schema:** `0019_incident_watch`
> **Status:** IncidentWatch v0 merged, migrated, deployed and smoke-verified on 2026-09-05.

## Production state

IncidentWatch v0 is now part of the canonical Humanitarian follow-up path:

```text
HumanitarianIncident
  -> IncidentWatch
  -> eligible bounded existing adapter
  -> SourceObservation
  -> existing correlation / incident / assessment pipeline
```

The production rollout included:

- PostgreSQL backup before migration;
- Alembic `0018 -> 0019_incident_watch`;
- coordinated restart of API, worker and Live edge publisher;
- scheduler registration of `incident_watch(5m)`;
- idempotent sync of all pre-existing canonical Humanitarian incidents into watch rows;
- first real scheduler cycle with successful executions and no degraded/error state;
- Live/Play public smoke after rollout.

IncidentWatch remains bounded: the scheduler claims at most three due watches per five-minute run. Existing-case backfill therefore drains gradually instead of creating a source-query storm.

## UI / vessel contract

IncidentWatch did not modify frontend source files.

The current public contract remains:

- moving and stationary vessels use the shared triangle marker;
- NGO colour is the intentional vessel-marker exception;
- Play reuses the same Live vessel marker asset;
- Live and Play production bundles both load the same `vesselMarker` JS/CSS asset.

## Closed operational issue

GitHub issue #41, the historical `demo-api` 502 on Play, was re-tested after rollout. The Play archive API returned HTTP 200 while still reporting `x-seacommons-proxy: demo-api.seacommons.org`, proving the original vhost path itself is healthy. The issue is closed.

## Current packet — OSINT Evidence Pipeline v1

A production false-positive review exposed a fusion-level evidence error: multiple SeaCommons detectors derived from one AIS lineage could be presented as `multi_source_corroborated`, and same-lineage AIS indicators could auto-open a maritime intelligence case.

The current packet corrects that before Review v0:

```text
raw/canonical observation
  -> evidence lineage
  -> one or more indicators
  -> verification from independent lineage count
  -> internal episode OR independently corroborated fused alert
```

Core rules:

- detector count is not source count;
- AISStream/MDA/AIS-derived transforms share one AIS sensor lineage for corroboration;
- X text + OCR from the same platform/publication are not independent corroboration;
- unknown lineage fails closed for corroboration;
- same-lineage multi-indicator grey-zone/sanctions episodes remain internal and do not auto-open intelligence cases;
- high-specificity identity evidence such as a real sanctions/list or duplicate-identity signal retains its dedicated case path;
- public fused alerts expose evidence count, independent-source count and lineage explanation.

YOUR WISDOM (MMSI 229113000 / IMO 9848388) is retained as a synthetic benign-service regression fixture for the Malta/Gozo ferry scenario. The production code contains no ferry/name whitelist.

## Order after this packet

1. production-verify OSINT Evidence Pipeline v1;
2. build Vessel Context + behavioural baseline;
3. formalise Observation -> Episode -> Hypothesis;
4. implement the already-designed Review v0 on top of the corrected evidence model;
5. advance to PostGIS / Section 10 only after those foundations are verified.

## Current engineering gate

Before merge/deploy:

1. keep all new behavior TDD-backed;
2. run full backend plus exact CI Ruff/mypy gates;
3. run Live/Play/map/API/simulation web regressions, lint and build;
4. verify Humanitarian privacy and SAR triangulation independence;
5. verify vessel-marker tests and assets are unchanged;
6. inspect the exact diff and run verification-before-completion;
7. merge only with green Full CI + CodeQL and exact-head verification.
