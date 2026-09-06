# Current work — Observation -> Episode -> Hypothesis v1

> **Runtime code baseline:** PR #152 merge `fbcdb55471af4b19f45dfc927146e7ea26dc08b2`
> **Production schema:** `0020_vessel_baselines`
> **Status:** OSINT Evidence Pipeline v1 and Vessel Context + Behavioural Baseline v1 are production-verified. Observation -> Episode -> Hypothesis v1 is the current release packet.

## Production state

The production reasoning chain currently includes durable SourceObservation/HumanitarianIncident, OSINT evidence lineage, and vessel-specific behavioural baselines. Production PostgreSQL is at `0020_vessel_baselines`; five bounded vessel baselines were audited after rollout. API, worker and Live edge publisher are active; `/ready`, Live and Play returned 200 after the baseline rollout.

Two unrelated operational warnings remain outside this packet: intermittent AISStream ping-timeout reconnects and the GFW `/v3/events` endpoint returning 404. They must not be reclassified as evidence failures.

## Public vessel contract

The public UI contract remains unchanged:

- moving and stationary vessels use the shared triangle marker;
- NGO colour is the intentional vessel-marker exception;
- Play reuses the Live vessel marker asset;
- Humanitarian public output does not expose MMSI/IMO/callsign/tracker dossier data.

## Current packet — Observation -> Episode -> Hypothesis v1

This packet corrects the remaining legacy assumption that detector count can stand in for evidence independence.

```text
SourceObservation / IntelEvent
  -> persisted MaritimeEpisode
  -> evidence lineage + BehaviourAssessment + alternative explanations
  -> hypothesis eligibility gate
  -> InvestigationHypothesis
  -> Review
  -> publication gate
```

Core rules:

- observations remain evidence authorities; an Episode is a deterministic, replayable derived object;
- migration `0021_maritime_episodes` creates `MaritimeEpisodeDB` and adds nullable `InvestigationHypothesisDB.episode_id`;
- legacy hypotheses remain untouched with `episode_id=NULL` and are never silently relinked;
- every new v1 hypothesis uses `hyp:v1:*` identity and a non-null episode ID;
- unknown maritime anomalies map to `unclassified_episode`; Safety is never a fallback;
- source independence comes only from the existing evidence-lineage classifier;
- behaviour context and alternative explanations remain analytical context, never an extra source;
- low-specificity gap/rendezvous/infrastructure patterns require genuine independent corroboration before a v1 hypothesis is created;
- high-specificity deterministic spoofing may create a candidate from one AIS lineage but cannot advance on detector count;
- Episode persistence occurs before interpretation, so benign/ineligible episodes remain auditable;
- bounded Prometheus counters report episode family/verification status and v1 hypothesis eligibility outcome without vessel identifiers.

## Regression contract

YOUR WISDOM remains a regression fixture, never a production whitelist. Normal recurring-service behaviour plus AIS gap/infrastructure indicators from one AIS lineage must remain `single_source_multi_indicator`, persist as internal analytical evidence, and produce zero new hypothesis, zero Case and zero public Intelligence allegation. A contrastive behavioural deviation remains `unusual` context but still obeys the evidence gate.

## Release verification completed on the branch

Fresh local verification has covered:

- full backend suite;
- focused Episode/hypothesis/replay/lineage regressions;
- canonical Ruff and mypy gates;
- Alembic fresh-head plus `0020 -> 0021 -> 0020 -> 0021` round-trip;
- Humanitarian stabilization/privacy contract;
- web lint/typecheck/tests/build;
- edge tests and Wrangler dry-run;
- Python/web/edge dependency audits;
- vessel-marker regression and shared built assets;
- hard-code scan for YOUR WISDOM/MMSI/IMO/Malta/Gozo production exceptions.

## Remaining gate before production

1. commit the final observability/docs alignment and rerun exact-head verification;
2. push one PR;
3. merge only after Full CI + CodeQL are green on the exact PR head;
4. production rollout is separate: backup PostgreSQL, migrate `0020 -> 0021`, supervised restart only with explicit operator approval, then `/ready`, Live/Play, Episode/Hypothesis counters and bounded production audit.

## Order after this packet

1. Review v0 on top of persisted Episodes and v1 hypotheses;
2. PostGIS / Section 10 after Review is verified;
3. expand real sensor/collector coverage only through explicit source contracts and provenance/independence rules.
