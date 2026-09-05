# SeaCommons — current agent prompt

Work on `suezcanalxyz/seacommons` from the latest `main` only.

## Verified baseline

- Baseline at design start: `ccef5022d220b67d309707e179fc7b264209ec3c`.
- PR #144 merged the shared Live/Play public shell and satellite-first Play map.
- PR #145 fixed Play archive request-loop contention; verification reported `1163 passed, 2 skipped` backend plus green web gates.
- PR #146 fixed progressive archive count labelling and is merged in the current production deployment.
- Vercel production deployment for `ccef502` is `READY` and aliases include `live.seacommons.org` and `play.seacommons.org`.
- No open PR exists at this baseline.

## Do not restart old work

The previous Maritime OSINT Phase 0 prompt is obsolete.

Already implemented on `main` include, among other work:

- durable/idempotent `SourceObservation` and adapter wiring;
- canonical `HumanitarianIncident` state and transitions;
- Humanitarian timer contract;
- current Drift ownership/cutover;
- Source Registry and Coverage Matrix;
- connector contract and preservation policy;
- `CorrelationDecision`;
- circular-reporting lineage;
- typed entity graph;
- Alarm Phone image/OCR V2 integration;
- AIS evidence/safety separation;
- Live 24h operational projection and Play historical archive;
- Sentinel/VIIRS evidence;
- standardized vessel markers and current Live/Play public UI.

Do not reimplement M0/M1/P0/P1/P2 work merely because `docs/fixes.md` or `docs/current_work.md` still contains older baseline language. Inspect actual `main`, merged PRs, and current tests before claiming a gap.

## Current task

The next intended platform primitive is **IncidentWatch v0**.

Authoritative design under review:

`docs/superpowers/specs/2026-09-05-incident-watch-v0-design.md`

Read that document completely before proposing implementation.

Core invariant:

```text
HumanitarianIncident
  -> IncidentWatch
  -> eligible bounded existing adapter
  -> SourceObservation
  -> existing correlation / incident / assessment pipeline
```

IncidentWatch must never directly mutate canonical incident truth.

## Important compatibility constraint

Current SeaCommons can represent an unresolved silent case as:

```text
incident_status=outcome_unknown
lifecycle=archived
```

For watch scheduling this means continued bounded follow-up, not immediate permanent expiration. `incident_status` wins when migration-era lifecycle/status fields disagree.

## Current stop gate

This branch is design-only.

Do **not** implement IncidentWatch code, create an Alembic migration, deploy, restart services, or mutate production until the operator explicitly approves the written design.

After design approval, create a detailed TDD implementation plan before touching production code. Keep the first implementation PR bounded to the canonical watch model/service/scheduler/audit vertical slice. Adapter-specific expansions that materially widen acquisition semantics should be separate follow-up PRs.

## Non-negotiable constraints

- Humanitarian privacy remains authoritative.
- No MMSI/IMO/callsign leakage into public Humanitarian surfaces.
- No new paid provider or uncontrolled general web crawler in v0.
- No LLM/VLM may become incident truth.
- New collected items enter through canonical `SourceObservation` semantics.
- Watch provenance is candidate context, never automatic `SAME_INCIDENT` evidence.
- Connector failure never changes incident lifecycle or outcome.
- No deploy, restart, DB migration, production write, or destructive cleanup without explicit operator approval.
