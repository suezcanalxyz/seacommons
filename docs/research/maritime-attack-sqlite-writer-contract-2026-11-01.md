# Maritime attack correlation — staging writer contract and LIVE/PLAY audit

**Observed 2026-11-01 ~05:18–05:20 UTC.** Branch `feature/maritime-attack-correlation-20261030`; previous head `a31db9e352420f800824d512cf251df9e233bef6`. No production deployment, VM writes, scheduled jobs, or production DB mutations.

## Concrete integration blocker fixed

`SourceObservationDB.source_policy` is `String(32)`, but `official_maritime_bulletin.prepare_official_bulletin` emitted `official_bulletin_metadata_only_reuse_unverified` (**48 characters**). SQLite silently permits oversized VARCHAR values, while PostgreSQL rejects them. This meant the adapter's previously green pure-unit tests did not prove that `record_observation` could persist a bulletin on PostgreSQL.

The adapter now emits `official_metadata_unverified` (**28 characters**), preserving the conservative policy semantics and the original `reuse_rights_verified=False` provenance. The new integration test explicitly checks every bounded string against ORM column lengths so SQLite cannot conceal the same bug.

## Actual isolated canonical-writer integration

New `tests/test_official_maritime_bulletin_sqlite.py` runs the **real** `ingest_official_bulletin -> record_observation -> SourceObservationDB + reported_by entity graph` path in an in-memory SQLite database. It checks CONTSHIP JET (IMO 9348625, MMSI 636019532, event 2026-10-28 10:00 UTC), idempotent replay, append-only document revisions, source metadata, provenance and non-publication flags, graph edge count, zero manufactured lineage, transaction rollback, and RITI anchorage/unknown event time. It deliberately creates no `intel_events` or `maritime_episodes` tables. This does not simulate the PostgreSQL server or prove PLAY promotion.

The branch-only GitHub Actions workflow installs SQLAlchemy **only** for this ephemeral integration job. No Oracle credentials or external database are configured. No VM cron, timer or loop was added.

**GitHub Actions run 41276412545: SUCCESS (2026-11-01 05:18 UTC).** `correlation-unit`: 268 + 18 = **286** Python tests; `bulletin-writer-sqlite`: **3/3** tests; frontend taxonomy and Vite build: SUCCESS. **289 Python tests total**, five JavaScript tests (existing suite), build successful. Previous intermediate commit 890869c failed because its unit assertion still expected the oversized policy; subsequent commits fixed the assertion and completed the integration job.

## Oracle and LIVE/PLAY status

Authorized device `instance-20260828-1159` online. The direct `psql -d seacommons` command failed with `role "ubuntu" does not exist`; a `sudo -u postgres` command was denied by the remote tool's command policy. No bypass was attempted. **New PostgreSQL read-only queries completed this run: 0.** Last verified Oracle table counts are from the earlier 2026-11-01 04:21 UTC audit; do not present those as fresh measurements.

Local API read-only GET checks at ~05:18–05:19 UTC:
- `/api/v1/play/counts`: HTTP 200; 3,566 total, 3,439 maritime, 127 humanitarian, 3,429 investigation; generated 05:18:35 UTC.
- `/api/v1/play/incidents?limit=1`: HTTP 200; catalog reports **3,567** total, generated 05:19:07 UTC.
- `/api/v1/live/pipeline`: HTTP 200; AIS, first-party and public-feed families live; partner and radio degraded at the sampled moment.
- Catalog/count discrepancy is **one item** at differing generation times; not enough evidence to call it a persistent bug, but requires same-snapshot validation before certifying freshness.

The live production deployment is **unchanged**. The new official bulletin adapter remains branch-only and is not a production collector.

## Candidate register and provenance limits

- **CONTSHIP JET** (IMO 9348625, MMSI 636019532): Bulgarian MOD original https://www.mod.bg/news9664 (28 October; 10:00 UTC incident). AIS slowdown in the earlier Oracle audit is context, **not** independent proof. Reuters reporting/verified video needs origin review; no attacker attribution.
- **RITI** (IMO 9249075, MMSI 352002473): Pakistan NAVAREA IX **420/26**, 30 October, https://hydrography.paknavy.gov.pk/navarea-ix-warnings/ . Its anchorage position is not automatically the attack site; warning issue time is not necessarily event time.
- **MSCIO 159/26, 162/26, 163/26**: reported attack/impact candidates; event and publication times must remain distinct, especially 163/26 (28 Oct event, 30 Oct publication). No verified independent second source or vessel resolution. Source: https://mscio.eu/ .
- **UKMTO 190/26 / MSCIO 161/26 AZINI**: possible shared original reporting chain; do not merge or count twice without verified vessel identity and lineage.
- **KHORYV** (IMO 8138712): capsized/drifting NAVWARN, negative attack control, distinct from CONTSHIP JET.

**Reuse rights:** UKMTO terms https://www.ukmto.org/terms-and-conditions allow reuse under the Open Government Licence, subject to exclusions and attribution. MSCIO https://mscio.eu/terms-of-service/ restricts redistribution/publication. NAVAREA IX explicitly warns that reports may come from incomplete sources; public access alone is not a second independent observation. No automated scraping or restricted text redistribution enabled.

## Next verification gates

1. Restore an explicitly authorized read-only PostgreSQL path (least-privilege credential/role) and query the six requested tables plus `source_observations`, `lineage_edges`, `maritime_episodes` using `BEGIN READ ONLY; SET LOCAL statement_timeout='6000ms'; ... ROLLBACK`. No role escalation.
2. Exercise the adapter against a **separate PostgreSQL staging database**, not Oracle production, to confirm dialect constraints, rollback and lineage.
3. Add an operator-reviewed, rights-compliant source connector without any VM scheduler; validate independent original reporting authorities and event/publication/receipt clocks.
4. Compare the LIVE/PLAY counts from one shared snapshot and prove reviewed candidate -> episode -> PLAY presentation, then require explicit approval before any production deployment.
