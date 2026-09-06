# SeaCommons — current agent prompt

Work on `suezcanalxyz/seacommons` from the latest `main` only.

## Verified production baseline — 2026-09-06

- Current runtime-code baseline: PR #151 merge `b44b5f2b72d64c84ffe99b52a959b597d47d71ea` (OSINT Evidence Pipeline v1).
- IncidentWatch v0 is implemented, migrated and deployed; production Alembic head is `0019_incident_watch`.
- Full CI #421 and CodeQL #380 passed on the implementation head before merge.
- Production Vercel deployment for the merge is `READY` on Live and Play.
- `live.seacommons.org` and `play.seacommons.org` both return 200 and load the same shared vessel-marker asset.
- Live public feed and Play archive API both return 200 after rollout.
- Existing canonical Humanitarian incidents were idempotently synced into IncidentWatch after deployment.
- The historical Play demo-api 502 issue #41 is closed after direct application smoke returned 200 through the same demo vhost.

## Do not restart completed work

Already implemented and production-backed include:

- durable/idempotent `SourceObservation` and adapter wiring;
- canonical `HumanitarianIncident`, lifecycle transitions and timer contract;
- current Drift ownership/cutover;
- Source Registry, Coverage Matrix and coverage-change tracking;
- connector contract and preservation policy;
- `CorrelationDecision`, circular-reporting lineage and typed entity graph;
- Alarm Phone image/OCR V2 and AIS evidence/safety separation;
- Live 24h operational projection and Play historical archive;
- Sentinel/VIIRS evidence;
- standardized shared Live/Play vessel triangles;
- `IncidentWatchDB`, bounded scheduling, leases, retry/backoff and operator audit;
- official-X bounded incident follow-up through `SourceObservation`;
- compatibility for unresolved `outcome_unknown + lifecycle=archived` cases.

Do not reimplement these because historical sections in `docs/fixes.md` describe them as future work. Inspect actual `main`, migrations, merged PRs and tests first.

## Current task

The immediate platform packet is **Vessel Context + Behavioural Baseline v1**. OSINT Evidence Pipeline v1 is already production-verified and must remain authoritative for source independence and publication.

Current invariant:

```text
vessel identity/context != behavioural baseline
unusual != suspicious
baseline output != allegation
behaviour context may inform an observation but cannot open a Case by itself
```

Required v1 behavior:

- build deterministic `VesselContext` from existing VesselSubject/registry/track evidence;
- persist versioned behavioural baselines with deterministic evidence fingerprints under migration `0020_vessel_behavioural_baselines`;
- model only route corridor, speed envelope, recurrent ports/port pairs and AIS silence distribution;
- emit only `expected`, `unusual`, or `insufficient_history` plus bounded reason codes and measurements;
- attach compact behaviour context to selected AIS-derived observations without altering fusion case/publication authority;
- keep baseline and behavioural reason codes operator/internal; public Live vessel context remains on the existing safe projection;
- preserve YOUR WISDOM as a benign recurring-service regression and a same-identity contrastive deviation, never as a hard-coded suppress rule.

## Order after Vessel Context + Behavioural Baseline v1

After this packet is production-verified, continue with **Observation -> Episode -> Hypothesis**, then **Review v0**. Section 10 / PostGIS remains after the evidence/review foundation.

## Non-negotiable constraints

- Humanitarian privacy remains authoritative; no MMSI/IMO/callsign leakage into public Humanitarian surfaces.
- Vessel class is context, never an allegation.
- Safety observations never become Humanitarian or Intelligence by fallback.
- Observation, incident/episode, assessment, review and publication remain distinct objects.
- Models may assist but never silently become canonical truth.
- Every new durable object is replayable and provenance-linked.
- One semantic authority per PR; TDD first; exact-commit verification before merge.
- Preserve the shared Live/Play vessel-marker contract and existing public UI semantics unless a packet explicitly targets them.
- No production migration, restart or destructive maintenance without explicit operator approval.
