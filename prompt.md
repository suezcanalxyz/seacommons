# SeaCommons — current agent prompt

Work on `suezcanalxyz/seacommons` from the latest `main` only.

## Verified production baseline — 2026-09-05

- Current runtime-code baseline: PR #148 merge `6e0d1057d9e7d1149a30f3d902e980e248c98d9d`; later docs-only commits may advance `main` without changing deployed API semantics.
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

The next platform packet is **Section 9 — Review and case-management subsystem** in `docs/updates.md`.

Implement it as a bounded, evidence-first vertical slice. Start with a written design/TDD plan before product code.

Initial target:

```text
uncertain/canonical object
  -> typed ReviewReason
  -> durable ReviewDecision / review queue item
  -> analyst/operator decision with provenance
  -> existing canonical pipeline consumes the explicit decision
```

The review subsystem must route uncertainty; it must not become a second incident truth store.

Minimum v0 reasons should cover the existing production uncertainties that are already computable, especially:

- ambiguous duplicate/correlation;
- conflicting location or outcome;
- stale/needs-review Humanitarian case;
- broken source thread;
- circular-reporting risk;
- privacy/publication review;
- entity identity conflict.

Do not invent review reasons whose evidence producers do not yet exist.

## Order after Review v0

Only after the Review subsystem is production-verified should the agent advance to Section 10 / P3 PostGIS foundation and spatial candidate retrieval.

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
