# SeaCommons — Maritime incident relay-lineage audit
UTC date: 2026-11-01, approximately 17:20 UTC. Staging branch: `feature/maritime-attack-correlation-20261030`.
Previous audited head: `b0a60daa`. No production deploy, Oracle writes, VM cron/timer/loop, or historical rewrite.

## Implemented on staging
- `apps/api/core/intel/maritime_attack_relay_lineage.py`: pure reviewed source-dependency edges. Requires claim IDs, matching canonical URLs, exact reviewed-document SHA-256 metadata, named reviewer, UTC capture/review clocks, supported relation, and publication chronology. A later or unclocked original document cannot be claimed as the source of an earlier relay. Returns rejected reasons; never authorizes publication. It does **not** fetch or independently verify the claimed hash or reviewer: an authenticated review process must do so before supplying these records.
- `tests/test_maritime_attack_relay_lineage.py`: synthetic two-source-to-one-lineage test, missing review/hash, forged URL, missing claim, clock errors, duplicate edge, independent third origin, unknown relation, and late/unclocked original-document controls.
- `tests/test_maritime_attack_correlation.py`: October IMO public-register malformed identifier regression (CAMEROON PROSPERITY listed as `93151598`, eight digits) and day-only AL MAYEDA unknown-object-impact negative control. The raw IMO typo must be preserved for review, not silently truncated into an entity link.
- Existing staging GitHub Actions workflow path filters include the new module/tests. No new workflow schedule.
- This only prepares reviewed `lineage_edges` for the existing correlator; it does not wire an ingestion collector or promote PLAY records.

## Documentary source lineage
- CONTSHIP JET, 2026-10-28 ~10:00 UTC: Bulgarian Ministry of Defence https://www.mod.bg/news9664 identifies the vessel by name and documents surveillance of three impacts, **not** IMO/MMSI. Contships Management https://contships-management.com/2026/10/29/contships-management-inc-company-update/ (page publication 29 Oct, dateline 28 Oct) supplies IMO 9348625 and relays the Master's account, but not an authenticated original Master transcript or MMSI. ZIM https://www.zim.com/za-hant/customer-updates/mv-contship-jet-cj5-v-74w says the **owners informed** the charterer. Its locale page displays 28 Oct 06:15 without a verified timezone, and it precedes the 29 Oct Contships press-release page: therefore ZIM **cannot** be asserted to derive from that later document. It may share the owner's originating information, but the underlying original owner notification has not been captured or reviewed. No verified lineage edge for this real pair yet; no new corroboration.
- AL MAYEDA, event **evening 2026-10-30** (exact UTC unknown), Arabian Gulf: operator Nakilat https://www.nakilat.com/al-mayeda-vessel-incident-in-the-arabian-gulf/ says struck by **unidentified objects**, crew safe and vessel operational. Qatar MoFA https://mofa.gov.qa/en/latest-articles/statements/qatar-condemns-attack-on-lng-carrier-in-arabian-gulf condemned the incident on **2026-11-01**; ministry is not automatically an independent eyewitness. Gard insurer vessel entry https://gard.no/vessels/48451/ associates name with IMO **9397298**; third-party maritime sources associate MMSI **538003356**, but no source document reviewed here prints both under an approved reuse contract. This is a **candidate impact**, not a proven deliberate drone/missile strike. It must not automatically merge with MSCIO 162/26 without event time/location matching.
- MSCIO 159/26 https://mscio.eu/alerts/195: 2026-10-29 22:12 UTC, 25 NM NE Khasab, tanker approached and explosive devices reported; Reuters reports LOUISE 1 by security sources but IMO/MMSI not verified in the original bulletin. MSCIO 162/26 https://mscio.eu/alerts/198: 2026-10-30 18:00 UTC, 40 NM south of Lavan, unknown vessel struck on port side; no identity crosswalk. Both fall in the 72-hour window beginning ~2026-10-29 17:20 UTC.
- MSCIO 161/26 https://mscio.eu/alerts/197: AZINI reported hijacked on 29 Oct ~09:00 UTC, **outside** the rolling 72-hour window at audit time but in October retrospective. The 30 Oct 04:00 UTC position is a **later reported position**, not the hijack location.
- IMO October retrospective https://www.imo.org/en/mediacentre/hottopics/pages/middle-east-highlighted-incidents.aspx: 122 confirmed incidents as of 30 Oct; GHANA PROSPERITY IMO 9732541 appears on 3 and 23 Oct as separate events. The same page prints CAMEROON PROSPERITY with malformed eight-digit IMO 93151598; quarantine rather than normalize. IMO compilation is not automatically independent of MSCIO/UKMTO.

