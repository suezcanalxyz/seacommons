# SeaCommons maritime attack correlation — Oracle read-only audit (2026-11-01)

Scope: **staging design and read-only production observation only**. Audited around 01:23–01:27 UTC on 2026-11-01 via the authorized Oracle device. No database writes, record edits, deployments, scheduled jobs or VM files were created. Database credentials are deliberately excluded. All SQL was executed with PostgreSQL `default_transaction_read_only=on`, bounded statement timeouts and `SELECT` statements.

## Compared with previous run

Previous staging head: `e1fd796346e5b630ebdad0f9785480eb919b17be` (264 Python tests and green CI). At the beginning of this run the branch was identical to that head. The previously reported remote-connector 0% quota was **not current**: this audit confirmed 99% of monthly remote calls remaining, permitting the first live read-only Oracle reconciliation.

## Database inventory

The requested tables exist. Approximate `pg_class.reltuples` estimates, **not exact counts**:

| Table | Approx. rows | Total disk |
|---|---:|---:|
| intel_events | 409,389 | 1,272 MB |
| vessel_tracks | 36,825,528 | 9,371 MB |
| alert_events | 0 | 24 kB |
| anomaly_events | 0 | 32 kB |
| humanitarian_incidents | 143 | 120 kB |
| forensic_events | 283 | 600 kB |
| maritime_episodes | 44,552 | 193 MB |
| source_observations | 2,500,518 | 2,584 MB |
| lineage_edges | 6,687 | 4,552 kB |

`alert_events` contains four old completed SAR alerts (latest `created_at` 2026-08-28); `anomaly_events` returned no rows. Recent `forensic_events` are classified as humanitarian `distress`. `humanitarian_incidents` has recent `distress` and `missing` review cases; these are **not** maritime-attack corroborations.

### Critical source-ingestion gap

For `intel_events` with `received_at >= '2026-10-01'`, the source-name filter `ukmto|mscio|navtex|navarea|navwarn|marad|bulgar|reuters|gdelt|imo` returned **zero** rows. The same official-source search over `source_observations` (source name or known official host) also returned **zero** rows. This does not prove no document exists elsewhere, but it does demonstrate that these official attack feeds are **not represented under the audited source identities in the two principal evidence tables**. The October non-AIS incident-title search yielded humanitarian/social material rather than the named commercial-ship attack cases.

In `source_observations` since October 1, major existing lanes are AISStream maritime/safety (555,601 rows), GFW maritime/intelligence (4,450), GDACS maritime/environmental (593), and humanitarian social/RSS sources. These are not substitutes for original incident bulletins. Do not count multiple downstream media copies of a single UKMTO/MSCIO announcement as independent origins.

No `maritime_episodes.episode_family` matching `attack|incident|sinking|piracy` was returned. The existing catalog is dominated by rendezvous, gaps, spoofing and unclassified episodes. A `multi_source_corroborated` **gap** episode is not a corroborated **attack**.

## CONTSHIP JET regression — IMO 9348625, MMSI 636019532

Official attack report: Bulgarian Ministry of Defence, 28 October 2026, 12:00 local / **10:00 UTC**, three drone impacts and crew rescue: https://www.mod.bg/news9664 . The Bulgarian NAVWARN 768/26 subsequently reported sinking at **20:30 UTC**, 43.130000 N, 28.756000 E (source URL and original bulletin require preservation in the claim provenance).

**Actual Oracle AIS evidence exists**: 19 `vessel_tracks` fixes for MMSI 636019532 between 2026-10-27 13:25:05 and 2026-10-28 19:37:34 UTC, source `aisstream`. Nearest pre-attack fix: 09:59:22 UTC, 10.2 kn; next available fix: 10:34:46 UTC, 0.6 kn. Last observed fix: 19:37:34 UTC, 0.8 kn, before the reported sinking. There is **no AIS fix at 20:30 UTC in this queried interval**. A 35-minute observation gap and subsequent low SOG are context, **not independent attack proof**, and cannot establish weapon, causation or perpetrator. Raw licensed AIS fixes are not republished in this document.

The `intel_events` records linked to 636019532 concern earlier AIS gaps, sudden stops, spoofing and rendezvous, not a canonical 28 October attack. Existing `maritime_episodes` for this MMSI are older gap/spoofing/identity/rendezvous families, not an attack episode. Thus **PLAY→incident is not operationally complete** for this regression despite available AIS and official external documentation. Do not write a historical record or promote LIVE without original-source ingestion, independently verified lineage and operator review.

## RITI — IMO 9249075, MMSI 352002473

Pakistan National Hydrographic Office NAVAREA IX **420/26**, issue time 2026-10-30 03:00 UTC, identifies RITI on fire at anchor in the Strait of Hormuz (26.401167 N, 56.412000 E): https://hydrography.paknavy.gov.pk/navarea-ix-warnings/ . This is the **warning time and reported anchorage**, not the independently established attack time or impact position. Oman maritime rescue statements were also reported, but the two reporting chains may share an originating notification. **Candidate, not independently corroborated**.

