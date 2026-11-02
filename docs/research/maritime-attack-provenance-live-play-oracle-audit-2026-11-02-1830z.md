# SeaCommons maritime attack correlation — staging-only audit (2026-11-02, ~18:23–18:35 UTC)

## Scope and safety

No production deployment, no DDL, no data deletion, no canonical writes, no scheduled work on Oracle. Oracle PostgreSQL accessed through the existing application connection with `default_transaction_read_only=on` and SQL statement timeouts. Queries were independent read-only sessions, not one transactionally consistent snapshot. No independent witness origins certified and no PLAY → incident promotion.

## Changes from previous run

Previous functional branch head: `fd1a9ad5`. This run adds fail-closed lineage provenance validation, regressions, and metadata-only MSCIO 148/26 manifest. Source code rejects boolean `False` masquerading as zero independent witnesses, noncanonical day-only event dates, malformed/credential-bearing/fragmented HTTPS evidence URLs, invalid optional publication/receipt timestamps, publication after receipt, source dates after receipt, and malformed SHA-256 fields. These are validation gates, not document authentication.

The isolated lineage test suite completed **27 tests passed** on the Oracle VM using a temporary copy; one existing Python 3.12-only test expression (`base | changed`) was adapted to Python 3.8 syntax in the temporary test copy only. No production checkout modified. The earlier `cad17ef0` commit's GitHub Actions run `41500725820` completed successfully (all four jobs). New manifest/test CI must be checked separately.

## Oracle PostgreSQL read-only audit

Window start fixed at `2026-10-30T18:23:22Z` (72 hours before this run). For varchar ISO-8601 UTC columns, comparisons used the common prefix `YYYY-MM-DDTHH:MM:SS` as a string, rather than an unsafe unindexed full-table cast; `vessel_tracks.ts` used a native timestamp comparison. Results:

| Relation | Window field | Count |
|---|---|---:|
| `intel_events` | `timestamp_utc` | 10,579 |
| `vessel_tracks` | `ts` | 815,369 |
| `alert_events` | `timestamp_utc` | 0 |
| `anomaly_events` | `timestamp_utc` | 0 |
| `humanitarian_incidents` | `last_update_at` | 9 |
| `forensic_events` | `timestamp_utc` | 7 |

These are rolling-window counts, not insert deltas. Text ordering presumes ISO-8601 timestamps normalized to UTC; this should be confirmed by a typed/indexed migration before relying on it as a permanent audit query.

Additional checks: `source_observations.observation_type = 'official_maritime_bulletin'` across the full database returned **0**; October `maritime_episodes` with `episode_family IN ('maritime_attack','piracy','explosion','sinking')` returned **0**.

Regression vessel: **CONTSHIP JET**, IMO 9348625 / MMSI 636019532. The five AIS fixes for 2026-10-28 09:45–11:10 UTC show 10.8 kn at 09:57:55, 10.2 kn at 09:59:22, 0.6 kn at 10:34:46, 0.7 kn at 10:46:24, and 0.8 kn at 10:58:15. This slowdown is contextual, **not independent attack proof**. The Bulgarian Ministry of Defence reports the attack at 12:00 Bulgarian local time (10:00 UTC) on 28 October, with subsequent rescue. Source: https://www.mod.bg/news9664. A later NAVWARN on sinking must remain a distinct outcome, not a second attack.

## Public LIVE / PLAY read-only audit

`https://api.seacommons.org/api/v1/play/counts`: HTTP 200; `total_count=3583`, `humanitarian_count=129`, `maritime_count=3454`, `investigation_count=3446`.

Eight requests to `/api/v1/play/incidents?limit=500&offset=...` all HTTP 200: **3,583 rows, 3,577 unique incident IDs, 6 pagination duplicates**, no returned incident type containing attack/piracy/explosion/sinking. Offset pagination is not snapshot-consistent and this is not proof of exhaustive unique coverage.

`/api/v1/live/signals?days=3&limit=300&mode=all`: HTTP 200, **12 features**: 10 AIS gaps, 2 navigation casualties, 0 attack-classified. Public absence is not evidence that no attacks occurred.

## Source discovery and availability (Oracle VM HTTP response time)

| Source | HTTP / error | Approx. HTTP elapsed |
|---|---|---:|
| Bulgarian Defence Ministry | 200 | 383 ms |
| Bulgarian Transport Ministry homepage | 200 | 406 ms |
| VTMIS / NAVWARN page | 200 | 138 ms |
| MSCIO 164/26 | 200 | 348 ms |
| UKMTO homepage | 403 | 43 ms |
| IMO homepage | 200 | 124 ms |
| MARAD advisories | 403 | 27 ms |
| NATO Shipping Centre | 403 | 26 ms |
| ONI homepage | 403 | 510 ms |
| GDELT DOC API | URLError | 7,129 ms |

These are HTTP availability measurements, not event→publication or publication→ingest latency. No access controls bypassed. UKMTO publishes under the Open Government Licence subject to conditions: https://www.ukmto.org/terms-and-conditions. MSCIO prohibits broad republication under its terms: https://www.mscio.eu/terms-of-service/. Bulgarian Defence Ministry permits reuse with source attribution. Access to IMO GISIS modules may require free registration and is not an anonymous API guarantee.

## New October candidate: MSCIO 148/26

Official notice https://mscio.eu/alerts/184, published 2026-10-17. It reports a tanker attacked with an RPG from a small boat on 2026-10-16 approximately 19:22 UTC, about 78 NM northeast of Al Jubayl in the Arabian Gulf, with damage and crew reported safe. The notice supplies no vessel name, IMO, MMSI or precise coordinates. Metadata-only staging manifest: `maritime-attack-mscio-148-2026-11-02.json`. No source-document hash, no independent witness certified, `publication_allowed=false` at the prepared-envelope level. Source rights classified `restricted_republication`. Do not infer a point from the distance/bearing description.

Other prioritized candidates: MSCIO 164/26 (2026-11-01 15:09 UTC, relayed VHF Mayday, unidentified ship) and UKMTO 192/26 (different reported tanker incident; direct original PDF still unverified). UKMTO 191/26 and MSCIO 164/26 may share the same originating Mayday and must not count as two independent witnesses.

## Remaining blockers and next step

No dedicated authorized PostgreSQL staging database with verified least-privilege INSERT/SELECT role has been demonstrated. The staging review schema and append-only adapter remain unactivated. Original witness origin independence is unverified. The canonical observation writer has zero official maritime bulletins. Next: validate manifest in CI, provision/authorize truly separate staging database, test insert→rollback→re-read and idempotence, then implement authenticated review; do not promote or deploy without explicit approval.
