# SeaCommons — maritime attack identity provenance and source-alias audit
Date: 2026-11-01 14:27 UTC. Branch: `feature/maritime-attack-correlation-20261030`.
Baseline: `665b923e`. Staging only; no Oracle writes, no production deployment, no VM cron/timer/loop.

## Code changes and regression
The identity-link adapter previously rejected repeated `source_record_id` values, but accepted two distinct record IDs referencing the *same normalized registry URL*. This could make one source appear as multiple separate identity-evidence records. It did not grant attack corroboration or publication, but weakened provenance fidelity.

`maritime_attack_identity_evidence.py` now tracks canonical HTTPS source URLs and blocks duplicates, including tracking-parameter aliases and fragment variations, returning `invalid_or_duplicate_identity_provenance`. This is fail-closed, with no DB writes or publication effects. Two regressions assert (a) the duplicate-URL veto and (b) two distinct URLs remain linkable *for review only*; neither is attack proof.

Commits:
- `7996d80f`: canonical registry URL deduplication.
- `f82ec499`: two regressions.

CI run https://github.com/suezcanalxyz/seacommons/actions/runs/41316205002 : completed **success** on `f82ec499` (2026-11-01 14:27 UTC). Logs: 305 maritime tests + 19 official bulletin tests + 3 SQLite + 6 isolated PostgreSQL = **333 Python tests PASS**. Frontend attack taxonomy job and build succeeded. This certifies the staging branch, not production Oracle or the end-to-end PLAY promotion.

## Real CONTSHIP JET identity evidence: source-specific fields
- Bulgarian Ministry of Defence attack bulletin, dated 28 October 2026: https://www.mod.bg/news9664 . Names CONTSHIP JET and the 12:00 local / 10:00 UTC event. It does **not** print IMO/MMSI. This is the incident source, not a vessel-registry source.
- Vessel operator/manager fleet page: https://contships-management.com/vessel/contship-jet/ . Names CONTSHIP JET and explicitly prints IMO **9348625**. It does **not** print MMSI on the retrieved page. This is primary operator evidence for the IMO/name link, **not** independent attack corroboration.
- Flexport Atlas vessel page: https://atlas.flexport.com/vessel/imo:9348625/mmsi:636019532/name:contship-jet . Prints both IMO **9348625** and MMSI **636019532**; the page says use is subject to Flexport terms. This is a candidate external identity record only, not a free-redistribution license and not independent attack corroboration.
- Econdb public vessel page: https://www.econdb.com/maritime/vessels/636019532/ . Prints the same IMO/MMSI but its fetched voyage data shows a last AIS signal of 24 October, unlike later 28 October observations elsewhere. Do not use its voyage position as a current or attack-time fix.

The external sources were checked on 1 November 2026; exact publisher publication clocks and original collector receipt timestamps are **not available** for these pages. Do not manufacture those clocks, set `reviewed_by` to an automated process, or ingest these as fully reviewed records. Operator page and Flexport may draw on related upstream registries; do not assume independent origin. All reuse rights for copying/automating external registry data remain unverified. A single URL link plus field-level citation may be retained for operator investigation without redistributing source content.

## Operational read-only checks
At ~14:27 UTC the public endpoints were reached without authentication:
- https://play.seacommons.org/api/v1/play/counts : `total_count=3572`, maritime `3444`, humanitarian `128`, generated 13:25:05 UTC.
- https://play.seacommons.org/api/v1/play/incidents?limit=1 : `total_count=3572`, generated 14:26:59 UTC. Counts agree, but timestamps differ by ~62 minutes.
- https://live.seacommons.org/api/v1/live/pipeline : generated 14:26:59 UTC. AIS, first-party and public feeds live; partner degraded; radio reported live with decoder stats. HTTP availability does not certify incident classification.

A local `psql` read-only attempt on the authorized Oracle device returned `FATAL: role "ubuntu" does not exist`. No role escalation or credential access. **No new SQL rows certified** for `intel_events`, `vessel_tracks`, `alert_events`, `anomaly_events`, `humanitarian_incidents`, `forensic_events` or official-source ingestion.

## Candidate separation and source lineage
- CONTSHIP JET: 28 October, Black Sea, Bulgarian ministry incident source plus AIS deceleration context; IMO from operator and MMSI from external registry source. No independent second incident witness certified, no attacker attribution.
- MSCIO 158/26 and 159/26: 29 October, Strait of Hormuz, vessel identifiers unresolved. Reuters reported LOUISE 1 for the latter; keep separate until a source-specific vessel identity link and origin lineage are verified.
- MSCIO 161/26: AZINI hijacking, 29 October, Somalia. The 30–31 October last-reported positions are not proven hijacking coordinates.
- UKMTO 190/26: 30 October suspicious boarding of an unnamed fishing vessel; **do not** automatically equate it to AZINI or classify it as an independently verified attack.
- MSCIO 163/26: reported 30 October about an incident dated 28 October; preserve event versus publication clocks.
- MARAD 2026-012: regional Black Sea advisory, not a ship-specific attack witness.

## Remaining gates
1. Authorized PostgreSQL read-only role: check `received_at` of CONTSHIP JET AIS rows and official bulletin coverage over October and the past 72h.
2. Capture permitted field-level operator identity evidence with documented receipt clock, reviewer and reuse terms. Do not rewrite Bulgarian ministry bulletin.
3. Isolated staging test from original document -> external identity link -> AIS context -> reviewed candidate; prove independent incident source lineage before any corroboration.
4. Verify attack-specific PLAY category/color and reviewed promotion with synchronized snapshots. Never auto-promote AIS anomaly or procedural investigation.
5. No production deployment without explicit approval.
