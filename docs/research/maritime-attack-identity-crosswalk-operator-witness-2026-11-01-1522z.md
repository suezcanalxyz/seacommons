# SeaCommons — IMO/MMSI crosswalk and first-party incident witness audit
Date: 2026-11-01 ~15:22 UTC (16:22 Africa/Tunis). Branch: `feature/maritime-attack-correlation-20261030`.
Baseline: `069d226b`. No production deployment, Oracle mutation, VM scheduling, or historic-record rewrite.

## Concrete code change: false vessel crosswalk blocked
The previous identity-linker accepted a reviewed IMO-only record and a different reviewed MMSI-only record whenever both carried the same normalized vessel name. That silently formed a crosswalk neither source actually asserted. Same-name collisions, recycled MMSIs, or inaccurate aggregator labels could therefore link AIS for the wrong ship. The link was only `linked_for_review`, not attack proof, but could contaminate later geospatial review.

`maritime_attack_identity_evidence.py` now blocks an identity result containing both IMO and MMSI unless **one** original bulletin or **one** reviewed external identity record explicitly prints both resolved IDs. Failure reason: `identity_imo_mmsi_crosswalk_unverified`. Name equality alone is insufficient. The original bulletin and evidence are never mutated; publication and attack corroboration remain disallowed.

Three new offline regression tests:
1. IMO-only + MMSI-only with the same name, distinct URLs and IDs -> BLOCKED.
2. IMO-only + a reviewed record explicitly printing both IDs -> `linked_for_review`, never attack proof.
3. Synthetic bulletin IMO-only + external MMSI-only -> BLOCKED.
Files changed: `apps/api/core/intel/maritime_attack_identity_evidence.py` and `tests/test_maritime_attack_identity_evidence.py`.
Commits: `89b99ff65a4678f0e94eb1b3c37f1aa1fb47ecff`, `5c32575183893e9e24420c14ac46d427f5b54569`.
CI verified after drafting: https://github.com/suezcanalxyz/seacommons/actions/runs/41320929962 completed SUCCESS on test commit `5c32575183893e9e24420c14ac46d427f5b54569` at 15:23 UTC. Logs: 308 correlation tests + 19 official adapter + 3 SQLite + 6 isolated PostgreSQL = **336 Python PASS**; frontend **5 JavaScript PASS** and build succeeded. Documentation-only commit is not itself a new functional test run.

## NEW first-party incident evidence: Contships Management company update
Source: https://contships-management.com/2026/10/29/contships-management-inc-company-update/
Retrieved via public web on 2026-11-01. The page is **posted 29 October**, but the statement itself is datelined **Athens, 28 October**; neither provides an exact publication clock or an exact incident time.

The ship's manager confirms CONTSHIP JET, IMO 9348625, was attacked off Bulgaria in the Black Sea by three sea drones of unknown origin. Crucially, it explicitly cites **reports received and a statement made by the Master**, plus serious damage, listing and safe evacuation of 18 crew. This is stronger than the operator's static fleet page because it is an **incident statement containing the IMO**, not merely a ship identity listing.

Separate primary source: Bulgarian Ministry of Defence https://www.mod.bg/news9664 (28 October). The ministry reports three impacts and observations by naval surveillance and a French patrol aircraft, with attack at 12:00 local (10:00 UTC after Bulgarian daylight-saving transition), but it does not print IMO/MMSI. The French observation appears within the same ministerial report; do not count it as a separate published source without original evidence.

Potential independent originating lineages:
- `BG_NAVY_OBSERVATION`: Ministry of Defence, naval surveillance / French patrol observation as reported by ministry.
- `VESSEL_MASTER_STATEMENT`: Ship manager's 29 October statement citing the Master's account.

These **might** be independently originated observations, but dependence and chain-of-custody have NOT been verified. The manager also refers to unspecified "reports received" and may incorporate the ministry account. **No automatic two-source corroboration or PLAY promotion**. Human review must verify the Master's original statement or equivalent first-party trace and mark source lineage explicitly.

The company statement supplies IMO 9348625; Flexport Atlas https://atlas.flexport.com/vessel/imo:9348625/mmsi:636019532/name:contship-jet shows both IMO and MMSI and can serve as a potential **identity crosswalk** if licensed and reviewed. It is not attack evidence. The operator statement does not print MMSI.

Data rights: Ministry says public information may be copied with attribution (see footer of ministry page). Operator statement is © 2026 Contships; no free redistribution license established. Flexport states use subject to terms; no automated copying or republishing authorized by this audit. Metadata-only links may be retained for review. Exact source receipt clocks were not obtained; never invent them.

## LIVE/PLAY read-only public API check
Queried from the authorized remote device at ~15:22 UTC, with GET only:
- `https://play.seacommons.org/api/v1/play/counts`: HTTP 200; total 3572, maritime 3444, humanitarian 128, investigation 3434; `generated_at=2026-11-01T14:39:42.404288Z`.
- `https://play.seacommons.org/api/v1/play/incidents?limit=1`: HTTP 200; total 3572; `generated_at=2026-11-01T15:22:26.655416Z`.
- `https://live.seacommons.org/api/v1/live/pipeline`: HTTP 200; `generated_at=2026-11-01T15:22:26.943272Z`; AIS, first-party, public feeds, radio live; partner degraded. Radio shows `navtex_accepted=0` in current decoder statistics, so radio "live" is not proof of usable NAVTEX ingestion.
Counts and catalog agree on the total but are **not** synchronized snapshots; counts projection is ~43 minutes older than catalog. HTTP 200 does not certify attack promotion or freshness of every source.

