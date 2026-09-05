# Current work — IncidentWatch v0 design review

> **Branch:** `spec/incident-watch-v0`
> **Base:** `ccef5022d220b67d309707e179fc7b264209ec3c`
> **Status:** design-only branch. No product code, migration, deploy, restart, or production mutation.

## Current production/repository baseline

The previous Humanitarian/Maritime Phase 0 notes in this file were stale. The current repository has already progressed through the canonical evidence foundation and the first production Humanitarian cutover.

Implemented on `main` before this branch include:

- durable/idempotent `SourceObservation` with source-adapter coverage;
- canonical `HumanitarianIncident`, lifecycle transitions and public timer fields;
- current Drift ownership and Live cutover;
- Source Registry, Coverage Matrix and coverage-change tracking;
- connector contract and preservation-policy classification;
- `CorrelationDecision`, circular-reporting lineage and typed entity graph;
- Alarm Phone image/OCR V2 integration and AIS evidence/safety fixes;
- Live 24h operational projection and Play historical archive;
- satellite evidence via Sentinel/VIIRS;
- shared Live/Play public shell and standardized vessel markers.

The current Vercel production deployment is built from `ccef502` and reports `READY`. No implementation PR is open at the start of this design branch.

## Current design target

The next platform primitive is `IncidentWatch v0`.

Authoritative design under review:

`docs/superpowers/specs/2026-09-05-incident-watch-v0-design.md`

The core data-flow invariant is:

```text
HumanitarianIncident
  -> IncidentWatch
  -> eligible bounded existing adapter
  -> SourceObservation
  -> existing correlation / incident / assessment pipeline
```

IncidentWatch performs follow-up collection only. It never directly changes lifecycle, incident truth, correlation decisions, Drift ownership, or public projection.

## Compatibility decision captured in the design

Current SeaCommons can persist a silent unresolved case as:

```text
incident_status=outcome_unknown
lifecycle=archived
```

For watch scheduling, this must remain eligible for bounded follow-up. `incident_status` therefore wins when migration-era lifecycle/status semantics disagree.

## Next gate

1. Operator reviews and approves the written IncidentWatch v0 design.
2. Only after approval, write the TDD implementation plan.
3. Implement the canonical watch model/service/scheduler/audit vertical slice in one reviewable PR.
4. Keep materially different adapter integrations as separate follow-up packets when they widen acquisition semantics.
5. Production rollout remains separately operator-approved after merge and verification.

## Production note

The historical GitHub issue #41 about `demo-api` returning 502 remains open, but it predates the current deployment. Vercel currently shows the `ccef502` deployment as `READY`, with `play.seacommons.org` and `live.seacommons.org` attached, and no 5xx runtime logs were observed in the checked recent window. Do not close #41 solely from that evidence; close it only after direct vhost/application smoke confirms the old symptom is gone.
