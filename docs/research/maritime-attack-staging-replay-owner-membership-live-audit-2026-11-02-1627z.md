# SeaCommons maritime attack correlation — staging replay and ownership gate

Audit: 2026-11-02 ~16:27 UTC. Scope: attack-correlation branch only. No deployment, no production DB writes, no migrations, no scheduled jobs or daemons.

## Delta from prior run

Previous head: `4ad36fd74eef9a55915bed3dc34d6c499df958ea`.
New code: `apps/api/core/intel/maritime_attack_staging_store.py`.
New regressions: `tests/test_maritime_attack_staging_store.py`.

Two fail-closed corrections:

1. **Owner-role escalation**: the staging role check now rejects membership in the PostgreSQL database, staging schema, or review table owner's role, even if privileges are not inherited. In PostgreSQL a NOINHERIT member may be able to `SET ROLE` to an owner; checking only `has_table_privilege(current_user, ..., 'UPDATE')` does not capture this. SQL checks `pg_has_role(..., 'MEMBER')` against `pg_database.datdba`, `pg_namespace.nspowner`, and `pg_class.relowner`. Existing CREATE, UPDATE, DELETE, TRUNCATE, TRIGGER and superuser checks remain.
2. **Corrupted idempotent replay**: on `ON CONFLICT DO NOTHING`, the previous code checked only the stored `snapshot_sha256` column. A corrupted or tampered stored JSON or case identity could therefore be incorrectly accepted as an identical replay if the digest column remained unchanged. The new readback compares all six immutable columns: snapshot ID, case ID, observation ID, evidence ledger digest, snapshot digest and exact payload JSON. Missing or mismatched rows fail closed.

These checks are staging guards, not a proof of physical database isolation, document authenticity, or protection from a privileged DBA.

## Tests

Fetched the exact staging branch revision to an isolated, self-cleaning temporary directory on the authorized Oracle VM; the operational checkout was not edited or switched. Ran `unittest discover` for `test_maritime_attack_staging_store.py`: **11 tests passed**, including replay tampering across five columns, missing-row rejection and owner-membership SQL assertions. Critical Ruff rules `E4,E7,E9,F` passed. This is **not** a full suite or a PostgreSQL integration test. No new GitHub Actions status checks were reported at the time of inspection.

## PostgreSQL read-only audit

Attempted to initiate a read-only PostgreSQL catalog audit using the authorized remote interface, but the interface explicitly rejected the requested command as **not allowed**. Did not retry via privilege escalation or retrieve database credentials. Consequently, **no fresh counts** are claimed for `intel_events`, `vessel_tracks`, `alert_events`, `anomaly_events`, `humanitarian_incidents`, or `forensic_events`. Prior counts are historical only. Dedicated PostgreSQL staging remains unprovisioned/unverified.

## Public LIVE/PLAY (2026-11-02 ~16:26 UTC)

Read-only HTTP 200 at `https://api.seacommons.org`:
- `GET /api/v1/live/pipeline`: revision `790c460e30c2`; AIS, first-party, public feeds and radio live; partner degraded. Radio decoder: 64 DSC accepted, **0 NAVTEX accepted**.
- `GET /api/v1/live/signals?days=3&mode=all&limit=500`: **13** features (prior 15), 11 `ais_gap`, 2 `navigation_casualty`. Verification: 12 `single_source_observed`, 1 `multi_source_corroborated` (not attack). No attack category in returned LIVE features.
- `GET /api/v1/play/incidents?limit=500&offset=N` for N=0,500,...,3500: eight HTTP 200 responses, **3,583** returned rows, **3,577** distinct IDs, six repeated IDs, and **0** attack/piracy/explosion/sinking categories in returned rows. Reported `total_count` 3,583 on all eight pages; category totals 3,447 maritime and 136 humanitarian. Offset pagination remains non-snapshot-consistent; do not claim exhaustive unique-incident coverage.

## Official-source HTTP availability from authorized VM

Bounded single GETs; timings are HTTP wall time, **not** publication-to-ingestion latency:
- Bulgarian MOD `news9664`: 200, 0.514 s.
- Bulgarian Transport homepage: 200, 0.399 s.
- VTMIS NAVWARN: 200, 0.108 s.
- MSCIO 164/26: 200, 0.265 s (**recovered from previous timeout**).
- IMO homepage: 200, 0.121 s.
- UKMTO homepage: 403, 0.035 s.
- MARAD: 403, 0.029 s.
- NATO Shipping Centre: 403, 0.104 s.
- ONI: 403, 0.510 s.
- GDELT DOC API: URL error at 7.133 s.

Do not bypass restrictions. UKMTO terms indicate Open Government Licence with conditions; MSCIO is treated as restricted for redistribution pending verification.

## Candidate incidents / regression

- **CONTSHIP JET**, IMO 9348625, MMSI 636019532: 28 Oct ~10:00 UTC, Black Sea. Bulgarian MOD reports attack; VTMIS NAVWARN 768/26 records later sinking. Prior AIS observations showed 10.2 kn at 09:59:22 to 0.6 kn at 10:34:46. **No fresh AIS SQL query in this run**; slowdown is context, not attack proof. No perpetrator attribution, no independent-witness certification, no publication.
- **MSCIO 164/26**: 1 Nov ~15:09 UTC, Strait of Hormuz, unidentified vessel, VHF 16 Mayday relay. **UKMTO 191/26** may derive from same original testimony; two publishers are not automatically independent.
- **UKMTO 192/26**: separate reported tanker incident on 1 Nov; official PDF not directly acquired and identity not established.
- October Black Sea retrospective: **ABLE**, **ALFA WATAN**, **CHELSEA-3**, **HS DIGNITY** remain distinct. Bulgarian Transport's 13 Oct bulletin describes CHELSEA-3 and HS DIGNITY separately; 14/17 Oct follow-ups are context, not automatically independent attack witnesses.

Sources:
- https://www.mod.bg/news9664
- https://www.vtmis.bg/wx/wx_eng.htm
- https://mscio.eu/alerts/200
- https://www.mtc.government.bg/en/category/1/technical-information-vessels-affected-and-those-provided-assistance-maritime-areas-republic-bulgaria-over-past-24-hours
- https://www.ukmto.org/terms-and-conditions

## Next safe gate

Obtain an explicitly authorized **separate** PostgreSQL staging database and a non-owner, non-superuser role with INSERT/SELECT only. Apply schema only there after approval, test actual rollback and idempotent replay, then implement authenticated manual case review. Keep `publication_allowed=false` and no production deployment without explicit authorization.
