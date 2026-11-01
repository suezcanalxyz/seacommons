# SeaCommons official maritime bulletin adapter — staging audit, 2026-11-01

**Scope:** branch-only implementation; Oracle PostgreSQL and LIVE/PLAY **read-only** audit. No VM file writes, scheduling, production deployment, case promotion or historical edits. This report supplements `maritime-attack-oracle-readonly-audit-2026-11-01.md`.

## Comparison with previous execution

Previous staging head: `394423e4e436a6d174d86ff8f8e31fe6d2ef708b`, 268/268 Python tests and successful staging CI. The new work adds `apps/api/core/intel/official_maritime_bulletin.py`, `tests/test_official_maritime_bulletin.py` and extends the existing staging CI workflow. This adapter is **not yet wired to an automatic collector**; it is an opt-in staging entry point for already reviewed structured bulletin metadata.

## Oracle: bounded SELECT-only observations, 2026-11-01 around 02:16–02:19 UTC

Connection was opened from the authorized Oracle device with `BEGIN READ ONLY`, `SET LOCAL statement_timeout = 6000/8000` and a transaction rollback. No credentials were displayed. Database: `seacommons`, `transaction_read_only=on`.

- Since 2026-10-29 00:00 UTC, `source_observations` contains 52,217 records (a slightly broader window than an exact rolling 72 hours). Latest receipt: **2026-11-01 02:16:49 UTC**. Largest sources: AISStream 51,430; GFW 559; GDACS 79. These counts are **not incident counts**.
- Since 2026-10-01, source name / original-source URL search for MSCIO, UKMTO, NAVAREA, NAVWARN, Bulgarian MOD, MARAD and GDELT in `source_observations` returned **0**. The prior audit also found 0 corresponding `intel_events` by source identity. This is a missing documented-source ingestion path, not evidence that attacks did not occur.
- `maritime_episodes` families matching `attack|incident|sinking|piracy`: **0**.
- CONTSHIP JET (MMSI 636019532): **19** AIS fixes from 27–28 October, 0.6–12.7 kn; the 09:59:22 UTC fix at 10.2 kn and 10:34:46 UTC fix at 0.6 kn bracket the externally reported 10:00 UTC attack. AIS is context, **not** a second corroboration.
- RITI (MMSI 352002473): **0** fixes 27–31 October. Do not infer an intentional AIS gap without coverage baseline.
- `alert_events`: 4 historical rows, latest created 2026-08-28; `anomaly_events`: 0 rows. Since October, `humanitarian_incidents` include distress and missing categories; `forensic_events` include 75 distress and 5 sar_osint rows. None establishes an attack.
- `lineage_edges`: 7,143 total, latest 2026-11-01 01:16:51 UTC; this is an overall graph count, **not** 7,143 independent incident sources.

Read-only SQL examples:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = 8000;
SELECT source_name, count(*) FROM source_observations
 WHERE received_at >= timestamp '2026-10-29 00:00:00'
 GROUP BY source_name ORDER BY count(*) DESC LIMIT 15;
SELECT count(*) FROM source_observations
 WHERE received_at >= timestamp '2026-10-01'
 AND (source_name ~* '(mscio|ukmto|navarea|navwarn|bulgar|marad|gdelt)'
      OR source_url ~* '(mscio.eu|mod.bg|hydrography.paknavy.gov.pk)');
SELECT episode_family, verification_status, count(*) FROM maritime_episodes
 WHERE episode_family ~* '(attack|incident|sinking|piracy)'
 GROUP BY 1,2 LIMIT 15;
SELECT count(*),min(ts),max(ts),min(sog),max(sog) FROM vessel_tracks
 WHERE mmsi='636019532' AND ts >= timestamp '2026-10-27'
 AND ts < timestamp '2026-11-01';
