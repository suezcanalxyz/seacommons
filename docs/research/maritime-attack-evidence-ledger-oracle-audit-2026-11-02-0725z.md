# SeaCommons maritime attack correlation — source evidence ledger and read-only audit

Audit time: 2026-11-02 07:25–07:29 UTC. Scope: attack-correlation feature branch only. No production deployment, DB mutation, historical overwrite, or new VM cron/timer/loop. Existing unrelated dirty VM working tree left untouched; tests run in a temporary detached worktree and cleaned up.

## Compared with previous run

Previous branch head: `90ebb4a6` (2026-11-02 06:23 UTC). This run added a deterministic, bounded **source evidence ledger** to the staging case-review bundle, including source URL, source rights, original report ID, canonical observation ID, document digest if actually available, metadata digest, exact/day-only event and publication clocks, canonical receipt, and source-check date. The ledger SHA-256 is explicitly a *derived snapshot fingerprint*, **not** a signed original-document digest, independent corroboration, or permission to republish. It is deterministic under follow-up reordering and changes if source provenance changes.

A follow-up investigation/rescue with a precise event clock is now rejected when it predates the attack, postdates its publication day, or conflicts with its own event date. A rescue/investigation location cannot be smuggled into the case as the attack site. The attack's geometry remains null unless directly evidenced. Context notices, wrecks and AIS do not become independent attack witnesses.

Files changed:
- `apps/api/core/intel/maritime_attack_staging_case_review.py`
- `tests/test_maritime_attack_staging_case_review.py`

Commits: `f29bc1db`, `76ef62f1`, `0a4158bb`, `2907dbef`.
The isolated staging case-review suite passed 19 tests, including missing/tampered provenance, day-only clock preservation, negative follow-up clocks, fake attack-site roles, foreign MMSI, duplicate reports, and unapproved publication.

## Oracle PostgreSQL read-only, rolling 72-hour window

At 2026-11-02 07:25:45 UTC, cutoff `2026-10-30T07:25:45`. Existing application connection, `PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=8000'`. No credentials recorded.

| Query / table | Result | Prior 06:22 UTC |
|---|---:|---:|
| `intel_events`, `left(timestamp_utc,19) >= cutoff` | 10,093 | 10,070 |
| `vessel_tracks`, `ts >= now() - interval '72 hours'` | 803,439 | 802,844 |
| `alert_events`, varchar clock via `left(timestamp_utc,19)` | 0 | 0 |
| `anomaly_events`, varchar clock via `left(timestamp_utc,19)` | 0 | 0 |
| `humanitarian_incidents`, `updated_at >= now()-interval '72 hours'` | 21 | 21 |
| `forensic_events`, varchar clock via `left(timestamp_utc,19)` | 11 | 11 |
| `source_observations` matching official maritime bulletin / named official sources since Oct 1 | 0 | 0 |
| `maritime_episodes` attack/piracy/sinking/explosion families | 0 | 0 |

These are *moving windows*; differences +23 intelligence and +595 AIS are not a measurement of new ingestion. The initial direct SQL timestamp comparisons for varchar fields failed with a type mismatch; they were rerun using the documented lexical ISO-clock approach and returned the counts above.

CONTSHIP JET IMO 9348625 / proposed external MMSI 636019532: five real AIS observations from 28 Oct 09:45–11:10 UTC, SOG 10.2 kn at 09:59:22 and 0.6 kn at 10:34:46, confirming a contextual slowdown and 35.396-min sampling gap. These **do not prove the attack**. Bulgarian MOD 28 Oct 10:00 UTC attack and three observed impacts: https://www.mod.bg/news9664 . Bulgarian VTMIS NAVWARN 768/26 reports the later sinking at 20:30 UTC and IMO 9348625, not a second attack: https://www.vtmis.bg/wx/wx_eng.htm . Original bulletin does not assert the MMSI. Independent attack witness count remains zero in the staging case review; no attacker attribution.

## Public API (07:25–07:29 UTC)

