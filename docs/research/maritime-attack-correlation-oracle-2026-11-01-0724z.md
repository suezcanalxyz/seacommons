# Maritime attack correlation — 2026-11-01 07:24 UTC (staging only)

## Scope and baseline

Compared branch `feature/maritime-attack-correlation-20261030` with prior run `a592c402`: initially identical (0 ahead / 0 behind). This run adds isolated PostgreSQL reviewed-correlation regression tests and a same-IMO/multiple-incident regression. No production deployment or scheduler changes.

## Oracle read-only audit

Connection: existing authorized remote device; existing application PostgreSQL URL parsed locally without displaying credentials. All SQL executed through `psql -X -v ON_ERROR_STOP=1 -f -`, with `PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=8000'`, `BEGIN READ ONLY` and `ROLLBACK`. No mutations. Audit time 2026-11-01 07:21:21 UTC; rolling 72h window begins 2026-10-29 07:21:21 UTC.

| Read-only query / table | Result |
|---|---:|
| `intel_events` created in 72h | 3,923 |
| `alert_events` created in 72h | 0 |
| `anomaly_events` created in 72h | 0 |
| `humanitarian_incidents` created in 72h | 16 |
| `forensic_events` created in 72h | 13 |
| `maritime_episodes` created in 72h | 33 |
| `source_observations` from October through Nov 1 matching official source labels or `official_maritime_bulletin` type | 0 |
| `maritime_episodes` with family attack/incident/sinking/piracy created in October | 0 |
| CONTSHIP JET `vessel_tracks` for 27–29 Oct | 19, first 27 Oct 13:25:05 UTC, last 28 Oct 19:37:34 UTC |

Targeted `intel_events` name/MMSI audit (1 Oct–1 Nov inclusive) used PostgreSQL **word boundaries** to avoid substring collisions:

```sql
BEGIN READ ONLY;
SELECT count(*) FROM intel_events
WHERE timestamp_utc >= '2026-10-01' AND timestamp_utc < '2026-11-02'
  AND (title ~* '\\mRITI\\M' OR linked_mmsi = '352002473');
-- 0
SELECT count(*) FROM intel_events
WHERE timestamp_utc >= '2026-10-01' AND timestamp_utc < '2026-11-02'
  AND (title ~* '\\mCONTSHIP[[:space:]]+JET\\M' OR linked_mmsi = '636019532');
-- 7
ROLLBACK;
```

The seven CONTSHIP JET `intel_events` are **AIS-only anomalies**: two sudden-stop pairs on 5 and 16 October, an AIS gap on 19 October, a circular-track signal on 24 October, and an AIS gap on 26 October. **None is a document-backed attack event**; none of these pre-attack anomalies is independent corroboration of the 28 October attack. The earlier naive substring search for `RITI` matched unrelated names such as `KRITI`; the exact word-boundary audit returns **0**. Exact name searches for GHANA PROSPERITY and LEONORA KOSAN also return 0. Do not infer that those incidents did not happen.

## LIVE / PLAY public API

Read-only GET on `https://api.seacommons.org`, 2026-11-01 ~07:24 UTC:
- `/api/v1/play/counts`: HTTP 200, total **3,567**, maritime **3,440**, humanitarian **127**, generated 07:23:56 UTC.
- `/api/v1/play/incidents?limit=1`: HTTP 200, total **3,567**, generated 07:24:08 UTC; counts and catalog agree at audit time.
- `/api/v1/live/pipeline`: HTTP 200, generated 07:24:08 UTC; AIS, first-party and public feeds live, partner degraded.
- `/api/v1/live/sources`: HTTP 200, generated 07:24:09 UTC.
- `https://seacommons-edge.seacommons.workers.dev/health`: HTTP 200, status `ok`.

An earlier `/api/v1/play/counts` response at 07:23 UTC was generated at 05:51:59 UTC; a subsequent request regenerated the counts. Therefore endpoint HTTP 200 alone is not a freshness guarantee. This audit does not certify end-to-end attack promotion.

## Document candidates and independence

- CONTSHIP JET, IMO 9348625 / MMSI 636019532, 28 Oct 10:00 UTC: Bulgarian Ministry of Defence original release `https://www.mod.bg/news9664`. AIS slowing is context, **not a second attack source**.
- IMO confirmed-incident list `https://www.imo.org/en/mediacentre/hottopics/pages/middle-east-highlighted-incidents.aspx` as of 30 Oct reports **122** confirmed incidents and **24** seafarer fatalities. Its October entries include GHANA PROSPERITY (IMO 9732541) on **3 Oct and 23 Oct**, and LEONORA KOSAN (IMO 9390953) on **23 Oct**. The same IMO on two dates is not the same episode. The IMO listing does not prove that an MSCIO notice has independent upstream provenance.
- MSCIO alert 163/26 `https://mscio.eu/alerts/199`: published 30 Oct but reports an event on 28 Oct; publication timestamp must not be mistaken for incident time.
- UKMTO and MSCIO bulletin licensing/republication restrictions must be checked per publisher. No mass scraping or redistribution was initiated. IMO listing remains external research evidence, not a bulk-ingested licensed dataset.

## Changes and CI

1. `tests/test_official_maritime_bulletin_postgres.py`: two tests exercise the real canonical PostgreSQL writer through the **reviewed DB correlation** path; distinct publisher labels cannot create verified independent sources, and an anchorage/publication-only notice cannot become an attack.
2. `tests/test_maritime_attack_correlation.py`: GHANA PROSPERITY 3/23 October same-IMO separate-episode regression, both arrival orders.
3. This audit document.

GitHub Actions run `41284529907` succeeded for commit `03e7bf070022b5625b55a98d9e2c1877cf281224`: 269 maritime Python unit tests + 18 adapter unit tests + 3 SQLite writer tests + 5 ephemeral PostgreSQL tests = **295 Python tests**, plus frontend JavaScript tests and build. The prior commit `e6457aa3dd40dbccab3c49b23922311018583923` also passed.

The PostgreSQL CI service is disposable and separate from Oracle; every test rolls back. No collector, cron, timer, background loop, production write, migration or deployment was introduced.

## Remaining gates

- Add legally authorized official-bulletin ingestion and operator-reviewed source-origin lineage to staging (not to the Oracle production database).
- Confirm AIS / incident geospatial uncertainty and independent authority chains with primary documents.
- Run a staging end-to-end PLAY candidate -> operator review -> incident promotion test with explicit audit trail and separate UI category/color.
- Keep production untouched until explicit approval.
