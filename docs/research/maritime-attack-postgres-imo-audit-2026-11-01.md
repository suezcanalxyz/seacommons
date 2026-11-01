# SeaCommons attack correlation — ephemeral PostgreSQL gate and IMO identity audit
Date: 2026-11-01, 06:20 UTC. Scope: staging branch only. No production deploy, no VM scheduling, no historical edits.

## Delta from previous run
Previous head: `0986ba509cfdfd91eaee5137a30a61d37a084117`.
New isolated PostgreSQL test: `tests/test_official_maritime_bulletin_postgres.py`.
CI gate: `.github/workflows/maritime-attack-correlation-staging.yml`.
GitHub Actions run: https://github.com/suezcanalxyz/seacommons/actions/runs/41280294694

The PostgreSQL test runs against a disposable `postgres:16` service in GitHub Actions, not the Oracle VM. The test URL is fail-closed: PostgreSQL dialect, loopback host, port 5432, exact database `seacommons_attack_test`. It uses the real `ingest_official_bulletin -> record_observation -> SourceObservationDB` path, including the canonical reported_by entity graph, and checks idempotent replay, append-only revision, provenance, receipt timestamp, and transaction rollback. RITI's anchorage and publication-only time remain explicitly non-incident-site and non-event-time. The adapter never writes `IntelEventDB` or PLAY. The PostgreSQL job passed 3/3 tests; the four CI jobs passed.

## Oracle access and public surface check
The authorized device is online. A local `psql -w` read-only attempt failed with `FATAL: role "ubuntu" does not exist`. No privilege escalation or DB role impersonation was attempted. **Zero new Oracle SQL queries succeeded in this run**; earlier counts must not be represented as current measurements. Pending authorized read-only credentials, inspect `intel_events`, `vessel_tracks`, `alert_events`, `anomaly_events`, `humanitarian_incidents`, `forensic_events`, `source_observations`, `maritime_episodes` and LIVE/PLAY separately.

Read-only public HTTP checks at ~06:19 UTC: `live.seacommons.org/` HEAD 200 (~90 ms), `play.seacommons.org/` HEAD 200 (~55 ms); public edge `GET /health` 200 (~42 ms) with `status: ok`. Edge `HEAD /health` returned 405 (method unsupported, not a health failure). These checks do **not** certify freshness of PLAY catalog, data projections or attack promotion. The HTML cache Age headers are not operational data latency.

Safe SQL template for authorized Oracle read-only account (not executed this run):
```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '3000ms';
SELECT ts, received_at, lat, lon, sog, source
FROM vessel_tracks
WHERE mmsi = '636019532'
  AND ts >= TIMESTAMP '2026-10-28 09:30:00'
  AND ts < TIMESTAMP '2026-10-28 21:00:00'
ORDER BY ts LIMIT 100;
SELECT observation_id, source_name, source_id, observed_at, received_at
FROM source_observations
WHERE received_at >= TIMESTAMP '2026-10-29 06:20:00'
  AND source_name IN ('MSCIO','UKMTO','Bulgarian Ministry of Defence','Pakistan NAVAREA IX')
ORDER BY received_at DESC LIMIT 100;
ROLLBACK;
```

## New official retrospective identity-resolution leads
IMO official highlighted confirmed-incident list, snapshot **as at 27 October 2026**, reports 121 incidents and 24 seafarer fatalities. Source:
https://www.imo.org/en/mediacentre/hottopics/pages/middle-east-highlighted-incidents.aspx

Potential same-episode matches (NOT two independent eyewitness chains):
- MSCIO 133/26: 7 October ~19:00 UTC, 51 NM north of Madinat ash Shamal, Qatar. IMO table lists **ACERS**, IMO **9301902**, on 7 October at the same reported location. MSCIO: https://mscio.eu/alerts/169
- MSCIO 135/26: 9 October ~10:00 UTC, 13 NM west of Al Jazeera, UAE. IMO table lists **GEM NO. 2**, IMO **9735373**, on 9 October at the same reported location. MSCIO: https://mscio.eu/alerts/171
- MSCIO 148/26: 16 October ~19:22 UTC, 78 NM northeast of Al Jubayl, Saudi Arabia. IMO table lists **LOYALTY**, IMO **9182306**, on 16 October at the same reported location. MSCIO: https://mscio.eu/alerts/184

These are strong entity-resolution *candidates* because date and geographic descriptions align. They are **not** automatically independent corroborations: IMO may rely on the same original incident notification. No MMSI, exact event geometry, publication timestamp or AIS match was invented. Retain original MSCIO observation and separately link the IMO list with an unverified lineage relation pending origin-chain investigation.

Important dedup regression: IMO lists **AL DASMA (9653446)** on 7 September and again on 20 October (second attack). Same IMO is NOT sufficient to merge separate episodes across dates.

Data-quality quarantine: IMO table displays `CAMEROON PROSPERITY (IMO 93151598)` on 4 October; this is eight digits, not a valid seven-digit IMO identifier. Do not auto-correct or use it for vessel identity without separate verification.

### Current-window candidate guardrails
- MSCIO 158/26, event 29 Oct 16:00 UTC, unidentified tanker, Strait of Hormuz: https://mscio.eu/alerts/194
- UKMTO 190/26, event 30 Oct 14:19 UTC, fishing vessel boarding: **suspicious activity**, not a confirmed attack; origin and hull identity unresolved.
- CONTSHIP JET, IMO 9348625 / MMSI 636019532, attack 28 Oct 10:00 UTC, remains regression (outside exact 72-hour event window at this audit time). Primary authority: https://www.mod.bg/news9664 . AIS slowdown is a temporal signal, never independent attack proof.

## Rights and latency
IMO website terms explicitly permit copying/reuse for **personal, non-commercial** purposes with attribution and prohibit commercial reuse, with possible further restrictions. Source: https://www.imo.org/en/about/pages/imo-website-terms-and-conditions-of-use.aspx . Thus do not bulk ingest, republish or commercially redistribute IMO material without rights review; link and record limited investigatory metadata only where permitted. Public web availability is not an API SLA. MSCIO reuse terms also require separate review. Source publication/receipt latency cannot be measured from an IMO snapshot without timestamps.

## Gates still open
1. Oracle production PostgreSQL read-only account/access (do not escalate).
2. Source licensing, originating authority and independence lineage for IMO ↔ MSCIO ↔ UKMTO.
3. Authorized staging import of reviewed official bulletin envelopes; still opt-in, no collector and no new VM cron.
4. LIVE/PLAY incident projection with distinct maritime-attack UI, cache freshness and false-positive controls.
5. Never promote PLAY -> incident or assign aggressor without reviewed, independent evidence and explicit release authorization.
