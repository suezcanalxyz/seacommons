# Maritime attack staging case review and Oracle audit — 2026-11-02 06:23 UTC

Scope: SeaCommons attack-correlation staging branch only. No production write, no
new VM scheduler, no publication, no historical mutation. This report compares
the prior 2026-11-02 05:22 UTC run (commit `85214f88`) to this run.

## Concrete change

Introduced `maritime_attack_staging_case_review.py`, an opt-in, pure staging
composition helper. It joins ONE already validated attack candidate to
subsequent, named-vessel context previews (investigation, rescue, navigation
hazard) and optional read-only AIS context. It cannot fetch/write a database,
promote to PLAY, schedule tasks, or change attack geometry.

Added the official Bulgarian Ministry of Transport as a source issuer
(`BG_TRANSPORT`) with an exact HTTPS host allowlist and a separate `rescue`
source kind. The ministry's 28 October 2026 statement documents the
CONTSHIP JET rescue and an MRCC Constanta notification; it is **not** an
independent second attack witness. Its original publication has a day-only
date, and the manifest preserves that precision. Its website permits reuse
with attribution and notice of modifications; no logo rights are assumed.

The case-review guard rejects foreign vessel names, conflicting IMO/MMSI,
duplicate report IDs, attack documents disguised as context, later hazards
that predate the attack, incorrect location roles, cross-case AIS joins,
unreviewed identity promotion, and any attempted publication. Later wreck
coordinates remain a `hazard_position`, not an attack point. The geospatial
comparison is only a nominal great-circle distance from a dated AIS fix to
the later hazard position; source uncertainty is explicitly unquantified.

## CONTSHIP JET regression (read-only Oracle AIS + in-memory source previews)

- BG MOD `news9664`: 28 October 10:00 UTC, attack, three observed impacts;
  source names vessel but does not state IMO/MMSI.
- BG TRANSPORT `20261028-contship-jet-rescue`: 28 October, day-only rescue
  context, not an attack witness.
- BG PROSECUTOR `80101`: 29 October, investigation context, not an attack
  witness.
- BG VTMIS `NAVWARN 768/26`: 28 October 20:30 UTC sinking/hazard at
  43.130000 N, 28.756000 E, official IMO 9348625; not a second attack.
- Oracle `vessel_tracks` for MMSI 636019532: five rows in 09:45–11:10 UTC,
  28 October. SOG 10.2 kn at 09:59:22, 0.6 kn at 10:34:46;
  AIS sampling gap 35.396 min. The AIS stop is a **signal**, never proof.
- Staging bundle: `staging-case-review:obs:f779260a02490a03e91e00d858917e62`.
  Three follow-up roles are preserved separately. Sinking follows attack
  by 630 minutes. Nominal separation from 10:34 AIS fix to wreck position
  15.16 km over 9.92 hours; **uncertainty not quantified**, no inferred route.
- Official IMO 9348625 from NAVWARN is visible as a proposed identity
  cross-reference. MMSI 636019532 remains an **unverified external crosswalk**;
  NAVWARN does not state MMSI.
- `attack_reported_location=null`, `independent_origins_verified=0`,
  `ais_as_attack_proof=false`, `publication_allowed=false`.
  No aggressor is attributed.

The source previews in this combined test were built from validated manifests
and in-memory observation fixtures, **not** rows persisted in Oracle.
Only AIS tracks were read from Oracle. Earlier isolated PostgreSQL writer
tests establish a separate persistence contract, not an Oracle staging
publication pipeline.

## Oracle PostgreSQL read-only audit

At approximately 06:22 UTC, using the existing application connection with
`PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=8000'`.
No credentials are printed or changed. For varchar ISO clocks, use lexical
`left(timestamp_utc,19)` comparisons; direct comparison to a SQL timestamp
is a type error. 72-hour cutoff `2026-10-30T06:22:52`.

| Table / query | Result |
|---|---:|
| `intel_events` with `left(timestamp_utc,19)>=cutoff` | 10,070 |
| `vessel_tracks` with `ts >= now() - interval '72 hours'` | 802,844 |
| `alert_events` | 0 |
| `anomaly_events` | 0 |
| `humanitarian_incidents` updated within 72h | 21 |
| `forensic_events` | 11 |
| `source_observations` official bulletin / relevant source names, Oct–Nov 2 | 0 |
| `maritime_episodes` attack/piracy/sinking/explosion families, Oct–Nov 2 | 0 |