## Oracle PostgreSQL: blocked, no fresh row claims
Remote device `instance-20260828-1159` online. `psql -X -w -Atqc 'SHOW transaction_read_only'` returned `FATAL: role "ubuntu" does not exist`. No credential search, escalation, or database writes attempted. Fresh read-only SQL result count: **zero**. Earlier table counts remain historical, not current.
The seven target datasets remain to be inspected: `intel_events`, `vessel_tracks`, `alert_events`, `anomaly_events`, `humanitarian_incidents`, `forensic_events`, and LIVE/PLAY projections. The staging test PostgreSQL is not production Oracle.

Prepared, **not executed**, authorized SQL (run only with an approved read-only role):
```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '6000ms';
SELECT id, mmsi, ts, received_at, sog, lat, lon
FROM vessel_tracks
WHERE mmsi = '636019532'
  AND ts >= TIMESTAMP '2026-10-28 09:30:00'
  AND ts <= TIMESTAMP '2026-10-28 11:30:00'
ORDER BY ts, id LIMIT 257;
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('intel_events','vessel_tracks','alert_events',
    'anomaly_events','humanitarian_incidents','forensic_events')
  AND (column_name ILIKE '%time%' OR column_name ILIKE '%_at'
       OR column_name IN ('ts','mmsi','imo','id'))
ORDER BY table_name, ordinal_position;
ROLLBACK;
```
Only after introspection choose each table's actual event/received clock for 72h and October scans. Never substitute publication or receipt date for unknown event time.

## Recent candidates and strict boundaries
- CONTSHIP JET / IMO 9348625 / MMSI 636019532: 28 Oct ~10:00 UTC, Bulgarian Black Sea. Ministry and new operator incident statement; potential independent witness lineages **unverified**. AIS deceleration 10.2 kn at 09:59:22 -> 0.6 kn at 10:34:46 is context only; Oracle receipt clocks still unverified.
- MSCIO 159/26: event 29 Oct 22:12 UTC, 25 NM NE Khasab, Oman; https://mscio.eu/alerts/195 . Reuters named LOUISE 1 from security sources; IMO/MMSI not verified. UKMTO 187 and MSCIO may share original reporting, so no independent double count.
- MSCIO 162/26: event 30 Oct 18:00 UTC, 40 NM south of Lavan Island; https://mscio.eu/alerts/198 . Reported port-side strike and fire, crew safe; ship ID unknown. UKMTO 188 appears same incident, lineage unverified.
- MSCIO 163/26: published 30 Oct but describes 28 Oct event; https://mscio.eu/alerts/199 . Keep event/publication clocks separate; UKMTO 189 likely a relay.
- MSCIO 161/26 / AZINI: hijacking reportedly 29 Oct 09:00 UTC off Somalia; https://mscio.eu/alerts/197 . Subsequent last-reported positions are NOT the hijack site; UKMTO 190 must not be auto-merged.
- MSCIO 160/26: 30 Oct 02:25 UTC, Gulf of Aden, suspicious approach, **no shots/boarding**; https://mscio.eu/alerts/196 . Negative control: not an attack.
- NEW 31 Oct Qeshm fishing-boats candidate: Reuters https://www.reuters.com/world/middle-east/iran-provincial-official-says-us-attacked-fishing-boats-off-qeshm-island-state-2026-10-31/ attributes an alleged drone attack on **two unnamed fishing boats** near Qeshm Island to Iranian media/officials. The reported injuries and missing-person counts vary by source/update. The reported US responsibility is **an allegation only**, with no independent US confirmation; no IMO/MMSI, no precise independently verified attack coordinates or event clock. Keep in PLAY review, not confirmed or attacker-attributed. Reuters' republication of IRIB/Fars is not an independent eyewitness.
- NEW 1 Nov AZINI reporting: AP https://apnews.com/article/dd4d404235781a3b871668c353540e4c reports a Puntland Maritime Police Force officer's account of the 29 Oct seizure. Potentially a different originating witness from MSCIO's notice, but original reporting dependence remains to be established. Do not automatically count two independent reports or map the 30 Oct last position as hijacking site.
- Retrospective October: UKMTO warnings 180 (20 Oct), 181 (22 Oct), 182 (23 Oct), 175 (16 Oct) accessible via https://www.ukmto.org/ . These are candidate incident reports, not automatically unique from MSCIO relays.

## Next safe gates
1. Confirm CI for new crosswalk tests. If green, keep this guard on staging.
2. Read-only Oracle access through an approved DB role; verify actual `received_at` for CONTSHIP JET and source ingestion coverage.
3. Model operator Master's statement as a distinct source-origin claim with day-only time, provenance and explicit manual lineage review, not as a second "official" bulletin or automatically independent report.
4. Stage the end-to-end chain and test false positives/negatives, source lineage, duplicate alerts, and attack UI category/color separately from humanitarian drift.
5. Never deploy to production without explicit approval.
