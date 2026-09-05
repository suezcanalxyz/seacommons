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

## Next packet

Next authority from `docs/updates.md`: **Section 9 — Review and case-management subsystem**.

The first Review v0 PR should persist typed, provenance-linked review work without creating a parallel truth model. It should consume already-existing uncertainty signals and provide a replayable decision boundary for analyst/operator actions.

PostGIS / Section 10 remains after Review v0, not before it.

## Current engineering gate

Before the next product PR:

1. sync latest `main`;
2. read Section 9 and its existing producers/consumers;
3. inventory current `review_status`, `CorrelationDecision.review_state`, privacy gates and entity-conflict signals;
4. define one canonical `ReviewDecision`/queue authority and deletion/compatibility path for overlapping flags;
5. write failing tests first;
6. keep the first PR to one review vertical slice;
7. run full backend, web/edge regression when touched, migrations and privacy/publication checks;
8. merge only with green CI and exact-head verification.
