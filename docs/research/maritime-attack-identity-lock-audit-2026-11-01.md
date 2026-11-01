# SeaCommons maritime attack correlation — immutable vessel identity gate

**Audit:** 2026-11-01 04:21–04:25 UTC. **Scope:** staging branch only, Oracle read-only, production GET endpoints. No VM file writes, new cron/timer/loop, database mutations, incident promotions or production deployment.

## Change relative to previous run

Previous certified application head: `9c50ce652cdfff0af3eaceab81709a3a8f95ac0f` (283 Python tests). The previous adapter validated document type, occurrence time and location role but allowed a model-extracted *valid yet different* IMO/MMSI/name to replace the vessel identified by the immutable official bulletin. That could misassociate a documented attack with an unrelated ship, even while location/time checks passed.

Now `official_maritime_bulletin.py` persists `vessel_imo`, `vessel_mmsi`, and `vessel_name` in canonical observation provenance. `claim_from_source_observation` refuses a supplied identity that differs from, or adds an ID absent from, the original reviewed bulletin. Partial extraction may omit known identifiers but cannot substitute or manufacture them. Older official observations without these provenance fields fail closed on attempted ID enrichment. Separate entity-resolution evidence must remain a separately auditable claim. This is an *extraction integrity* check, not a claim that a name/IMO is independently corroborated.

Three new regressions cover a CONTSHIP JET→RITI valid-IMO swap, MMSI/name substitution, ID invention from an unidentified ship, and legacy missing provenance. Existing location-role, chronology, lineage, source-independence and AIS-is-not-proof controls remain unchanged.

**Certified CI:** GitHub Actions run 41272919755 at 04:24 UTC, SUCCESS. `correlation-unit`: 268 tests; `test_official_maritime_bulletin`: 18 tests; **286 Python tests total**. `frontend-attack-taxonomy`: **5 JS tests** and Vite build SUCCESS. CI proves these tests only; no end-to-end Oracle ingestion was run.

## Oracle read-only verification

Authorized device `instance-20260828-1159`; DB `seacommons`. All SQL executed via psql with `BEGIN TRANSACTION READ ONLY`, `SET LOCAL statement_timeout='6000ms'`, `ROLLBACK`. No secrets printed.

72-hour interval: **2026-10-29 04:21 UTC to 2026-11-01 04:22 UTC** for source observations; other event counts use the lower bound at snapshot time.

