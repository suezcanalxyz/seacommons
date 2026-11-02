# SeaCommons — Attack lineage evidence-integrity audit (staging only)

UTC audit window: 2026-11-02 13:25–13:37. Previous report: commit `03244f76`, audit 12:28–12:34 UTC. Branch: `feature/maritime-attack-correlation-20261030`.

## Change implemented

The suspected-lineage graph previously hashed **only graph groups and explicit links**, not the underlying source metadata. Changing a candidate's incident time, reported location, vessel IMO, document digest, receipt time or source URL without changing its report ID could leave `lineage_snapshot_sha256` unchanged. This was an integrity blind spot, not a demonstrated production exploit.

`apps/api/core/intel/maritime_attack_staging_lineage.py` now fingerprints a deterministic, report-ID-sorted source-evidence projection **alongside** groups and links. Fields include source URL, rights, check/receipt/publication/event clocks and precision, metadata/original-document hashes, reported vessel identities and source geometry (including null vs zero uncertainty). Extra untracked location fields now fail closed. This is a **derived staging snapshot hash**, not a signature of a primary bulletin. It never verifies witness independence or authorizes publication.

`tests/test_maritime_attack_staging_lineage.py` adds a regression varying each evidence field, including unknown versus explicitly zero geospatial uncertainty. Unchanged evidence remains deterministic. Test run: `PYTHONPATH=apps/api pytest -q tests/test_maritime_attack_*.py` — **430 passed, 234 subtests passed**. Ruff check passed. No GitHub Actions result claimed until it completes.

## Oracle PostgreSQL: authorized read-only audit

Used the existing authorized `DATABASE_URL` from the local application environment without printing credentials, with `default_transaction_read_only=on`, `statement_timeout=7000`, SELECT only and rollback. Snapshot **2026-11-02 13:32 UTC**; rolling 72-hour cutoff **2026-10-30 13:32 UTC**. `intel_events.timestamp_utc` and `humanitarian_incidents.last_update_at` are ISO text; `vessel_tracks.ts` and other `created_at` clocks are PostgreSQL timestamps.

| Relation / clock | Current 72h | Previous 12:28 UTC |
| --- | ---: | ---: |
| `intel_events.timestamp_utc` | 10,475 | 10,438 |
| `vessel_tracks.ts` | 810,426 | 809,433 |
| `alert_events.created_at` | 0 | 0 |
| `anomaly_events.created_at` | 0 | 0 |
| `humanitarian_incidents.last_update_at` | 11 | 11 |
| `forensic_events.created_at` | 13 | 13 |

Moving-window counts are **not** ingest deltas. October `source_observations` with `observation_type='official_maritime_bulletin'`: **0**. October `maritime_episodes`: gap 2,075; spoofing 228; safety 67; rendezvous 30; identity_integrity 3; port_call 2; attack/piracy/sinking/explosion **0**. An optional forensic classification GROUP BY failed because the guessed column `event_type` does not exist; no classification breakdown is claimed this run.

Regression on CONTSHIP JET: read-only query `vessel_tracks WHERE mmsi='636019532' AND ts BETWEEN '2026-10-28 09:45' AND '2026-10-28 11:10'` returned five fixes, including **09:59:22 UTC at 10.2 kn** and **10:34:46 UTC at 0.6 kn**. IMO **9348625** is externally sourced, not silently imputed to the Bulgarian defence statement. The speed drop is context, not proof of attack; 28 October 20:30 UTC wreck notice is a later event.

## LIVE/PLAY public read-only check

`/api/v1/play/counts` returned **3,579** (3,450 maritime, 129 humanitarian) with a 12:33 UTC cache generation timestamp. Subsequent `/api/v1/play/incidents` paginated reads returned **3,580 rows, 3,574 distinct IDs, 6 duplicates**, across eight different page timestamps. No attack/piracy category was seen, but the pagination is not a consistent snapshot; one `shipwreck` category must not be relabeled as an attack without evidence.

`/api/v1/live/signals?limit=300&days=3&mode=all` returned **12 GeoJSON features** (10 `ais_anomaly`, 1 `vessel_incident`, 1 `twitter` at the coarse type level), none explicitly attack-classified. `/api/v1/live/pipeline` reports AIS/first-party/public-feed/radio live, partner degraded, DSC accepted **62**; NAVTEX remains unverified. Coarse feature types do not establish incident classification.

## Official sources, accessibility, reuse

Measured from the authorized VM with a single streamed HTTP GET per endpoint (milliseconds are HTTP response latency, **not** publication-to-ingest latency):

| Source | Result |
| --- | --- |
| Bulgarian Defence https://www.mod.bg/news9664 | 200 / 467 ms |
| VTMIS https://www.vtmis.bg/wx/wx_eng.htm | 200 / 174 ms |
| MSCIO 164/26 https://mscio.eu/alerts/200 | **403 / 143 ms** |
| MSCIO 158/26 https://mscio.eu/alerts/194 | **403 / 112 ms** |
| UKMTO home / terms https://www.ukmto.org/terms-and-conditions | **403 / 103 and 79 ms** |
| IMO https://www.imo.org/ | 200 / 148 ms |
| MARAD https://www.maritime.dot.gov/ | 403 / 46 ms |
| NATO Shipping https://shipping.nato.int/ | 403 / 30 ms |
| ONI https://www.oni.navy.mil/ | 403 / 340 ms |
| GDELT DOC API | 8-second read timeout |

MSCIO and UKMTO remain browsable through some independent web retrieval routes, but **not reliably retrievable from this VM**. No 403 was bypassed. UKMTO's official terms describe Open Government Licence subject to conditions; MSCIO reuse remains conservatively restricted pending clearance. No original-document hash or source-receipt latency was fabricated.

## Candidate cases and next steps

- **CONTSHIP JET**, 28 Oct ~10:00 UTC, Black Sea, IMO 9348625, proposed MMSI 636019532: Bulgarian Defence https://www.mod.bg/news9664; VTMIS NAVWARN 768/26 later sinking; no verified independent-origin count.
- **MSCIO 164/26**, 1 Nov ~15:09 UTC, Hormuz, unidentified vessel: https://mscio.eu/alerts/200. UKMTO 191/26 is suspected republication of the same VHF Mayday, **not** an independent witness.
- **UKMTO 192/26**, 1 Nov reportedly 23:47 UTC, east of Ras Al Khafji: distinct candidate; original numbered PDF still not authenticated.
- **MSCIO 158/26**, 29 Oct ~16:00 UTC, Hormuz, unidentified tanker: https://mscio.eu/alerts/194. No IMO/MMSI or invented position.
- **ABLE** and **ALFA WATAN**, 6 Oct, and **CHELSEA 3 / HS DIGNITY**, 13 Oct, Black Sea: retrospective candidates. The latter pair appears in reliable reporting, but original official evidence and identifier crosswalks require review before staging ingest.

Next priority: authenticated primary-document capture and a durable, **isolated** PostgreSQL staging review adapter; prove independent originating observations before any PLAY-to-incident promotion. Keep AIS anomalies, rescue, wreck and investigation notices as contextual evidence only.

Safety: **no production deployment, no production DB writes, no historical record edits/deletions, no incident promotion, no cron/timer/loop/scheduler added to Oracle**.
