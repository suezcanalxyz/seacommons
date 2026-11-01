# Maritime attack correlation: AIS receipt chronology and LIVE/PLAY audit
Date: 2026-11-01, ~09:19 UTC. Scope: staging branch only.

## Comparison with prior run
Baseline: `96745fc0850874ce7465a71ff715097f15dac961`.
Before changes, GitHub compare returned `identical` (ahead 0, behind 0).
This run changes the pure correlator, adds receipt-chronology regressions and
adds their file to the existing CI trigger paths. No production deployment,
new scheduled task, VM cron, service, or Oracle write.

## New guard: event timestamp versus AIS receipt timestamp
`AISFix.received_at` is optional for backward compatibility. When supplied,
the pure correlator rejects a fix whose `observed_at` is more than 300 seconds
later than its receipt. Naive/invalid receipt timestamps are quarantined.
Such fixes cannot create sudden-stop context, corroborate a spatial location,
or demote an otherwise corroborated documentary event by claiming a distant
position. Delayed receipts and <=5 minute clock skew are accepted. Missing
receipt timestamps remain an audit limitation, NOT proof of integrity.
No AIS signal can create a documentary incident, count as an independent
witness, or authorize publication.

New tests: plausible CONTSHIP JET fixes, future-dated fix excluded, invalid
receipt timezone, exact five-minute skew, delayed receipt, and protection
against a false AIS spatial veto. Synthetic documentary claims are explicitly
test fixtures and do not certify independent real-world sources.

## Oracle PostgreSQL read-only snapshot
Authorized Oracle remote device, existing application DB configuration
(without printing credentials). SQL used `BEGIN READ ONLY`,
`SET LOCAL statement_timeout='7000ms'`, `ROLLBACK`.
Snapshot time ~2026-11-01 09:17 UTC, 72-hour lower bound
2026-10-29 09:17 UTC. Counts are by each column indicated:

| Table | Count | Timestamp |
| --- | ---: | --- |
| intel_events | 3,672 | created_at |
| alert_events | 0 | created_at |
| anomaly_events | 0 | created_at |
| humanitarian_incidents | 19 | updated_at, not new cases |
| forensic_events | 13 | created_at |
| maritime_episodes | 32 | created_at |
| source_observations: AISStream | 49,843 | received_at |
| source_observations: GFW | 340 | received_at |
| source_observations: GDACS | 69 | received_at |

October episode families: gap_episode 1,487; spoofing_episode 212;
safety_episode 60; rendezvous_episode 28; port_call_episode 2;
identity_integrity_episode 1. No attack/sinking/piracy family in the
returned distribution. October official-bulletin recognition query
(`source_name` regex MSCIO/UKMTO/NAVAREA/NAVWARN/Bulgarian Ministry/
MARAD/GDELT or `observation_type='official_maritime_bulletin'`)
returned **zero**. This is an identity-based detection query, not proof
that no relevant article is hidden under an unrelated source label.

CONTSHIP JET IMO 9348625, MMSI 636019532: 19 AIS fixes from 27–28 Oct.
At 28 Oct 09:59:22 UTC, 10.2 knots, 43.265927 N 28.814900 E;
10:34:46 UTC, 0.6 knots, 43.259197 N 28.815740 E.
This is temporal context for the 10:00 UTC reported attack, NOT a second
independent witness. The schema audit confirmed `vessel_tracks.received_at` exists, but
individual receipt timestamps were NOT retrieved in this run; the
new receipt guard therefore remains a staging contract, not a
production-data validation. No production rows were modified.

