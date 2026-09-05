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

The immediate platform packet is **OSINT Evidence Pipeline v1**. It takes precedence over Section 9 Review v0 because review must sit on top of analytically correct evidence semantics.

Current invariant:

```text
observation != corroboration
multiple detectors != multiple independent sources
single-source multi-indicator evidence may remain an internal episode
but may not claim multi-source corroboration or auto-open an intelligence case
```

Required v1 behavior:

- derive source/sensor lineage from canonical provenance and `independence_group`;
- treat AIS-derived detectors sharing one sensor lineage as one source for corroboration;
- treat X post text and OCR from the same platform/publication as one source lineage;
- emit `single_source_observed`, `single_source_multi_indicator`, or `multi_source_corroborated` from actual lineage;
- keep same-lineage grey-zone/sanctions fused episodes internal unless a high-specificity evidence producer independently justifies a case;
- expose evidence count, independent-source count and lineage explanation on genuinely publishable fused alerts;
- preserve YOUR WISDOM (Malta/Gozo ferry) as a benign-service regression fixture, never as a hard-coded suppress rule.

## Order after OSINT Evidence Pipeline v1

After this packet is production-verified, continue with **Vessel Context + behavioural baseline**, then **Observation -> Episode -> Hypothesis**. Revisit **Review v0** only on top of that corrected evidence model. Section 10 / PostGIS remains after the evidence/review foundation, not before it.

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
