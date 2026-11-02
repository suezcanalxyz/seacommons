# SeaCommons — Maritime attack staging review: AIS summary integrity and MSCIO 164/26

Audit time: **2026-11-02 10:26–10:34 UTC**. Baseline: `638b4c55` (previous staging report). Branch: `feature/maritime-attack-correlation-20261030`.

## Implementation, staging only

- `apps/api/core/intel/maritime_attack_staging_case_review.py`: revalidate caller-supplied AIS review summaries before displaying them: exact event-clock linkage, no AIS-derived incident geometry, bounded and ordered AIS fixes, coordinate/speed sanity, sampling-gap consistency, coverage and sudden-stop flags, receipt-status vocabulary. This prevents forged or stale summary fields from being displayed as a real slowdown. The review is still **not cryptographic authentication** of raw AIS records.
- `tests/test_maritime_attack_staging_case_review.py`: reject forged event clock, geometry, gap, coverage, speed, sudden-stop flag, kinematic conflict, receipt status, impossible fix time, and future vessel position.
- `docs/research/maritime-attack-mscio-164-2026-11-02.json`: new metadata-only source record, **MSCIO 164/26**. Source: https://mscio.eu/alerts/200 . Reported attack approximately **2026-11-01 15:09 UTC**, Strait of Hormuz. A merchant master **relayed another vessel's VHF Ch16 Mayday** reporting a projectile hit. Affected vessel, IMO, MMSI, precise coordinates, crew condition and aggressor **unknown**. Publication date 1 Nov, source check date 2 Nov; rights conservatively `restricted_republication`; no source independence verified, no promotion. Do not merge with the unrelated northern-Gulf tanker attack reported as UKMTO 192/26 at 23:47 UTC.
- `tests/test_maritime_attack_staging_manifest.py`: regressions preventing an invented vessel identity and ensuring the new alert remains distinct from the October batch.
- `.github/workflows/maritime-attack-correlation-staging.yml`: watch MSCIO 163/26 and 164/26 manifests for future CI changes.

CI on `bba0adc1`: https://github.com/suezcanalxyz/seacommons/actions/runs/41429416741 — **success**: 407 maritime unit tests, 23 bulletin tests, 3 SQLite tests, 11 isolated PostgreSQL tests = **444 Python tests**; frontend taxonomy tests and build successful. No production credentials in CI.

## Oracle PostgreSQL read-only audit

Existing application `DATABASE_URL` used without exposing credentials. SQL transaction explicitly `READ ONLY`, `statement_timeout=5000ms`, rollback; no writes. At **2026-11-02 10:26:59 UTC**, rolling cutoff **2026-10-30 10:26:59 UTC**:

| Relation | Count in 72h |
| --- | ---: |
| `intel_events` | 10,300 |
| `vessel_tracks` | 806,626 |
| `alert_events` | 0 |
| `anomaly_events` | 0 |
| `humanitarian_incidents` (`last_update_at`) | 12 |
| `forensic_events` | 11 |

Compared with prior 09:26 audit: intel 10,241; tracks 805,025; alerts/anomalies 0; forensics 11. Rolling-window differences are **not ingest rates**. The previous humanitarian 21 may have used a different update-field definition; do not interpret 21→12 as a verified decline.

October exact `source_observations.observation_type='official_maritime_bulletin'`: **0**. October attack/piracy/explosion/sinking `maritime_episodes`: **0**.

CONTSHIP JET regression: `mmsi='636019532'`, 28 Oct 09:45–11:10 UTC: **five AIS fixes**. 09:59:22 speed 10.2 kn; 10:34:46 speed 0.6 kn. All five `received_at=ts`; independent receipt latency unavailable. The Bulgarian Ministry of Defence report https://www.mod.bg/news9664 describes the 10:00 UTC attack; Bulgarian NAVWARN 768/26 https://www.vtmis.bg/wx/wx_eng.htm describes the 20:30 UTC sinking, IMO 9348625. Neither the AIS slowdown nor later sinking is a second attack witness. The attack site is not inferred from AIS or wreck geometry.

LOUISE 1 proposed MMSI 352003797: **0 AIS fixes** on 29–30 October. No synthetic gap or trajectory.

## LIVE/PLAY

Read-only public endpoints https://api.seacommons.org:
- `/api/v1/play/counts`: 3,578 total, 3,449 maritime, 129 humanitarian (snapshot 09:29:52 UTC).
- Eight bounded pages `/api/v1/play/incidents?limit=500&offset=...`: 3,579 rows, 3,573 unique IDs, six duplicated IDs; zero attack/piracy/sinking/explosion categories among returned rows. **Pagination is not snapshot-consistent.**
- `/api/v1/live/signals?limit=300&days=3&mode=all`: 13 signals, zero attack-like categories.
- `/api/v1/live/pipeline`: AIS and radio live; partner degraded; 61 DSC accepted; NAVTEX 0.

## Source access measured from Oracle VM

One-off bounded HTTP requests, **HTTP response time only** (not publication-to-ingestion latency): Bulgarian MOD 200/464 ms; VTMIS 200/126 ms; MSCIO 164 200/368 ms; MSCIO 162 200/396 ms; UKMTO homepage 200/229 ms; IMO 200/136 ms; MARAD 403/31 ms; NATO Shipping Centre 403/41 ms; ONI 403/31 ms; GDELT timeout ~7.1 s. No access restrictions bypassed.

**Other candidate:** UKMTO Warning 192/26, reportedly 1 Nov 23:47 UTC, tanker hit by two unknown projectiles 72 NM east of Ras Al Khafji. Secondary reports: https://www.iranintl.com/en/202611025952 . Official numbered document not independently retrieved in this run, so **no canonical staging manifest** and no identity/attacker attribution. This is distinct from MSCIO 164/26 (15:09 UTC Strait of Hormuz Mayday relay).

## Remaining blockers

1. Official bulletin observations absent from production canonical store; isolated persistent staging store/reviewer not yet connected.
2. Verify original document hashes and originating witness lineages; MSCIO/UKMTO may relay the same Mayday, and two publishers are not two independent witnesses.
3. Confirm source-specific reuse rights, exact source acquisition timestamps, and UKMTO 192/26 primary document.
4. Resolve PLAY pagination consistency before claiming exhaustive catalog coverage.

**No production deployment, no Oracle writes, no historical modifications, no incident promotion, no new cron/timer/loop on the VM.**