Oracle `vessel_tracks` returned **zero** fixes for MMSI 352002473 from 2026-10-27 through 2026-10-31. This is insufficient to infer an AIS gap without an established coverage baseline. Earlier September intelligence exists for that MMSI; it is not evidence of the October incident.

## LIVE / PLAY GET-only verification

At about 01:25 UTC, read-only local HTTP GET checks returned HTTP 200 for `/api/v1/live/pipeline`, `/api/v1/live/sources`, `/api/v1/play/cache-status`, `/api/v1/play/counts`, and `/api/v1/play/incidents?limit=2`. LIVE pipeline reported AIS and public feeds live, partner and radio degraded. The PLAY counts endpoint returned 3,564 catalog items (127 humanitarian, 3,437 maritime), **not 3,564 verified attacks**. PLAY catalog and counts caches were around **6,400 seconds old** at the time of inspection, with no reported last_error. HTTP success establishes endpoint availability, not freshness or correct attack categorization.

`intel_events` for the last 72 hours showed active AIS and social ingestion. The 2026-10-31 Alarm Phone item `39d2211c` about eight missing boats is classified `operational` without a populated incident lifecycle; this is a separate humanitarian LIVE qualification risk, **not an attack**. Route to the humanitarian review pipeline; do not change historical rows as part of this branch.

### Timestamp/latency integrity

Among `intel_events` received since 2026-10-29, event timestamps more than one hour **after** the stored receipt occurred for 160/335 `ais` signal records, 235/319 `mda` signal records, and 116/358 `SeaCommons fusion` news records. These are counts of inconsistent event/receipt ordering, **not measured negative network latency**. Derived-event timestamp semantics, update behavior and collector clock provenance must be audited before computing or publishing latency SLAs. Do not substitute `event.timestamp_utc` for original source publication time.

## Reproducible, bounded read-only queries

Run under a read-only session with a statement timeout; never interpolate untrusted input into SQL.

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '8s';
SELECT mmsi, count(*), min(ts), max(ts), min(sog), max(sog)
FROM vessel_tracks
WHERE mmsi = '636019532'
  AND ts >= timestamp '2026-10-27'
  AND ts < timestamp '2026-11-01'
GROUP BY mmsi;

SELECT source, count(*)
FROM intel_events
WHERE received_at >= timestamp '2026-10-01'
  AND source ~* '(ukmto|mscio|navtex|navarea|navwarn|marad|bulgar|reuters|gdelt|imo)'
GROUP BY source;

SELECT episode_family, verification_status, count(*)
FROM maritime_episodes
GROUP BY 1, 2
ORDER BY count(*) DESC
LIMIT 25;
ROLLBACK;
```

## External sources and permissions

- Bulgarian Ministry of Defence: https://www.mod.bg/news9664 — primary evidence for CONTSHIP JET; no original French patrol-aircraft record yet.
- Pakistan NAVAREA IX: https://hydrography.paknavy.gov.pk/navarea-ix-warnings/ — public warning index, but the issuing authority explicitly cautions that upstream information can be incomplete; public access does not establish bulk redistribution permission.
- MSCIO: https://mscio.eu/alerts/195 (159/26, 29 October 22:12 UTC, explosive devices), https://mscio.eu/alerts/198 (162/26, 30 October 18:00 UTC, projectile and fire), https://mscio.eu/alerts/196 (160/26, **suspicious approach, no shots**, negative control). Public consultation does not establish unrestricted republication; preserve link, metadata and a short factual extraction only.
- GDELT: https://www.gdeltproject.org/data.html — published 15-minute dataset update cadence, **not** SeaCommons measured collector latency.

## Staging acceptance gates

1. Import original-source **structured observations** with stable original report IDs, source URL, authority, source publication/receipt/event timestamps and explicit precision; keep raw licensed text out of public rehosting.
2. Correlate IMO/MMSI with explicit conflict veto, time/location uncertainty and verified lineage. AIS speed changes, sudden stops, gaps, satellite or media repetitions remain contextual signals.
3. Keep distinct attack/sinking/piracy/suspicious-activity families, dedicated UI colors and separate humanitarian drifts. A sinking can update a documented attack without creating a second attack.
4. Require two genuinely independent original authorities, reviewed provenance and a separate operator publication decision for PLAY→incident. Never infer an attacker from proximity, flag or political context.
5. Re-run regression on CONTSHIP JET (including the observed 35-minute AIS interval), RITI (no October AIS coverage), KHORYV (capsized, no attack claim), MSCIO 160/26 (suspicious only) and timestamp-skew samples.
6. Certify GitHub Actions and a subsequent read-only end-to-end Oracle audit **before** seeking explicit production-deployment approval.

No production deployment, database writes, deletion, history rewriting or VM scheduling were performed.