ROLLBACK;
```

## LIVE/PLAY GET-only verification

HTTP 200 on `/api/v1/live/pipeline`, `/api/v1/live/sources`, `/api/v1/play/cache-status`, `/api/v1/play/counts` and `/api/v1/play/incidents?limit=2` from local API on 2026-11-01 around 02:19 UTC. PLAY reports **3,566** catalog entries (127 humanitarian, 3,439 maritime), compared with 3,564 in the prior audit. Cache age improved from ~6,400 s to **155 s** (catalog) / **167 s** (counts); no cache errors reported. Radio is now shown `live` (prior audit: degraded), partner remains degraded. HTTP success and freshness do **not** establish incident-source completeness or end-to-end corroboration.

## Official bulletin source review

| Document | Event date/time UTC | Original source | Operational interpretation |
|---|---|---|---|
| CONTSHIP JET, IMO 9348625, MMSI 636019532 | 28 Oct 10:00 | Bulgarian Ministry of Defence, https://www.mod.bg/news9664 | Official attack claim; exact publication clock and SeaCommons receipt unknown. Single primary reporting chain pending independent review. |
| MSCIO 158/26 | 29 Oct 16:00 | https://mscio.eu/alerts/194 | Tanker reportedly struck in Hormuz; vessel IDs unknown. |
| MSCIO 159/26 | 29 Oct 22:12 | https://mscio.eu/alerts/195 | Tanker reportedly attacked with attached explosive devices; vessel IDs unknown. |
| MSCIO 162/26 | 30 Oct 18:00 | https://mscio.eu/alerts/198 | Projectile/fire in Arabian Gulf; vessel IDs unknown. |
| MSCIO 163/26 | 28 Oct, time unknown; published 30 Oct | https://mscio.eu/alerts/199 | Time-late attack report, NOT a new 30 Oct attack. |
| RITI, IMO 9249075, MMSI 352002473, NAVAREA IX 420/26 | Attack time unverified; warning issued 30 Oct 03:00 | https://hydrography.paknavy.gov.pk/navarea-ix-warnings/ | Incident and reported anchorage, NOT verified impact position. |
| UKMTO 185/26 | 29 Oct | https://www.ukmto.org/recent-incidents | Suspicious activity/dhow fire; NOT independently established attack. |
| KHORYV, IMO 8138712, NAVWARN 766/26 | 28 Oct 18:00 | Bulgarian navigational warning (see preceding audit) | Capsized/drifting vessel; no attack documented. Negative control. |

Public official pages were accessible during the source review. No complete official permission for automated scraping, full-text redistribution or bulk reuse has been established. Keep **metadata-only**, original links, dates, report IDs, provenance and document hashes when legally available. GDELT 2.0 advertises 15-minute data updates (https://www.gdeltproject.org/data.html), which is not the observed latency of SeaCommons.

## Implemented staging-only adapter

`prepare_official_bulletin` validates issuer/HTTPS host, bulletin ID, IMO checksum, MMSI format, timezones, date-only precision, coordinate ranges and uncertainty. It creates a stable document-revision delivery key, preserves event/publication timestamps separately, retains source URL and source-document SHA256 (if available), and explicitly sets `origin_authority_verified=False`, `reuse_rights_verified=False`, `attack_corroboration_allowed=False`. The source itself may be a relay, not an independent eyewitness.

`ingest_official_bulletin(db, bulletin)` is opt-in, uses the **existing** `record_observation` path and caller-owned transaction, and has no scheduler, fetch, new table or automatic PLAY/LIVE publication. It does **not** import the actual October source documents into Oracle yet. A verified extraction/lineage audit must precede `claim_from_source_observation` and any incident promotion.

Regression coverage includes CONTSHIP JET, RITI, MSCIO 159/26, MSCIO 160/26, UKMTO 185/26, hostile lookalike URLs, malformed IMO/MMSI, ambiguous dates, unknown positions, deterministic replay and immutable revisions.

## Next gates

1. Certify the new adapter and regressions in staging CI.
2. Validate the issuing authorities' terms and a compliant collector acquisition method; do not treat MSCIO/UKMTO/NAVAREA relays as independent originals.
3. Run an **explicit staging-only** trial of the canonical writer with a caller-owned test database and separately reviewed structured source metadata. No production writes.
4. Re-run read-only Oracle comparison, then test candidate-only PLAY projections, uncertainty and UI category separation. Promotion remains operator-gated.

No attacker attribution, no live publication, no new VM cron/timer/loop.
