# SeaCommons — attack correlation: prosecutor context and persisted PostgreSQL audit

**Audit window (UTC):** 2026-10-30 04:21:21 through 2026-11-02 04:21:21.
**Baseline:** `7cf227e0` (previous execution).
**Branch:** `feature/maritime-attack-correlation-20261030`.
**Production deployment:** none. **Oracle writes:** none. **VM cron/timers/schedulers:** none added.

## Functional changes

- `maritime_attack_staging_preview.py` now exposes review blockers `original_document_hash_unavailable` and `incident_location_unverified` for source-faithful staging previews. A SHA-256 of locally structured metadata is not a SHA-256 of the original published bulletin. A last-known vessel location is not an incident site.
- The Bulgarian Military Prosecutor's **29 October 2026** notice on CONTSHIP JET is now an opt-in separate one-record staging manifest (`maritime-attack-prosecutor-source-check-2026-11-02.json`). It is classified as `investigation` and `context_only`, **not** a second independent attack witness. The document reports that the Varna Military Police referred the incident for investigation; the report itself has a publication date, but no original minute-precise event clock or IMO/MMSI.
- The original six-source manifest checked on 1 November remains immutable and unchanged; the new notice has a separate 2 November source-check clock.
- The preview now reports provenance mismatch **field names only**, never evidence contents, to support forensic debugging.
- Added isolated PostgreSQL tests for real SQLAlchemy reloads, tamper rejection and the prosecutor document. An intermediate test failed because mutating ORM objects followed by lazy loading caused autoflush inside the disposable test transaction; the regression was corrected to tamper a cloned canonical dataclass while verifying the actual rehydrated PostgreSQL rows separately. No production database was affected.

## Verification

CI for functional commit `b0e971b3170ce3e4c75238a37f28c1db59bbc027`: https://github.com/suezcanalxyz/seacommons/actions/runs/41388475850

- Maritime correlation unit tests: **363 passed**.
- Official bulletin tests: **23 passed**.
- SQLite: **3 passed**.
- Isolated PostgreSQL: **10 passed**, including real PostgreSQL reload and rollback.
- **Total Python: 399 passed.** Frontend attack taxonomy job succeeded (5 JS tests and frontend build).

## Oracle PostgreSQL: read-only, no changes

Authorized application DB URL was used with `PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=8000'`, `psql` SELECT-only queries. 72h cutoff: `2026-10-30T04:21:21`.

| Source | Query condition | Count |
|---|---|---:|
| `intel_events` | `timestamp_utc >= '2026-10-30T04:21:21'` (text ISO) | 9,950 |
| `vessel_tracks` | `ts >= now() - interval '72 hours'` | 801,780 |
| `alert_events` | same text ISO cutoff | 0 |
| `anomaly_events` | same text ISO cutoff | 0 |
| `humanitarian_incidents` | `updated_at >= now() - interval '72 hours'` | 21 |
| `forensic_events` | same text ISO cutoff | 11 |
| `source_observations` | `observation_type='official_maritime_bulletin' AND observed_at >= '2026-10-01'` | 0 |
| `maritime_episodes` | family regex `attack|piracy|sinking|explosion` | 0 |

These are moving windows, not a differential ingest count. Source-name search of official publishers since 1 October also returned zero.

CONTSHIP JET (IMO 9348625; MMSI 636019532): original `vessel_tracks` positions on 28 October: 09:57:55 UTC / 10.8 kn; 09:59:22 / 10.2 kn; 10:34:46 / 0.6 kn; 10:46:24 / 0.7 kn; 10:58:15 / 0.8 kn. In these legacy rows `received_at=ts`; ingestion latency cannot be inferred. AIS speed reduction is contextual only, never independent attack corroboration.

## Public LIVE/PLAY checks

- `/api/v1/play/counts`: HTTP 200; 3,576 total (3,447 maritime, 129 humanitarian), **snapshot timestamp 03:19:15 UTC**.
- Complete paginated `/api/v1/play/incidents` scan later in this run: **3,577 records**, **0** with attack in `incident_type`, `visual_category`, or `episode_family`. The difference from counts is due to differing query times/snapshots and is not a certified count discrepancy.
- `/api/v1/live/signals?limit=100&days=3&mode=all`: HTTP 200; **13 signals**, **0 attacks** in the response.
- `/api/v1/live/pipeline` 04:22:44 UTC: AIS/first-party/public feeds live, partner degraded; radio live with **58 DSC accepted**, **0 NAVTEX accepted**.

## Sources, rights, and access

- Bulgarian Ministry of Defence, 28 Oct: https://www.mod.bg/news9664 — names CONTSHIP JET, three impacts, rescue; public with explicit attribution; no IMO/MMSI in the primary bulletin.
- Bulgarian Military Prosecutor, 29 Oct: https://prb.bg/bg/news/aktualno/80101-voenno-okrazhna-prokuratura-sofiya-obrazuva-dosadebno-proizvodstvo-za-napadeniet — investigation opened, no independent eyewitness certified; rights **unknown**. The notice is contextual, not a second attack witness.
- MSCIO 162/26: https://mscio.eu/alerts/198 — 30 Oct ~18:00 UTC impact/fire, ship not identified; candidate only.
- MSCIO 159/26: https://mscio.eu/alerts/195 — 29 Oct ~22:12 UTC near Khasab, candidate in October retrospective.
- MSCIO 160/26: https://mscio.eu/alerts/196 — suspicious approach without shots/boarding; negative control.
- AZINI / MSCIO 161/26: https://mscio.eu/alerts/197 — 29 Oct hijacking reported; AP on 2 Nov interviewed a Puntland maritime police officer. This is a potentially distinct reporting line, but lineage independence is **not** automatically established.
- MARAD 2026-012: https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations — regional risk advisory, **not** incident proof.
- MSCIO rights: restricted republication; UKMTO: OGL with attribution/third-party caveats; prosecutor rights unknown. No source full-text republication was performed.

Single HEAD requests from Oracle VM: BG MOD 200/526ms; BG prosecutor 200/375ms; MSCIO 159 200/314ms; MSCIO 162 200/230ms; IMO 200/100ms; UKMTO 403/34ms; MARAD 403/25ms; NATO Shipping Centre 403/24ms; ONI 403/19ms; GDELT connection failed after 6.15s. These are HTTP response times, **not** publication-to-ingest latency. No restrictions bypassed.

## Next release gates

1. Original bulletin document archival/hash and source-licence review. The current structured metadata hash is insufficient.
2. Reviewer-confirmed incident-site uncertainty and independent-origin lineage (Bulgarian prosecutor notice is context, not automatically a second witness).
3. Isolated staging reviewer surface and audited promotion flow; `publication_allowed=false` until explicit review.
4. Verify complete LIVE/PLAY projection and NAVTEX decoding after staging integration. Production remains unchanged.