- `source_observations`: AISStream **50,023**; GFW **559**; GDACS **73**; alarm_phone **25**; radio_receiver:heimiswil_hb9cwk_kiwisdr **22**; InfoMigrants **21**. These are observations, not incident corroborations.
- `intel_events`: **3,921** received since 2026-10-29 04:21 UTC; latest receipt 2026-11-01 04:19:09 UTC.
- `maritime_episodes`: **35 gap_episode**, **1 safety_episode**, **1 spoofing_episode** created since lower bound; **0** families matching `attack|incident|sink|piracy` created since 1 Oct.
- `humanitarian_incidents`: **16**; `forensic_events`: **13**; `alert_events`: **0**; `anomaly_events`: **0** since lower bound.
- October official-source audit: **0** `source_observations` whose `source_name` contains MSCIO/UKMTO or whose `source_url` contains mscio.eu/mod.bg (bounded check). This does not exclude differently labelled observations, but confirms the known missing official-bulletin collector.
- CONTSHIP JET MMSI `636019532`: 2026-10-28 09:59:22 UTC **10.2 kn** at 43.2659 N, 28.8149 E; 10:34:46 UTC **0.6 kn** at 43.2592 N, 28.8157 E; last 19:37:34 UTC **0.8 kn** at 43.1285 N, 28.7548 E. The source document (https://www.mod.bg/news9664) reports attack at 10:00 UTC. AIS slowdown is context, **not** a second independent attack confirmation.

Reproducible bounded query pattern:

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout='6000ms';
SELECT source_name, count(*) FROM source_observations
 WHERE received_at >= timestamp '2026-10-29 04:21:00'
   AND received_at < timestamp '2026-11-01 04:22:00'
 GROUP BY source_name ORDER BY count(*) DESC LIMIT 12;
SELECT episode_family, count(*) FROM maritime_episodes
 WHERE created_at >= timestamp '2026-10-29 04:21:00'
 GROUP BY episode_family ORDER BY count(*) DESC LIMIT 12;
SELECT ts, sog, lat, lon FROM vessel_tracks
 WHERE mmsi='636019532'
   AND ts >= timestamp '2026-10-28 09:30:00'
   AND ts < timestamp '2026-10-29'
 ORDER BY ts LIMIT 35;
ROLLBACK;
```

## LIVE/PLAY read-only GET audit

At 04:24 UTC: HTTP 200 from `/api/v1/play/counts`, `/api/v1/play/incidents?limit=1`, and `/api/v1/live/pipeline` on the local API. PLAY counts **3,566 total**, **3,439 maritime**, **127 humanitarian**; generated 04:24:06 UTC. Catalog cache age **3,712.6 seconds**, `refreshing=true`; counts cache age **5.4 seconds**, `refreshing=false`. No documented attack family is available in the canonical episode table. Catalog freshness remains a separate issue.

## October/72-hour source review and licensing

- **CONTSHIP JET**: Bulgarian MOD 28 Oct 2026, 10:00 UTC event, IMO 9348625, MMSI 636019532: https://www.mod.bg/news9664. Original authority verified as *publisher*, not as a second independent reporting chain.
- **MSCIO 162/26**: 30 Oct 18:00 UTC reported impact/fire 40 NM south of Lavan Island; unidentified vessel: https://mscio.eu/alerts/198.
- **MSCIO 163/26**: 28 Oct event, published 30 Oct; time-late report, not a new 30 Oct attack: https://mscio.eu/alerts/199.
- **MSCIO 161/26 / AZINI**: reported hijack 29 Oct, update published 31 Oct: https://mscio.eu/alerts/197. The UKMTO homepage on 1 Nov lists **UKMTO #190 (31 Oct)**, a large fishing vessel boarded by unauthorized personnel: https://www.ukmto.org/. Possible overlapping upstream chain with AZINI; **do not count as a second independent report or deduplicate automatically** without vessel identity and source lineage.
- **RITI**: NAVAREA IX 420/26, IMO 9249075, MMSI 352002473, anchorage position (not impact): https://hydrography.paknavy.gov.pk/navarea-ix-warnings/.
- **KHORYV**: IMO 8138712, capsized/drifting 28 Oct, negative attack control; distinct IMO from CONTSHIP JET.

Licensing finding: UKMTO explicitly states its site is published under the **Open Government Licence** and allows reproduction subject to licence terms, attribution and third-party exclusions: https://www.ukmto.org/terms-and-conditions (clauses 17–21). MSCIO terms restrict disclosure/publication of site information: https://mscio.eu/terms-of-service/. UKMTO and MSCIO are part of a shared reporting ecosystem, so two pages can relay a single original source; independent corroboration remains unverified. No automated scraping or full-text redistribution was enabled. The adapter conservatively retains `reuse_rights_verified=False` until source-specific review.

## Remaining gates

1. Perform a canonical `record_observation` integration test against a **separate, isolated staging DB**, with rollback/replay/lineage assertions; never write Oracle production.
2. Implement legally compliant, rate-limited, operator-approved metadata ingestion for permitted sources, without any VM cron/timer/loop. Respect source-specific rights and avoid storing restricted full text.
3. Resolve catalog cache refresh age, then test the full reviewed path from official bulletin to PLAY candidate and operator-approved incident, with attack colors distinct from humanitarian drift.
4. Independently corroborate source origins; do not attribute an attacker, treat AIS gaps as proof, or promote cases without review.
