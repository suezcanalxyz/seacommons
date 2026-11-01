# SeaCommons maritime attack correlation — staging audit, 2026-11-01 03:19–03:22 UTC

**Previous head:** `ed1a2379379fa060a651e3119184c20b78126dbc`. **Scope:** branch `feature/maritime-attack-correlation-20261030` only. No VM files changed, no scheduler or daemon added, no production deployment, no PostgreSQL writes or historical rewrites.

## Implemented: prevent event, category and position laundering

The opt-in `official_maritime_bulletin.py` adapter now records `bulletin_kind`, `occurred_at_utc`, and `location_role` in immutable source provenance. Location roles: `incident_site`, `anchorage`, `last_reported_position`, `hazard_position`, `unknown`. Coordinates without an explicit role are rejected. A document revision receives a new deterministic source delivery key; replay is stable.

The pure `claim_from_source_observation` bridge now refuses to reinterpret a suspicious-activity or navigational-hazard bulletin as an attack, refuses to treat publication-only information as an event clock, checks exact event time/day against immutable provenance, enforces at least 1,440 minutes uncertainty for day-only events, excludes anchorage/last-reported positions from incident-site geometry, and refuses to make a verified incident-site location more precise than the source. It also refuses relocated extracted coordinates. These guards apply specifically to `official_maritime_bulletin` observations and do not change the legacy extraction behavior for other sources.

**Negative regression:** RITI's NAVAREA IX 420/26 anchorage position is context, not the impact site; KHORYV's capsize/drift is not proof of attack. **Positive regression:** CONTSHIP JET, IMO 9348625, MMSI 636019532, 2026-10-28 10:00 UTC, remains an event-time reference, without inventing publication clock or a second independent source. MSCIO 159/26 event 2026-10-29 22:12 UTC was **published 2026-10-30**, not on the event date; the test fixture now preserves that difference.

No automatic verification, incident promotion, attribution, or LIVE/PLAY publication was enabled. Existing `origin_authority_verified=False`, `reuse_rights_verified=False`, `attack_corroboration_allowed=False` remain in place.

## Oracle read-only audit

Authorized Oracle PostgreSQL device `instance-20260828-1159`; `seacommons` database. SQL used `BEGIN READ ONLY`, `SET LOCAL statement_timeout='7000ms'`, `ROLLBACK`. Snapshot clock **2026-11-01 03:19:53 UTC**.

- `source_observations` exact rolling 72h (since approximately 2026-10-29 03:19 UTC): AISStream **50,007**, GFW **559**, GDACS **76**, alarm_phone **25**, InfoMigrants **21** (other sources omitted here). Counts are observations, not attacks.
- October source-name/URL match for MSCIO, UKMTO, NAVAREA, NAVWARN, Bulgarian MOD, MARAD, GDELT: **0**. The official bulletin adapter remains **unwired** to automatic collection.
- `maritime_episodes` family matching `attack|incident|sinking|piracy`: **0**.
- Last 72h `intel_events`: **3,924**; `alert_events`: **0**; `anomaly_events`: **0**; `humanitarian_incidents`: **16**; `forensic_events`: **13**; `maritime_episodes`: **37**. These are not confirmed attacks.
- CONTSHIP JET MMSI 636019532: **19** AIS fixes 27–28 Oct. At **09:59:22 UTC**: 43.2659267 N, 28.8149 E, **10.2 kn**; at **10:34:46 UTC**: 43.2591967 N, 28.81574 E, **0.6 kn**. This speed change is context, **not** independent attack evidence. Last AIS fix was 19:37:34 UTC.

