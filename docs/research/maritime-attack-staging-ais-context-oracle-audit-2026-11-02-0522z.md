# SeaCommons — Maritime attack AIS staging context and Oracle read-only audit
**UTC audit:** 2026-11-02 05:22–05:26. **Scope:** `feature/maritime-attack-correlation-20261030`. **Production writes/deploys:** none.

## Change from previous run (d661f2fc)

Added `apps/api/core/intel/maritime_attack_staging_ais_context.py`, a pure staging-only adapter for an explicitly supplied vessel crosswalk and a bounded list of read-only VesselTrackDB rows. Added `tests/test_maritime_attack_staging_ais_context.py` with seven tests; added both paths to the existing staging CI workflow. No cron, daemon, collector, staging DB connection, production API or canonical episode writer was created.

The adapter:
- Requires an attack/piracy **candidate** preview with `staging_only=true` and `publication_allowed=false`; rejects humanitarian/context-only records.
- Validates IMO check digit, MMSI format, original reported vessel name, original-source identifier conflicts, canonical HTTPS crosswalk URL and all supplied AIS row MMSIs.
- Rejects conflicting AIS fixes sharing a timestamp; deduplicates identical fixes; bounds input to 256 rows and analysis to +/-3 hours of an event with an explicit UTC clock.
- Returns separate **AIS vessel-track** before/after coordinates and an observed speed-drop/sampling-gap *signal*. Never writes these coordinates into incident-site geometry and never counts AIS as an attack witness.
- Does not claim a verified vessel identity merely because a reviewer supplies an external crosswalk; `external_identity_requires_review` is explicit. No event-time precision means no speed-drop claim.
- Treats legacy `received_at == ts` as `legacy_equal_event_clock`, not an independently measured ingest latency.

## Real-data regression: CONTSHIP JET

Original case: CONTSHIP JET, IMO 9348625, MMSI 636019532, reported attack 2026-10-28 10:00 UTC. The Bulgarian MOD bulletin names the vessel but does not assert IMO/MMSI. The crosswalk must therefore remain a separately reviewed source, never an invented identifier in the primary bulletin.

Oracle read-only `vessel_tracks` query for MMSI 636019532, 2026-10-28 09:50–11:00 UTC:
- 09:57:55, 10.8 kn, 43.26831 / 28.8189467.
- 09:59:22, 10.2 kn, 43.2659267 / 28.8149000.
- 10:34:46, 0.6 kn, 43.2591967 / 28.8157400.
- 10:46:24, 0.7 kn, 43.2581067 / 28.8131967.
- 10:58:15, 0.8 kn, 43.2562433 / 28.8107600.

These rows exhibit a speed drop between 09:59 and 10:34 UTC, with a **35.4-minute AIS sampling interval**, but neither this speed drop nor an AIS gap is an attack proof. All five rows have `received_at == ts`; actual ingest latency cannot be measured from these legacy records. The unit regression uses the two bounding rows; it does not claim to have imported all five into staging.

Original Bulgarian MOD: https://www.mod.bg/news9664
Bulgarian prosecutor, investigation notice 2026-10-29: https://prb.bg/bg/news/aktualno/80101-voenno-okrazhna-prokuratura-sofiya-obrazuva-dosadebno-proizvodstvo-za-napadeniet
Reuters 2026-10-29 describes verified footage; its original custody and testimonial independence still require review: https://www.reuters.com/world/europe/greek-container-ship-sinks-after-drone-attack-off-bulgaria-2026-10-29/

## Oracle read-only 72h audit

At 2026-11-02 05:22 UTC, approximate rolling window starts 2026-10-30 05:22 UTC:
- `intel_events` 10,007; `vessel_tracks` 802,148; `alert_events` 0; `anomaly_events` 0; `humanitarian_incidents` updated 21; `forensic_events` 11.
- `source_observations` with `observation_type='official_maritime_bulletin'` and October `observed_at`: 0.
- `maritime_episodes` where family matches attack/piracy/sinking/explosion: 0.
- Targeted non-AIS `intel_events` title/text keyword query over 72h: 0 matches. This is a *query result*, not proof that no real incident occurred.

