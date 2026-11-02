# SeaCommons — Maritime attack source-observation integrity audit
UTC observation window: 2026-10-30 03:18 to 2026-11-02 03:18
Branch: `feature/maritime-attack-correlation-20261030`
Baseline: `49bbe53b` (prior run); functional changes: `4c2d21fc`, `920153b0`.
Production deploy: **not performed**. Oracle writes: **none**. VM schedulers: **none added**.

## What changed
`apps/api/core/intel/maritime_attack_staging_preview.py` now fails closed when a persisted SourceObservation's `observed_at`, `lat`, `lon`, `uncertainty_m` or `location_precision` differs from the source-faithful official bulletin envelope. Float comparisons allow storage rounding, not an invented location. The preview exposes `canonical_observed_at`, `observed_at_semantics`, and the original reported location with role and uncertainty (or `null`); it does not invent incident coordinates.

The canonical `received_at` must contain a clock (not a day-only string), and must not precede the documented event, publication, source date or operator source-check day. Date-only evidence remains day-only. A canonical naive UTC receipt is accepted only under the existing DB convention; external source clocks remain timezone-aware.

`tests/test_maritime_attack_staging_preview.py` adds three tests: source-clock/position tampering, receipt chronology, and documented location role/uncertainty; it also extends the day-only receipt negative test. All nine preview tests passed in an isolated Git worktree. The CI for `920153b0` completed successfully: 361 maritime Python tests + 23 official bulletin tests + 3 SQLite + 8 isolated PostgreSQL = **395 Python tests**; 5 JavaScript tests and frontend build also passed.
CI: https://github.com/suezcanalxyz/seacommons/actions/runs/41382500456

## Oracle PostgreSQL — read-only
Queries used existing authorized application connection, with `PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=7000'`; no transaction modified data.

- `intel_events` by text ISO `timestamp_utc >= '2026-10-30T03:18:00'`: **9,877**.
- `vessel_tracks` by timestamp `ts >= now()-interval '72 hours'`: **801,416**.
- `alert_events`: **0**; `anomaly_events`: **0**; `forensic_events`: **11** (same ISO timestamp cutoff).
- `humanitarian_incidents` by `updated_at`: **21** (updated, not necessarily new distress).
- `source_observations` of type `official_maritime_bulletin` observed during October–2 Nov: **0**.
- `maritime_episodes` family matching `attack|piracy|sinking|explosion`: **0**.
- October episodes by family include `gap_episode=2079`, `spoofing_episode=228`, `safety_episode=67`; these are **not attack confirmations**.
- Search for October `intel_events` with UKMTO/MSCIO/MARAD/Bulgarian MOD source names/URLs: **0**.

The first attempt to compare text `timestamp_utc` directly to PostgreSQL `now()` failed with a type mismatch. The successful counts use an ISO UTC string cutoff consistent with sampled `timestamp_utc` values; they are not counts by receipt time.

CONTSHIP JET, IMO 9348625 / MMSI 636019532, 2026-10-28 10:00 UTC regression:
- 09:57:55 UTC: 10.8 kn, 43.26831 N, 28.818947 E
- 09:59:22 UTC: 10.2 kn, 43.265927 N, 28.814900 E
- 10:34:46 UTC: 0.6 kn, 43.259197 N, 28.815740 E
- 10:46:24 UTC: 0.7 kn
- 10:58:15 UTC: 0.8 kn
`received_at` matched `ts` in these rows; no independent ingestion-latency inference is possible. AIS speed reduction is **context only**, never independent attack evidence. The Bulgarian Ministry of Defence identifies the ship by name and reports three impacts, but the source does not supply IMO/MMSI: https://www.mod.bg/news9664

## LIVE / PLAY public read-only checks
- PLAY `/api/v1/play/counts`: total **3,576**, maritime **3,447**, humanitarian **129**, investigation **3,437**; counts snapshot generated 2026-11-02 02:41:27 UTC.
- Complete paginated PLAY scan: **3,576/3,576**, **0** items with attack in `incident_type`, `visual_category`, or `episode_family`.
- LIVE `/api/v1/live/signals?limit=100&days=3&mode=all`: **11** signals, **0** attacks.
- LIVE pipeline 2026-11-02 03:19 UTC: AIS/first-party/public feeds live, partner degraded, radio live with **56 DSC accepted** and **0 NAVTEX accepted**.
These checks do not certify transactional consistency between PLAY counts and catalog.

## Verified source candidates / controls
- MSCIO **162/26**: event approximately 2026-10-30 18:00 UTC, 40 NM south of Lavan Island, unknown vessel, impact/fire reported. Candidate only; no verified vessel identity or independent corroboration. https://mscio.eu/alerts/198
- MSCIO **159/26**: event approximately 2026-10-29 22:12 UTC near Khasab, tanker reportedly attacked with two devices. Retrospective (outside the precise 72-hour cutoff). https://mscio.eu/alerts/195
- MSCIO **160/26**: 2026-10-30 02:25 UTC, suspicious approach; **no shots, no boarding**. Negative control, not an attack. https://mscio.eu/alerts/196
- MARAD **2026-012**: active Black Sea / Sea of Azov *regional risk advisory*, not evidence for an individual incident. https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations
- UKMTO conditions: Open Government Licence with attribution and third-party rights caveats; UKMTO reports may be shared with MSCIO, so cross-posts do not automatically count as two independent origins. https://www.ukmto.org/terms-and-conditions

## Source access from Oracle VM (single HEAD request each)
BG MOD 200 / 439 ms; MSCIO 159/26 200 / 301 ms; MSCIO 162/26 200 / 242 ms; IMO 200 / 117 ms. MARAD 403 / 22 ms; UKMTO 403 / 46 ms; NATO Shipping Centre 403 / 109 ms; ONI 403 / 502 ms. HTTP RTT is **not** source publication-to-ingest latency. No access restrictions were bypassed. GDELT availability/terms and NAVTEX end-to-end decoding were **not revalidated** in this run.

## Release gates / next work
The repaired source preview is **staging-only**, `publication_allowed=false`, `independent_origins_verified=0`. No official attack observations exist in the current production canonical store. Next: test the same integrity guard against real isolated PostgreSQL staging rows and an authenticated reviewer surface; verify source origin lineage and independently supported IMO/MMSI crosswalks. Only after manual approval may a corroborated attack become a canonical episode and be considered for PLAY. Never attribute an aggressor based solely on AIS gaps, stops, or relayed bulletins.
