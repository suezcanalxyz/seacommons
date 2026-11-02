# Maritime attack correlation — staging append-only privilege gate

Audit UTC: 2026-11-02 15:30. Scope: attack-correlation staging branch only.
No production deploy, no Oracle PostgreSQL writes, no cron/timer/scheduler/daemon created.

## Delta from prior run
Prior staging head: `f2d51c168a7171bd9d9b5fc222af6ff9f801f44e`.
The prior `maritime_attack_staging_store.py` required a dedicated PostgreSQL
database ending in `_staging`, but did not verify that its current connection
role was incapable of mutating or deleting the evidence ledger. A table with
INSERT-only intended grants is not sufficient if the runtime role is its
owner, a superuser, or inherits UPDATE/DELETE/TRUNCATE/DDL privileges.

New fail-closed read-only SQL privilege preflight in
`apps/api/core/intel/maritime_attack_staging_store.py` rejects:
- superusers and roles able to CREATE on the staging database or schema;
- roles lacking schema USAGE or table SELECT/INSERT;
- roles with UPDATE, DELETE, TRUNCATE, or TRIGGER privileges on the
  `attack_review_staging.review_snapshots` table.

This check runs **before** any INSERT. No privilege changes, migrations,
schema creation, or commits are performed by the code. It does not prove
physical separation of the staging server and does not replace human
approval or independent evidence verification.

Tests added to `tests/test_maritime_attack_staging_store.py`: reject
privileged connection before INSERT, assert all sensitive privilege classes
appear in the SQL gate. A stale raw-GitHub branch response initially
caused two false test failures; rerun pinned to immutable commit
`ba94054b6b5831c40da5556aaba8902968f5e295` succeeded:
**11 isolated tests and 26 subtests passed**. Critical Ruff
`E4,E7,E9,F` passed; isolated full Ruff reports pre-existing
import-order and exception-type warnings. No full repository CI run
or live PostgreSQL integration test is claimed.

## Oracle read-only audit status
The authorized VM shell was used for process/repository checks and
read-only HTTP requests. PostgreSQL local role `ubuntu` does not exist;
`psql -U seacommons` via local peer authentication was rejected.
The available connection was not used to obtain database credentials.
**No fresh direct SQL count is available for intel_events, vessel_tracks,
alert_events, anomaly_events, humanitarian_incidents or forensic_events**.
Previous run's counts are not carried forward as fresh evidence.

The operational checkout on the VM is on
`fix/live-oracle-feed-recovery-20261013` at `790c460e` and has many
uncommitted changes from other work. It was not edited, checked out, reset,
or used as the staging workspace. VM disk: 45G total, 32G used, 14G free
(71%). The isolated tests used a temporary directory that self-deleted.

## Public LIVE/PLAY verification (2026-11-02 15:28–15:30 UTC)
GET `/api/v1/live/signals?days=3&mode=all&limit=500`: HTTP 200,
15 features, 14 maritime and 1 humanitarian. Visual categories:
12 `ais_gap`, 2 `navigation_casualty`, 1 `humanitarian_alarm_phone`.
Verification statuses: 13 single-source observed, 1 multi-source
corroborated (not an attack), 1 machine-extracted unverified.
No attack category is present in the returned LIVE features. GET `/api/v1/play/incidents?limit=500&offset=N`
for N=0,500,...,3500: eight HTTP 200 responses, 3,583 rows,
3,577 distinct incident IDs, six repeated IDs, no attack/piracy category
in returned records. Pagination is **not snapshot-consistent**; the
absence claim applies only to the returned rows.

GET `/api/v1/live/pipeline`: HTTP 200, runtime revision `790c460e30c2`,
AIS live, first-party/public feeds live, partner degraded, radio live.
Radio NAVTEX end-to-end remains unverified.

## Official-source availability from Oracle VM
Single bounded GETs, measured wall time, not publication-to-ingestion latency:
- Bulgarian Ministry of Defence CONTSHIP JET: 200 / 0.387 s.
- Bulgarian VTMIS NAVWARN: 200 / 0.109 s.
- MSCIO 164/26: timeout after 7.201 s.
- UKMTO homepage: 403 / 0.057 s.
- MARAD advisories: 403 / 0.019 s.
- IMO homepage: 200 / 0.143 s.
- NATO Shipping Centre: 403 / 0.036 s.
- ONI: 403 / 0.020 s.
- GDELT DOC API: URL/network error after 7.126 s.

No anti-bot restriction was bypassed. The MARAD advisory is readable
through an independent web retrieval path, not from the VM. UKMTO
publishes under Open Government Licence subject to terms; MSCIO content
is treated conservatively as redistribution restricted until cleared.

## Incident candidates / regression
- CONTSHIP JET, IMO 9348625, externally reported MMSI 636019532:
  Bulgarian MOD news9664 describes attack on 28 Oct at 12:00 local
  (=10:00 UTC); VTMIS NAVWARN 768/26 records sinking at 20:30 UTC.
  Prior read-only AIS samples showed speed decline 10.2 kn at 09:59:22
  to 0.6 kn at 10:34:46; **not freshly queried in this run**.
  Sinking and AIS slowdown are context, not second independent attack witnesses.
- MSCIO 164/26: Mayday relay, 1 Nov around 15:09 UTC, Hormuz,
  vessel unidentified; UKMTO 191/26 may share original reporting.
  Two publications are not automatically two independent origins.
- UKMTO 192/26: separately reported tanker impact on 1 Nov;
  official document still not independently downloaded from the VM.
- October Black Sea retrospective: ABLE, ALFA WATAN, CHELSEA-3,
  HS DIGNITY remain separate candidate dossiers pending source lineage
  and individual IMO/MMSI checks.
- MARAD 2026-013 (issued 23 Sep 2026) advises that AIS may be
  deliberately disabled for ship safety in parts of the Red Sea:
  gaps cannot establish attack causality.

## Sources
- https://www.mod.bg/news9664
- https://www.vtmis.bg/wx/wx_eng.htm
- https://mscio.eu/alerts/200
- https://www.ukmto.org/terms-and-conditions
- https://www.maritime.dot.gov/msci/2026-013-red-sea-bab-el-mandeb-strait-gulf-aden-arabian-sea-and-somali-basin-houthi-attacks

## Next gate
Provision/identify a separately authorized PostgreSQL staging database and
a dedicated non-owner, non-superuser role with only schema USAGE and table
SELECT/INSERT. Apply the reviewed schema only there, run a real transaction
test with rollback and replay, then add authenticated review UI. Do not
publish PLAY→incident or alter production without explicit approval.
