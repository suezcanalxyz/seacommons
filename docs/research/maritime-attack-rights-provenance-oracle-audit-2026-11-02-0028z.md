# SeaCommons — attack correlation: canonical source rights and Oracle audit
**UTC audit:** 2026-11-02 00:23–00:29. **Staging branch:** `feature/maritime-attack-correlation-20261030`. **Previous reported HEAD:** `e0cc79ad`. **Functional HEAD:** `342aff35`. No production deployment.

## Implementation — a lost-provenance defect fixed
The six-source metadata-only staging manifest already classified reuse restrictions and recorded the source-check date. However, these fields were only held in `StagingSourceRecord`: `ingest_official_bulletin(db, record.bulletin)` discarded them before writing the immutable canonical `SourceObservation`. The problem matters for MSCIO bulletins marked `restricted_republication`; a later projection cannot safely infer reuse rights from a URL or a generic `reuse_rights_verified=False` flag.

Changes:
1. `OfficialMaritimeBulletin` now accepts optional `source_rights` (closed vocabulary: `public_with_attribution`, `restricted_republication`, `unknown`) and `source_checked_on_utc` (date, not datetime). Reject non-string, forged or inconsistent metadata and source-check dates before any writer call.
2. `prepare_official_bulletin` stores both fields in canonical `provenance`. `source_rights` is included in the immutable reviewed revision payload; `source_checked_on_utc` is deliberately **not** included in the source payload/hash because rechecking the same document the next day is not a second observation. Legacy callers without optional metadata retain their previous `source_id` and payload.
3. `prepare_staging_bulletin_manifest` now passes both fields to the canonical adapter. The manifest's existing six documents remain review-only: `attack_corroboration_allowed=False`, `origin_authority_verified=False`, `reuse_rights_verified=False`, `publication_allowed=False`.
4. Unit and isolated PostgreSQL regressions verify that the metadata survives the actual writer; a next-day check replays the same immutable observation and retains the **first** check date. No restricted MSCIO full text is stored or redistributed. No new collector, scheduler, database table or episode writer was introduced.

Modified files: `apps/api/core/intel/official_maritime_bulletin.py`, `apps/api/core/intel/maritime_attack_staging_manifest.py`, `tests/test_maritime_attack_staging_manifest.py`, `tests/test_official_maritime_bulletin.py`, `tests/test_official_maritime_bulletin_postgres.py`.

## Oracle PostgreSQL read-only audit
Existing authorized application connection; `PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=9000'`; bounded SELECT only. No role/credential/privilege changes. Window: 2026-10-30 00:22:37 UTC to 2026-11-02 00:22:37 UTC.

| Canonical table | 72-hour query result |
| --- | ---: |
| `intel_events` | 9,745 |
| `vessel_tracks` | 799,583 |
| `alert_events` | 0 |
| `anomaly_events` | 0 |
| `humanitarian_incidents` (updated, not new distress) | 21 |
| `forensic_events` | 11 (10 distress, 1 resolved) |

No `official_maritime_bulletin` or `operator_incident_statement` observations in the Oct 1–Nov 2 `source_observations` search; no `attack`/`piracy`/`sinking` canonical `maritime_episodes` family. Exact-name/text search in `intel_events` found no CONTSHIP JET or AL MAYEDA in the checked late-October period. A broad keyword query returned 452 rows but was dominated by AIS status/gap events; it is **not** a count of attacks.

Representative SELECTs (each executed with read-only connection settings):
```sql
SELECT count(*) FROM intel_events WHERE timestamp_utc >= '2026-10-30T00:22:37';
SELECT count(*) FROM vessel_tracks WHERE ts >= '2026-10-30 00:22:37';
SELECT count(*) FROM alert_events WHERE timestamp_utc >= '2026-10-30T00:22:37';
SELECT count(*) FROM anomaly_events WHERE timestamp_utc >= '2026-10-30T00:22:37';
SELECT count(*) FROM humanitarian_incidents WHERE updated_at >= '2026-10-30 00:22:37';
SELECT count(*) FROM forensic_events WHERE timestamp_utc >= '2026-10-30T00:22:37';
SELECT source_name, count(*) FROM source_observations
 WHERE observed_at >= '2026-10-01' AND observed_at < '2026-11-03'
 AND observation_type IN ('official_maritime_bulletin','operator_incident_statement')
 GROUP BY source_name;
SELECT episode_family,count(*) FROM maritime_episodes
 WHERE lower(episode_family) LIKE '%attack%'
    OR lower(episode_family) LIKE '%piracy%'
    OR lower(episode_family) LIKE '%sinking%'
 GROUP BY episode_family;
```

**CONTSHIP JET regression** (IMO 9348625; MMSI 636019532): `vessel_tracks` reports 2026-10-28 09:57:55 10.8 kn; 09:59:22 10.2 kn; 10:34:46 0.6 kn; 10:46:24 0.7 kn; 10:58:15 0.8 kn. The Bulgarian Ministry of Defence `news9664` reports three observed impacts at 12:00 Bulgarian local time (10:00 UTC). The original MOD report does **not** state IMO/MMSI. In the legacy AIS rows, `received_at == ts`, so no true ingestion latency can be inferred. Speed change is a contextual signal, **not proof** of an attack or attacker identity.