Previous rolling-window counts at 05:22 UTC: intel 10,007 and AIS 802,148.
Differences +63 and +696 are **not** direct ingestion counts because windows
move. A broad regex query for textual attack candidates timed out at 8s and
must not be represented as an exhaustive negative result.

The `source_observations` population remains dominated by AIS gap/nav
status and radio observations, not official maritime bulletins.

## Public LIVE/PLAY (06:23 UTC)

- `/api/v1/play/counts`: 3,577 total, 3,448 maritime, 129 humanitarian;
  snapshot generated 05:23:35 UTC.
- Full paginated `/api/v1/play/incidents` scan returned 3,578 rows, only
  3,572 unique IDs, no attack/piracy labels in the rows returned. The
  pagination is **not a consistent snapshot**; do not claim every unique
  incident was checked exactly once.
- `/api/v1/live/signals?limit=200&days=3&mode=all`: 15 signals, zero
  attack/piracy labels; includes navigation casualty, AIS gap and two
  humanitarian distress items.
- `/api/v1/live/pipeline`: AIS/first-party/public-feed live, partner
  degraded, radio live; 60 accepted DSC, zero accepted NAVTEX.

No attack has been promoted or published by this run.

## Recent and October source checks

- MSCIO 162/26, event 30 Oct ~18:00 UTC, projectile/fire 40 NM south of
  Lavan Island: candidate, ship unidentified, no independent witness
  certified. Source: https://mscio.eu/alerts/198
- Nakilat AL MAYEDA: operator report of 30 Oct evening impact, published
  1 Nov; keep distinct from MSCIO 162/26 unless identity/location/time
  independently match. See public Qatar Stock Exchange/operator statement.
- Reuters 1 Nov: IRGC Navy claimed two tankers exploded on mines in Hormuz;
  no ship IDs or independent confirmation in this audit, not promotable.
- MSCIO 159/26, 29 Oct ~22:12 UTC, explosive devices on tanker; retroactive
  candidate, potentially LOUISE 1 from Reuters, identity not certified.
  Source: https://mscio.eu/alerts/195
- MSCIO 161/26, AZINI reported hijacked 29 Oct ~09:00 UTC, retroactive
  piracy candidate; last-known position is not incident location.
  Source: https://mscio.eu/alerts/197
- BG VTMIS NAVWARN 779/26, 780/26, 781/26 describe 1 Nov drifting
  containers/boat around Burgas, **navigation hazards, not attacks** and
  not automatically CONTSHIP JET follow-ups. Primary:
  https://www.vtmis.bg/wx/wx_eng.htm
- MARAD 2026-012 remains a Black Sea regional advisory, not an individual
  incident witness. IMO GISIS piracy reports require registration; monthly
  published reports are not necessarily real-time.

### Availability from Oracle VM (one-shot GET, 8s cap)

| Source | Result | HTTP response time |
|---|---|---:|
| Bulgarian MOD | 200 | 408 ms |
| Bulgarian Transport | 200 | 285 ms |
| Bulgarian Prosecutor | 200 | 369 ms |
| Bulgarian VTMIS | 200 | 111 ms |
| MSCIO 159/26 | 200 | 365 ms |
| MSCIO 162/26 | 200 | 414 ms |
| IMO | 200 | 137 ms |
| UKMTO | 403 | 67 ms |
| MARAD | 403 | 24 ms |
| NATO Shipping Centre | 403 | 25 ms |
| ONI | 403 | 22 ms |
| GDELT DOC API | URL error / timeout | 8,126 ms |

Do not bypass 403s. These are HTTP response times, **not** the latency
between event, publication and ingestion. The latter remains unmeasurable
until a permitted source collector records actual receipt timestamps.

Rights: MOD and Bulgarian Transport allow public reuse with attribution;
UKMTO declares Open Government Licence subject to conditions and possible
third-party rights; MSCIO restricts republication; VTMIS reuse rights remain
unverified. All new observations retain `publication_allowed=false`.

## Tests and operational boundaries

Local Python 3.12: 390 maritime-attack unit tests and 23 official-bulletin
unit tests passed. The new staging case-review suite includes positive and
negative regressions (wrong vessel, duplicate, spoofed URL, wrong IMO/MMSI,
future AIS, location role, fake promotion, and day-only rescue).
The isolated SQLite/PostgreSQL writer jobs and frontend build require CI;
they were **not** rerun locally in this run. The staging workflow now watches
the new code/test/manifest paths.

Next: certify CI on the pushed staging branch; establish a truly isolated
staging database and authenticated review surface; verify original document
hashes, independent origin lineage and MMSI registry evidence; implement
reviewed-only PLAY promotion behind explicit approval. No production deploy.
