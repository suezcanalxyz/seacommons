# Current work — post-IncidentWatch production baseline

> **Runtime code baseline:** PR #151 merge `b44b5f2b72d64c84ffe99b52a959b597d47d71ea`
> **Production schema:** `0019_incident_watch`
> **Status:** OSINT Evidence Pipeline v1 is merged, deployed and production-verified; Vessel Context + Behavioural Baseline v1 is the current packet.

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

## Current packet — Vessel Context + Behavioural Baseline v1

OSINT Evidence Pipeline v1 is production-verified. The next packet adds explainable vessel memory without creating a vessel reputation score or a second identity truth store.

```text
VesselSubject + registry + VesselTrackDB
  -> deterministic VesselContext
  -> versioned BehaviouralBaseline
  -> explainable BehaviourAssessment
  -> advisory detector metadata only
```

Core rules:

- `VesselContext` is a projection of existing canonical inputs, not new truth;
- persisted baselines are versioned analytical products with deterministic evidence fingerprints;
- v1 dimensions are route corridor, speed envelope, recurrent ports/port pairs, and AIS silence distribution;
- assessment states are exactly `expected`, `unusual`, `insufficient_history`;
- unusual behaviour never by itself alleges intent, opens a Case, or bypasses evidence-lineage/publication gates;
- baseline/operator behaviour metadata is internal and is not added to public Live vessel context;
- YOUR WISDOM is a synthetic benign-service regression plus a same-identity contrastive deviation; production code contains no name/MMSI/IMO/ferry exception.

Migration `0020_vessel_baselines` creates append/version-friendly analytical persistence only. It performs no fleet-wide backfill. Initial production baseline builds are bounded and explicitly audited.

## Order after this packet

1. production-verify Vessel Context + Behavioural Baseline v1;
2. formalise Observation -> Episode -> Hypothesis;
3. implement the already-designed Review v0 on top of the corrected evidence/behaviour model;
4. advance to PostGIS / Section 10 only after those foundations are verified.

## Current engineering gate

Before merge/deploy:

1. keep all new behavior TDD-backed;
2. run full backend plus exact CI Ruff/mypy gates;
3. run Live/Play/map/API/simulation web regressions, lint and build;
4. verify Humanitarian privacy and SAR triangulation independence;
5. verify vessel-marker tests and assets are unchanged;
6. inspect the exact diff and run verification-before-completion;
7. merge only with green Full CI + CodeQL and exact-head verification.