**AL MAYEDA** (reported MMSI 538003356): 0 `vessel_tracks` rows in the Oct 1–Nov 2 window queried. Do not manufacture a trajectory or join to MSCIO 162/26 without matching original identifiers, positions and timestamps.

## LIVE/PLAY public API audit
Public `/api/v1/play/counts`: 3,576 total (3,447 maritime; 129 humanitarian; 3,437 investigation), cached at 2026-11-01 23:41 UTC. Full paginated scan of **all 3,576** PLAY incident records: **0 attack-labeled** `incident_type`/`visual_category`/`episode_family`. Public `/api/v1/live/signals?days=3&mode=all&limit=150`: 13 signals, **0 attack-labeled**. This does not imply no real attacks; it demonstrates the official bulletin ingestion/promotion path is not operational in production.

LIVE pipeline: AIS, first-party, public feeds and radio `live`; partner `degraded`. Decoder counters `dsc_accepted=48`, `navtex_accepted=0`; NAVTEX acquisition remains unproven.

## Source availability and rights (one HEAD each from Oracle, 2026-11-02 ~00:25 UTC)
| Source | HEAD | Request RTT | Interpretation |
| --- | --- | ---: | --- |
| Bulgarian MOD news9664 | 200 | 559 ms | Public information may be copied with explicit attribution (site footer). |
| MSCIO 159/26 | 200 | 320 ms | Metadata/link only; redistribution conservatively restricted. |
| MSCIO 162/26 | 200 | 221 ms | Metadata/link only; redistribution conservatively restricted. |
| IMO confirmed-incidents page | 200 | 180 ms | Aggregated context; not an independent original witness for each incident. |
| UKMTO | 403 | 34 ms | Direct Oracle retrieval blocked. |
| MARAD | 403 | 20 ms | Direct Oracle retrieval blocked; web-readable advisory 2026-012 is regional context. |
| NATO Shipping Centre | 403 | 48 ms | Direct Oracle retrieval blocked. |
| ONI | 403 | 22 ms | Direct Oracle retrieval blocked. |
| GDELT DOC API | TLS handshake timeout | ~8128 ms | No usable observation or collector-latency measurement. |

These are HTTP round-trip times, **not** publication-to-ingestion delays. No bypass of HTTP restrictions, mass scraping or automatic redistribution. Source links:
- https://www.mod.bg/news9664
- https://mscio.eu/alerts/194 (158/26); https://mscio.eu/alerts/195 (159/26); https://mscio.eu/alerts/196 (160/26 negative control); https://mscio.eu/alerts/197 (161/26 piracy); https://mscio.eu/alerts/198 (162/26)
- https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations
- https://www.imo.org/en/mediacentre/hottopics/pages/middle-east-highlighted-incidents.aspx

## Candidate queue and epistemic limits
- **BG_MOD news9664 / CONTSHIP JET**, 28 Oct 10:00 UTC, Black Sea: documented military observation; name-only in primary source; external IMO/MMSI link for review; AIS speed change not proof; no attacker attribution.
- **MSCIO 158/26**, 29 Oct ~16:00 UTC, Hormuz: unnamed tanker reportedly struck, no strong vessel ID.
- **MSCIO 159/26**, 29 Oct ~22:12 UTC, Hormuz: unnamed tanker, two explosive devices reported; UKMTO coverage may share an upstream source.
- **MSCIO 160/26**, 30 Oct ~02:25 UTC, Gulf of Aden: suspicious approach without shots/boarding; **negative attack control**.
- **MSCIO 161/26 / AZINI**, event 29 Oct, piracy/hijacking; keep later positions distinct from event site.
- **MSCIO 162/26**, 30 Oct ~18:00 UTC, Arabian Gulf: unnamed vessel, reported impact/fire; do not automatically merge with AL MAYEDA.
- **AL MAYEDA**, reported 30 Oct evening, Gulf: operator reports unknown objects; no matching AIS rows in queried canonical track window, no verified second independent witness.
- **Two unnamed tankers reportedly struck by mines**, 1 Nov, Strait of Hormuz: Reuters attributes the statement to Iran's IRGC Navy; **unverified single-origin claim**, no ship identifiers or independent corroboration. Do not promote.

## Remaining gates
1. The six-document manifest and canonical writer are exercised **only** in disposable PostgreSQL CI. No operational staging database import has been authorized/performed; Oracle remains untouched.
2. Source-document identity, independent original witness groups and exact publication/receipt clocks still require review before any promotion.
3. Implement and test an opt-in, reviewed candidate episode in isolated staging, then a non-public PLAY preview with distinct attack taxonomy. No production deployment without approval.

No deletions, historical mutations, production deployment, new VM cron/timer/loop or automatic promotion.
