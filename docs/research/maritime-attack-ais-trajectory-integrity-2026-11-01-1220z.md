# SeaCommons maritime incident correlation — AIS trajectory integrity audit

Date: 2026-11-01 ~12:20 UTC. Branch: `feature/maritime-attack-correlation-20261030`.
Previous head: `0dc07f35`. Scope: staging code, read-only public APIs, and official-document verification. No production deploy, no Oracle writes, no VM scheduling.

## Implemented changes

- `apps/api/core/intel/maritime_attack_ais_context_readonly.py`: fail closed on an AIS event timestamp more than five minutes after its collector receipt clock; fail closed on simultaneous incompatible positions or an impossible jump between adjacent fixes (80 kn plus 2 km allowance). A rejected batch returns no partial fixes, and preserves suspect `vessel_tracks.id` values for audit.
- `tests/test_maritime_attack_ais_context_readonly.py`: four regressions covering impossible receipt chronology, permitted five-minute skew and delayed receipt, geographic teleport, and contradictory same-timestamp fixes.
- These checks assess AIS quality only. They do not prove an attack, spoofing, an attacker, or an independent source.

Commits: `3ad3b2e4970a0ae85d1aac139cc6f1c8bb108951`, `c2ac7c371d79a1df3a5fd476798023dea150303c`.
CI: https://github.com/suezcanalxyz/seacommons/actions/runs/41305983711
At ~12:21 UTC, all four CI jobs succeeded. 297 maritime Python + 18 bulletin Python + 3 SQLite + 6 PostgreSQL = **324 Python tests PASS**; frontend taxonomy and Vite build succeeded.

## Public LIVE/PLAY snapshot

GET at ~12:20 UTC, all HTTP 200:
- `https://play.seacommons.org/api/v1/play/counts`: 3,570 total, 3,442 maritime, 128 humanitarian, generated 11:40:41 UTC.
- `https://play.seacommons.org/api/v1/play/incidents?limit=1`: 3,570 total, generated 12:20:11 UTC.
- `https://live.seacommons.org/api/v1/live/pipeline`: generated 12:20:11 UTC; AIS, first-party and public feeds live; partner and radio degraded.

Counts and catalog agree on total, but the counts snapshot is ~39.5 minutes older. HTTP 200 does not certify the attack-correlation pipeline or a new incident color.

## Oracle read-only limitation

The authorized remote device is online. No newly certified Oracle PostgreSQL queries were completed in this execution; prior access to an application read-only role was blocked. No database counts from earlier runs are presented as fresh.

Recommended read-only checks, for an explicitly authorized database session:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '7000ms';
SELECT now() AT TIME ZONE 'UTC' AS snapshot_utc;
SELECT id, mmsi, ts, received_at, sog, lat, lon
FROM vessel_tracks
WHERE mmsi = '636019532'
  AND ts BETWEEN '2026-10-28 09:30:00' AND '2026-10-28 11:30:00'
ORDER BY ts, id LIMIT 257;
SELECT count(*) FROM intel_events WHERE created_at >= now() - interval '72 hours';
SELECT count(*) FROM alert_events WHERE created_at >= now() - interval '72 hours';
SELECT count(*) FROM anomaly_events WHERE created_at >= now() - interval '72 hours';
SELECT count(*) FROM humanitarian_incidents WHERE updated_at >= now() - interval '72 hours';
SELECT count(*) FROM forensic_events WHERE created_at >= now() - interval '72 hours';
SELECT count(*) FROM maritime_episodes WHERE created_at >= now() - interval '72 hours';
SELECT count(*) FROM source_observations
WHERE received_at >= '2026-10-01'
  AND (observation_type = 'official_maritime_bulletin'
       OR source_name ~* '(MSCIO|UKMTO|NAVAREA|NAVWARN|Bulgarian Ministry|MARAD|GDELT)');
ROLLBACK;
```

## Documentary candidates (not promoted)

- CONTSHIP JET, IMO 9348625, MMSI 636019532, 28 October 10:00 UTC. Bulgarian MOD primary report: https://www.mod.bg/news9664 . The ministry reports an observed attack and French patrol-plane warning; that shared ministry document is **one publication**, not two independent documentary sources. The published ministry text does not itself state IMO/MMSI: external vessel identity enrichment must remain separate from original-document claims. Previously observed AIS speed reduction 10.2 -> 0.6 kn is contextual only; actual Oracle receipt clocks remain unverified.
- MSCIO 158/26, 29 October 16:00 UTC, Hormuz: https://mscio.eu/alerts/194 .
- MSCIO 159/26, 29 October 22:12 UTC, Hormuz, published 30 October: https://mscio.eu/alerts/195 .
- MSCIO 162/26, 30 October 18:00 UTC, Arabian Gulf: https://mscio.eu/alerts/198 .
- MARAD 2026-012 Black Sea advisory: https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations . This is risk context, not a vessel-specific incident.

Publication clocks and collector receipt clocks are distinct. MSCIO/UKMTO syndication cannot automatically count as two independent origins. IMO and MSCIO redistribution restrictions still apply; no bulk ingestion.

## Next release gates

1. Verify Oracle `vessel_tracks.received_at` and trajectory integrity with a permitted read-only role; quarantine contradictions with original row IDs.
2. Separate primary Bulgarian bulletin vessel identity from externally sourced IMO/MMSI enrichment.
3. Ingest licensed bulletin metadata in isolated staging and test original-source lineage, separate attack/sinking episodes, and negative controls.
4. Certify end-to-end PLAY -> reviewed incident, with incident-specific color/category separate from humanitarian drift.
5. Require explicit production deployment approval.
