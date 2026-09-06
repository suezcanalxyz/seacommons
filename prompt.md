# SeaCommons — current agent prompt

Work on `suezcanalxyz/seacommons` from the latest `main` only.

## Verified production baseline — 2026-09-06

- Current runtime-code baseline: PR #152 merge `fbcdb55471af4b19f45dfc927146e7ea26dc08b2`.
- OSINT Evidence Pipeline v1 is merged, deployed and production-verified.
- Vessel Context + Behavioural Baseline v1 is merged, deployed and production-verified.
- Production Alembic head is `0020_vessel_baselines`; bounded production baseline rows were audited after rollout.
- API, worker and Live edge publisher are active; `/ready`, `live.seacommons.org` and `play.seacommons.org` returned 200 after the rollout.
- Live and Play still use the same shared vessel-marker assets.
- IncidentWatch v0 remains the canonical bounded Humanitarian follow-up path.

## Do not restart completed work

Already implemented and production-backed include:

- durable/idempotent `SourceObservation` and adapter wiring;
- canonical `HumanitarianIncident`, lifecycle transitions and current Drift ownership;
- Source Registry, Coverage Matrix, preservation policy, correlation decisions and lineage edges;
- Alarm Phone image/OCR V2 and Humanitarian privacy boundaries;
- Live 24h operational projection and Play archive;
- Sentinel/VIIRS evidence;
- shared Live/Play vessel triangles;
- IncidentWatch v0;
- OSINT evidence-lineage classification and real source-independence semantics;
- deterministic VesselContext, versioned BehaviouralBaseline and `expected | unusual | insufficient_history` BehaviourAssessment.

Inspect actual `main`, migrations, merged PRs and tests before changing historical work described in `docs/fixes.md`.

## Current task

The immediate packet is **Observation -> Episode -> Hypothesis v1**. Its approved design and implementation plan are:

- `docs/superpowers/specs/2026-09-06-observation-episode-hypothesis-v1-design.md`
- `docs/superpowers/plans/2026-09-06-observation-episode-hypothesis-v1.md`

Current invariant:

```text
observation != episode
multiple detectors != multiple independent sources
behaviour context != corroboration
low-specificity single-lineage evidence != intelligence hypothesis
new v1 hypothesis -> exactly one persisted episode
```

Required behavior:

- persist deterministic/replayable `MaritimeEpisodeDB` under migration `0021_maritime_episodes`;
- add nullable `InvestigationHypothesisDB.episode_id`, where NULL explicitly marks legacy/pre-v1 rows;
- never mutate or silently relink legacy hypothesis rows;
- use `unclassified_episode` for unknown maritime anomalies; Safety is explicit only;
- carry parent observation IDs, derived feature IDs, evidence fingerprint, lineage groups, verification status, behaviour context and alternative explanations on the Episode;
- create low-specificity gap/rendezvous/infrastructure hypotheses only with genuine independent corroboration;
- allow high-specificity deterministic spoofing to remain candidate on one lineage, never to advance on detector count;
- give every new hypothesis `hyp:v1:*` identity and non-null episode ID;
- persist Episode before interpretation so hypothesis-ineligible events remain auditable;
- expose only bounded, identity-free observability labels for Episode and v1 hypothesis decisions;
- preserve YOUR WISDOM as a generic benign-service regression, never a whitelist or hard-coded suppress rule.

## Order after this packet

After Observation -> Episode -> Hypothesis v1 is merged and production-verified, implement the already-designed **Review v0**. PostGIS / Section 10 follows Review. Sensor/collector expansion remains after the reasoning/review foundation.

## Non-negotiable constraints

- Humanitarian privacy remains authoritative; no MMSI/IMO/callsign leakage into public Humanitarian surfaces.
- Vessel class is context, never an allegation.
- Safety observations never become Humanitarian or Intelligence by fallback.
- Observation, incident/episode, assessment/hypothesis, review and publication remain distinct objects.
- AI/models may assist but never silently become canonical truth.
- Every durable analytical object is replayable and provenance-linked.
- Evidence independence is determined by lineage, not detector count or provider display name.
- One semantic authority per PR; TDD first; exact-commit verification before merge.
- Preserve the shared Live/Play vessel-marker contract and existing public UI semantics unless a packet explicitly targets them.
- No production migration, restart or destructive maintenance without explicit operator approval.