Example SQL used (each through PostgreSQL `PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=7000'`):
```sql
SELECT count(*) FROM intel_events
 WHERE timestamp_utc >= to_char((now() AT TIME ZONE 'UTC')-interval '72 hours',
                                'YYYY-MM-DD"T"HH24:MI:SS');
SELECT count(*) FROM vessel_tracks
 WHERE ts >= (now() AT TIME ZONE 'UTC')-interval '72 hours';
SELECT id,mmsi,ts,received_at,sog,lat,lon FROM vessel_tracks
 WHERE mmsi='636019532'
   AND ts BETWEEN '2026-10-28 09:50:00' AND '2026-10-28 11:00:00'
 ORDER BY ts LIMIT 20;
SELECT count(*) FROM source_observations
 WHERE observed_at >= '2026-10-01'
   AND observation_type='official_maritime_bulletin';
```
Note: `timestamp_utc` is a varchar column in several tables, not a timestamp. The ISO lexical query above was used after verifying the current format. The first attempt comparing varchar directly to timestamp failed and was corrected; no data changed.

## Public LIVE/PLAY (2026-11-02 05:23 UTC)

- PLAY paginated scan: **3,577** items; attack-category matches **0**. Cached `/api/v1/play/counts` says **3,576** (3,447 maritime; 129 humanitarian), generated at **04:22:40 UTC**. The count and catalog do not represent the same snapshot.
- LIVE `/api/v1/live/signals?limit=200&days=3&mode=all`: **13** signals (9 AIS gaps, 1 dark activity, 1 navigation safety, 2 distress), **0** attacks.
- LIVE pipeline at 05:23:39 UTC: AIS and first-party/public feeds live, partner degraded, **radio offline**, DSC accepted 58, NAVTEX accepted 0. Decoder alive does not prove end-to-end NAVTEX reception.

## Source checks (HEAD from Oracle, 2026-11-02 05:24 UTC)

| Source | Result | HTTP time (not publication-to-ingest latency) |
|---|---|---|
| Bulgarian MOD | 200 | 341 ms |
| Bulgarian prosecutor | 200 | 366 ms |
| MSCIO 159/26 | 200 | 268 ms |
| MSCIO 162/26 | 200 | 248 ms |
| IMO | 200 | 189 ms |
| NAVAREA III | 200 | 192 ms |
| UKMTO | 403 | 62 ms |
| MARAD | 403 | 21 ms |
| NATO Shipping Centre | 403 | 27 ms |
| ONI | 403 | 502 ms |
| GDELT | TLS handshake timeout | 8,126 ms |

HTTP 403 is not a declaration of source absence or permission to bypass access controls. A 200 HEAD is not proof of an accessible machine-readable incident feed. MSCIO redistribution restrictions remain in force; UKMTO's Open Government Licence requires compliance with attribution and other conditions. The checked MARAD 2026-012 is regional risk context, not case-specific evidence: https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations

## Incident candidate queue

- **BG_MOD:news9664 — CONTSHIP JET** (28 Oct 10:00 UTC, Black Sea): attack documented by Bulgarian MOD; IMO/MMSI crosswalk external; AIS stop contextual only; prosecutor investigation procedural, not automatically independent witness.
- **MSCIO:162/26** (30 Oct 18:00 UTC, south of Lavan Island): impact/fire, vessel identity unresolved; cannot assume identity with Nakilat's AL MAYEDA statement.
- **MSCIO:159/26 / LOUISE 1** (29 Oct 22:12 UTC): retrospective outside rolling 72h; potential shared origin with UKMTO, no double-counting.
- **MSCIO:160/26** (30 Oct): suspicious approach without shots/boarding; negative control, not physical attack.
- **IRGC-reported two tankers** (1 Nov, Strait of Hormuz): Reuters relay of Iranian state claim, no vessel identifiers or independent corroboration; no promotion. https://www.reuters.com/world/middle-east/irans-irgc-navy-says-two-tankers-exploded-after-hitting-mines-hormuz-2026-11-01/
- **AZINI / MSCIO:161/26** (29 Oct): piracy candidate, distinct from attack category; later AP report is not automatically independent from maritime authority sources.

## Tests and restrictions

GitHub Actions run `41393905551` on functional head `fd5d4127`: **370** maritime attack unit tests + **23** official bulletin tests + **3** SQLite + **10** PostgreSQL isolated = **406 Python tests**; **5 JavaScript tests**, frontend build success; all four jobs passed.

No production deployment, no writes to Oracle, no changes to historical records, no incident promotion, no new timers/cron/loops/schedulers. The Oracle checkout contains unrelated dirty changes from other workflows and was left untouched. The new helper is a staging-only pure function, **not** yet wired to an authenticated staging review API or an independent source-document archive.

**Next:** supply a verifiable IMO/MMSI crosswalk source with original document/hash and reviewer audit trail; connect the read-only helper to an authenticated, isolated staging review surface; validate duplicate/replayed source lineage and the actual PLAY promotion gate before requesting production approval.