## LIVE / PLAY read-only HTTP verification (17:18–17:20 UTC)
- PLAY counts `GET https://play.seacommons.org/api/v1/play/counts`: HTTP 200; total 3575 (maritime 3446, humanitarian 129, investigation 3435), generated_at `2026-11-01T16:30:19.038790+00:00`.
- PLAY catalog `GET https://play.seacommons.org/api/v1/play/incidents?limit=1`: HTTP 200, total 3575, generated_at `2026-11-01T17:18:49.352611+00:00`. Totals agree but timestamps differ ~48 minutes; not a synchronized snapshot.
- LIVE pipeline `GET https://live.seacommons.org/api/v1/live/pipeline`: HTTP 200, generated_at `2026-11-01T17:18:49.679224+00:00`; AIS, first-party, public feeds, radio live; partner degraded. Radio `navtex_accepted=0` despite DSC accepted 46; radio service availability does not prove NAVTEX ingestion.
- LIVE maritime `GET https://seacommons.org/api/v1/live/signals?mode=maritime`: HTTP 200, nine features; one existing `episode:subj:imo:9158159:gap_episode:1` has `verification_status=multi_source_corroborated` but `corroborated=false`. Needs projection-semantic audit, not proof of an attack bug.

## Oracle PostgreSQL: access denied, not audited
The authorized remote device is online, but the noninteractive read-only `psql -w -X` attempt returned `FATAL: role "ubuntu" does not exist`. No credential discovery, role modification or escalation. **Fresh SQL results: zero.**
Prepared only, not executed:
```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '6000ms';
SELECT id, mmsi, ts, received_at, sog, lat, lon
FROM vessel_tracks
WHERE mmsi IN ('636019532','538003356')
  AND ts >= TIMESTAMP '2026-10-28 00:00:00'
  AND ts < TIMESTAMP '2026-11-01 00:00:00'
ORDER BY mmsi, ts, id LIMIT 257;
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('intel_events','vessel_tracks','alert_events',
    'anomaly_events','humanitarian_incidents','forensic_events')
ORDER BY table_name, ordinal_position;
ROLLBACK;
```
Note: the combined 257-row LIMIT is only an exploratory cap and must **not** be treated as a complete per-vessel trajectory; use separately bounded, complete per-MMSI windows for forensic correlation.

## Licensing and latency
Bulgarian MoD permits attributed copying of public information on its site. Nakilat, Contships, ZIM, insurer/registry sources and MSCIO have not been cleared for bulk redistribution. IMO terms restrict some reuse; only links and minimal factual metadata recorded. MARAD 2026-012 https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations remains active as contextual risk guidance, not a specific attack witness. GDELT's published refresh frequency does not establish SeaCommons ingestion latency. No actual collector-to-publication latency measured. No attacker attribution.

## CI verified
GitHub Actions https://github.com/suezcanalxyz/seacommons/actions/runs/41331010738 completed **SUCCESS** at 2026-11-01 17:21 UTC on functional commit `b31eee86`. Unit correlation **326 PASS**, official bulletin **19 PASS**, isolated SQLite **3 PASS**, isolated PostgreSQL **6 PASS**: **354 Python PASS**; JavaScript taxonomy **5 PASS** and frontend build **SUCCESS**. Isolated PostgreSQL CI does not validate Oracle production connectivity.

## Next gates
1. Obtain a genuinely authorized read-only Oracle role and audit the six tables, October 2026 retrospective, rolling 72-hour windows, and real `received_at` for CONTSHIP JET and AL MAYEDA.
2. Authenticate original owner/crew or independent observation evidence, source hashes and origin dependency before any two-source corroboration.
3. Verify staged PLAY projection with incident taxonomy/color, humanitarian drift isolation, timestamp provenance and explicit reviewer approval. No production deploy without approval.