Representative bounded SQL:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout='7000ms';
SELECT source_name, count(*), max(received_at)
FROM source_observations
WHERE received_at >= now()-interval '72 hours'
GROUP BY source_name ORDER BY count(*) DESC LIMIT 12;
SELECT count(*) FROM source_observations
WHERE received_at >= timestamp '2026-10-01'
AND (source_name ~* '(mscio|ukmto|navarea|navwarn|bulgar|marad|gdelt)'
OR source_url ~* '(mscio.eu|mod.bg|hydrography.paknavy.gov.pk)');
SELECT episode_family,verification_status,count(*)
FROM maritime_episodes WHERE episode_family ~* '(attack|incident|sinking|piracy)'
GROUP BY episode_family,verification_status;
SELECT ts,lat,lon,sog,source FROM vessel_tracks
WHERE mmsi='636019532'
AND ts >= timestamp '2026-10-28 09:50:00'
AND ts < timestamp '2026-10-28 11:00:00'
ORDER BY ts LIMIT 20;
ROLLBACK;
```

## LIVE / PLAY GET-only checks

At 03:20–03:22 UTC all five endpoints returned HTTP 200: `/api/v1/live/pipeline`, `/api/v1/live/sources`, `/api/v1/play/cache-status`, `/api/v1/play/counts`, `/api/v1/play/incidents?limit=2`. PLAY: **3,566** entries (3,439 maritime, 127 humanitarian; 3,429 investigation). LIVE source summary: 7 sources, 2 active, 1 degraded, 3 disabled, 1 pending. At 03:20, cache catalog age **2,126.8 seconds**, counts age **2,138.3 seconds**: HTTP 200 does not imply fresh projections. No attack episode is proven end-to-end.

## Candidate source register and licensing gate

- **CONTSHIP JET**: Bulgarian Ministry of Defence original 28 Oct bulletin, https://www.mod.bg/news9664. Event time 10:00 UTC; published date 28 Oct; exact publication clock unknown. AIS only context.
- **MSCIO 158/26**: https://mscio.eu/alerts/194 — tanker reportedly struck 29 Oct 16:00 UTC; vessel IMO/MMSI unknown.
- **MSCIO 159/26**: https://mscio.eu/alerts/195 — reported explosive-device attack 29 Oct 22:12 UTC, published 30 Oct; IMO/MMSI unknown.
- **MSCIO 162/26**: https://mscio.eu/alerts/198 — reported impact/fire 30 Oct 18:00 UTC, IMO/MMSI unknown.
- **MSCIO 163/26**: https://mscio.eu/alerts/199 — published 30 Oct, **event on 28 Oct**, not a new 30 Oct attack.
- **RITI**: IMO 9249075, MMSI 352002473, NAVAREA IX 420/26, https://hydrography.paknavy.gov.pk/navarea-ix-warnings/ — warning issued 30 Oct 03:00 UTC; anchorage is not verified impact site.
- **AZINI**: MSCIO 161/26, https://mscio.eu/alerts/197 — reported piracy/hijack on 29 Oct; update location not a new attack.
- **KHORYV**: IMO 8138712, Bulgarian NAVWARN 766/26 — capsize/drift only, negative control.

Official public pages are currently accessible; this does not establish automated scraping, bulk reproduction, derivative redistribution or continuous availability rights. Keep metadata-only, links and original IDs; verify source-specific terms before acquisition. MSCIO and UKMTO may relay the same upstream reporting chain, so they are not automatically independent. GDELT 2.0 publishes 15-minute dataset updates (https://gdeltproject.org/data.html), not a verified SeaCommons collector latency.

## Tests and next gate

The preceding certified staging CI was **278 Python tests** (268 correlation + 10 adapter). This change adds **5 adapter regressions**, for **283 expected**. GitHub Actions run for the application/test commit `c9c2ef2e` passed 268 correlation + 15 adapter tests and the frontend job. The final date-fixture commit `9c50ce65` has the same executable code and awaits its own CI confirmation.

**Next:** verify final CI, then perform a separate opt-in canonical-writer integration test in an isolated staging database (never Oracle production), and only after provenance/rights review connect a legally permitted metadata collector. Keep PLAY incident promotion operator-gated and maritime-attack UI tokens separate from humanitarian drifts.