- `/api/v1/play/counts`: 3,578 total, 3,449 maritime, 129 humanitarian; snapshot 07:03:01 UTC.
- `/api/v1/play/incidents?limit=100&offset=...`: 3,578 rows, **3,572 unique IDs**, zero attack/piracy category matches in returned rows. Concurrent offset pagination is not a consistent snapshot, so do not claim exhaustive unique coverage.
- `/api/v1/live/signals?limit=200&days=3&mode=all`: 16 signals, zero attack/piracy text matches.
- `/api/v1/live/pipeline`: AIS/first-party/public-feed/radio live; partner degraded; DSC accepted 60; NAVTEX accepted 0.

## Source research and October candidates

New Black Sea retrospective leads, **not yet imported to canonical source_observations**:
- **ABLE**, attacked on 6 October, examined by Bulgarian Defence Ministry 9 October. Official report: https://www.mod.bg/news9637 . The minister reports severe fire/flooding and explicitly declines to attribute the drone operator without physical evidence. The report does not itself establish IMO/MMSI or the attack's precise time. Bulgarian Telegraph Agency cites ArmyMedia for IMO 9001136: https://www.bta.bg/en/news/1218507-two-merchant-ships-attacked-by-sea-and-aerial-drones-in-bulgaria-s-exclusive-eco . Treat vessel crosswalk as separately sourced and unreviewed.
- **ALFA WATAN**, a *different* ship in the 6 October two-vessel attack; BTA cites ArmyMedia for IMO 7510884. Reported sinking and missing crew must not be merged with ABLE or treated as confirmed deaths: same BTA source and Reuters 7 October https://www.reuters.com/world/europe/bulgaria-halts-rescue-operation-crew-sunken-ship-2026-10-07/ .
- CONTSHIP JET 28 October: distinct incident, official MOD and VTMIS as above.
- MSCIO 162/26, 30 October 18:00 UTC: unidentified vessel, projectile/fire near Lavan Island, candidate only: https://mscio.eu/alerts/198 .
- MSCIO 159/26, 29 October ~22:12 UTC: limpet-mine attack near Khasab, potential vessel LOUISE 1 per Reuters but identity not certified by original MSCIO notice: https://mscio.eu/alerts/195 and https://www.reuters.com/world/tanker-strait-hormuz-hit-by-limpet-mines-security-sources-say-2026-10-30/ .
- MSCIO 161/26, AZINI, 29 October piracy: https://mscio.eu/alerts/197 . No automatic geolocation from last-known position.
- 1 November IRGC claim of two tankers striking mines in Hormuz, Reuters report https://www.reuters.com/world/middle-east/irans-irgc-navy-says-two-tankers-exploded-after-hitting-mines-hormuz-2026-11-01/ . Unidentified vessels and no independent confirmation in this audit. Do not create two corroborated attacks.

The 6 October ABLE/ALFA WATAN evidence is newly surfaced in this audit; **not** counted as a new last-72h incident.

## Source availability from authorized VM, one-shot GET

| Source | Status | Approx. HTTP response time |
|---|---|---:|
| Bulgarian MOD | 200 | 1,126 ms |
| Bulgarian VTMIS | 200 | 139 ms |
| Bulgarian Transport | 200 | 253 ms |
| MSCIO | 200 | 272 ms |
| IMO | 200 | 198 ms |
| UKMTO | 403 | 36 ms |
| MARAD | 403 | 24 ms |
| NATO Shipping Centre | 403 | 27 ms |
| ONI | 403 | 489 ms |
| GDELT DOC API | 200 on first request (~12.9 s), 429 on immediate retry (~9.3 s) | unstable / rate-limited |

HTTP 200 does not establish data validity, licensing or reliable ingest. Do not bypass 403 or 429. HTTP latency is not source publication-to-receipt latency. Rights must be reviewed individually: MSCIO republication is restricted, UKMTO declares Open Government Licence subject to conditions and third-party rights; Bulgarian MOD permits public copying with attribution; original NAVWARN reuse rights have not been certified. No collector scheduled or enabled.

## Boundaries and next step

Staging-only source review and negative tests have improved. No official bulletins are yet ingested in the production canonical observation pipeline; no attack is published in LIVE/PLAY. Next: establish a dedicated, authenticated staging review surface backed by isolated PostgreSQL; obtain original document hashes and reliable IMO/MMSI crosswalk evidence; test independent-origin lineage; only then consider explicitly approved promotion. Never infer attack sites from AIS/wreck coordinates or attackers from speculation.
