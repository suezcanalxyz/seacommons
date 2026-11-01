# Maritime attack correlation — AIS sudden-stop contextual signal (2026-11-01, 08:27 UTC)

## Baseline and scope

Previous branch head: `dd571fccb85e94cd145e118931bfbfb4cf28f32f`. This run adds a **staging-only, pure** AIS speed-drop context check and regressions. No production deployment, cron, timer, service, collector, migration, or Oracle write. Existing maritime attack and humanitarian pipelines are unchanged.

## Oracle read-only audit

Accessed the authorized Oracle device using the application's existing local PostgreSQL connection settings **without printing credentials**. PostgreSQL session confirmed `default_transaction_read_only=on` and `statement_timeout=6s`; each SQL batch used `BEGIN READ ONLY` and `ROLLBACK`. Audit snapshot: **2026-11-01 08:24:53 UTC**; 72h window begins **2026-10-29 08:24:53 UTC**.

| Dataset | 72h count / semantics |
| --- | ---: |
| `intel_events` | 3,696 rows by `created_at` |
| `alert_events` | 0 by `created_at` |
| `anomaly_events` | 0 by `created_at` |
| `humanitarian_incidents` | 19 **updated**, not necessarily created, in window |
| `forensic_events` | 13 by `created_at` |
| `maritime_episodes` | 32 by `created_at` |
| `source_observations`: AISStream | 49,886 by `received_at` |
| `source_observations`: GFW | 340 by `received_at` |
| `source_observations`: GDACS | 72 by `received_at` |

October `maritime_episodes` family distribution: `gap_episode` 1,487; `spoofing_episode` 212; `safety_episode` 60; `rendezvous_episode` 28; `port_call_episode` 2; `identity_integrity_episode` 1. No attack/sinking/piracy family was returned in this grouping. The **previous** official-bulletin audit found zero recognized official observations; the new source-name sample does not independently certify a zero count for the entire month.

Representative queries:

```sql
BEGIN READ ONLY;
SELECT count(*) FROM intel_events
 WHERE created_at >= now() - interval '72 hours';
SELECT source_name, count(*) FROM source_observations
 WHERE received_at >= now() - interval '72 hours'
 GROUP BY source_name ORDER BY count(*) DESC LIMIT 15;
SELECT episode_family, count(*) FROM maritime_episodes
 WHERE created_at >= '2026-10-01'
 GROUP BY episode_family ORDER BY count(*) DESC;
SELECT ts, sog, lat, lon, source FROM vessel_tracks
 WHERE mmsi='636019532' AND ts >= '2026-10-27'
   AND ts < '2026-10-29' ORDER BY ts LIMIT 25;
ROLLBACK;
```

## CONTSHIP JET regression: real AIS observations

Vessel **CONTSHIP JET**, IMO `9348625`, MMSI `636019532`. Bulgarian Ministry of Defence primary report: https://www.mod.bg/news9664 (28 Oct 2026, reported attack at **10:00 UTC**). PostgreSQL contains **19** AIS positions for 27–28 October, including:

| UTC | SOG knots | Latitude | Longitude |
| --- | ---: | ---: | ---: |
| 28 Oct 09:59:22 | 10.2 | 43.2659267 | 28.814900 |
| 28 Oct 10:34:46 | 0.6 | 43.2591967 | 28.815740 |
| 28 Oct 19:37:34 | 0.8 | 43.1284667 | 28.754847 |

The speed drop is temporally consistent with the ministry's reported attack, but **AIS is not a second independent witness**. Neither the cause of slowing nor an aggressor is inferred from these fixes.

The new pure correlator accepts optional `AISFix.sog_knots` and returns auditable `related_sudden_stop_fixes` timestamps. The context signal requires a valid matching MMSI, finite plausible speed values, a precisely timed incident claim (uncertainty at most 30 min), a pre-event fix within 30 min with SOG >=5 kn, a post-event fix within 90 min with SOG <=1.5 kn, a drop >=5 kn, 2–90 min elapsed, and <=15 km movement. If the incident has a reported location, both fixes must also fall within its uncertainty envelope plus 30 km. No speed drop can create an incident without a documentary claim, increase the number of independent groups, change status, or authorize publication.

Negative regressions cover wrong MMSI, far-away fix, hours-late fix, day-only/coarse event clock, NaN SOG, simultaneous/one-second speed flips, and a signal without a documentary claim.

## LIVE/PLAY read-only checks

Read-only GETs at **08:26 UTC** returned HTTP 200 for PLAY counts, PLAY catalog, LIVE pipeline, LIVE sources and edge health. PLAY counts at 08:26:11 UTC: **3,568 total = 3,441 maritime + 127 humanitarian**. PLAY catalog generated at 08:26:46 UTC returned **3,569 total**. The one-item difference has *different generation timestamps* and is not yet a proven persistent discrepancy. LIVE pipeline generated at 08:26:46 UTC. Edge health status `ok`. None of these proves that attacks are represented end-to-end in PLAY.

## Official source checks (not ingested)

- Bulgarian MOD, 28 Oct: https://www.mod.bg/news9664 — CONTSHIP JET primary military observation; attribution of attacker not established.
- MSCIO 158/26, 29 Oct 16:00 UTC: https://mscio.eu/alerts/194 — tanker struck, identity not established here.
- MSCIO 159/26, 29 Oct 22:12 UTC (published 30 Oct): https://mscio.eu/alerts/195 — tanker, two devices on hull, identity not established here.
- MSCIO 162/26, 30 Oct 18:00 UTC: https://mscio.eu/alerts/198 — projectile/fire, Arabian Gulf, identity not established here.
- MSCIO 163/26, **event** 28 Oct, **published** 30 Oct: https://mscio.eu/alerts/199 — time-late report, identity not established.
- MARAD active Black Sea advisory 2026-012: https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations — threat context, **not** an individual incident witness.
- GDELT 2.0: https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/ — advertised 15-minute update cadence, **not** SeaCommons ingestion latency.
- IMO website terms: https://www.imo.org/en/about/pages/imo-website-terms-and-conditions-of-use.aspx — commercial reuse restricted; no bulk ingestion/redistribution authorized by this check.

Original reporting authority vs relaying publisher, license, and precise publication/reception chronology still need individual validation. No independent two-origin corroboration or PLAY→incident promotion was claimed.

## CI and next gate

First implementation commit `506d9368` and regression commit `fd44498b`: GitHub Actions run **41288839559 SUCCESS** (275 maritime Python tests, 18 bulletin unit tests, 3 SQLite, 5 ephemeral PostgreSQL = **301 Python**, plus frontend job). Follow-up stricter time guards `6323ff83` and tests `d263ff38` require their own CI result; do not call them certified until it completes.

Next: certify the final CI head, then test reviewed original-bulletin acquisition and AIS context together on isolated staging PostgreSQL. Preserve source links, event/publication/reception timestamps, uncertainty, and origin lineage. Do not touch Oracle historical rows or deploy without approval.