Representative SQL (read-only):
```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout='7000ms';
SELECT count(*) FROM intel_events
 WHERE created_at >= '2026-10-29 09:17+00';
SELECT source_name, count(*) FROM source_observations
 WHERE received_at >= '2026-10-29 09:17+00'
 GROUP BY source_name ORDER BY count(*) DESC LIMIT 12;
SELECT episode_family, count(*) FROM maritime_episodes
 WHERE created_at >= '2026-10-01+00'
 GROUP BY episode_family ORDER BY count(*) DESC;
SELECT count(*) FROM source_observations
 WHERE received_at >= '2026-10-01+00'
 AND (source_name ~* '(MSCIO|UKMTO|NAVAREA|NAVWARN|Bulgarian Ministry|MARAD|GDELT)'
      OR observation_type='official_maritime_bulletin');
SELECT ts,sog,lat,lon FROM vessel_tracks
 WHERE mmsi='636019532'
 AND ts BETWEEN '2026-10-28 09:45+00' AND '2026-10-28 11:00+00'
 ORDER BY ts;
ROLLBACK;
```

## LIVE/PLAY public GET (read-only)
At ~09:19 UTC, all four checked URLs returned HTTP 200:
- https://play.seacommons.org/api/v1/play/counts
- https://play.seacommons.org/api/v1/play/incidents?limit=1
- https://live.seacommons.org/api/v1/live/pipeline
- https://live.seacommons.org/api/v1/live/sources

Counts: 3,569 total = 3,442 maritime + 127 humanitarian;
counts generated 08:43:54 UTC. Catalog generated 09:18:55 UTC,
also 3,569 total. Values agree at this snapshot, but the counts cache
is ~35 minutes older than the catalog; HTTP 200 alone is not a
freshness guarantee. No attack episode end-to-end promotion was verified.

## Documentary candidate checks and dependency risk
- Bulgarian MOD (28 Oct): https://www.mod.bg/news9664 ;
  CONTSHIP JET, reported attack 12:00 Bulgarian local = 10:00 UTC.
  Reuters (28–29 Oct) reports independent footage verification,
  but footage provenance and origin-independence remain unverified.
- MSCIO 158/26: https://mscio.eu/alerts/194 ;
  tanker hit 29 Oct 16:00 UTC; IMO/MMSI unknown.
- MSCIO 159/26: https://mscio.eu/alerts/195 ;
  29 Oct 22:12 UTC; compare UKMTO #187, do NOT count automatically
  as independent reports.
- MSCIO 163/26: https://mscio.eu/alerts/199 ;
  28 Oct event, published 30 Oct; UKMTO #189 is potentially the
  same upstream account, NOT a second independent source by default.
- MSCIO 161/26: https://mscio.eu/alerts/197 ;
  AZINI reported hijacked 29 Oct 09:00 UTC, last reported coordinates
  dated 30 Oct are NOT necessarily the piracy location. UKMTO #190
  is suspicious-activity reporting, not independent attack proof.
- IMO confirmed incidents as at 30 Oct:
  https://www.imo.org/en/mediacentre/hottopics/pages/middle-east-highlighted-incidents.aspx
  GHANA PROSPERITY IMO 9732541 appears on 3 Oct and 23 Oct;
  one vessel, two incidents. IMO may rely on the same upstream source.
- MARAD Black Sea 2026-012:
  https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations
  is risk context, not an individual attack report.

Reuse and latency: IMO website terms prohibit commercial reuse of site
materials without permission:
https://www.imo.org/en/about/pages/imo-website-terms-and-conditions-of-use.aspx
GDELT 2.0 advertises free data and 15-minute publication cadence:
https://www.gdelt.org/ and https://gdeltproject.org/data.html .
This is NOT SeaCommons collector latency. No bulk scraping or
redistribution of restricted source material was performed.

## CI and release gate
GitHub Actions run 41292556116 for commit `8d2bf06b`:
283 maritime Python tests (including 6 new receipt-guard tests),
18 official bulletin tests, 3 SQLite writer tests, 5 ephemeral PostgreSQL
writer tests = **309 Python tests**, all PASS. Frontend attack-taxonomy
tests and build PASS. The tests do not prove production AIS integrity or
independence of actual reporting origins.

Remaining gates: optional receipt metadata must be supplied by the
authorized AIS read adapter before the new guard can protect real fixes;
verified source-origin chains must be recorded in staging; official
bulletin ingestion and PLAY-to-incident promotion require isolated
end-to-end tests and operator approval. No production deploy.
