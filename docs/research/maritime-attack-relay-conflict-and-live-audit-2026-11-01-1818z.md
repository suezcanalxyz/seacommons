# SeaCommons — maritime attack relay conflicts and LIVE/PLAY audit
UTC audit: 2026-11-01 18:17–18:20. Branch: `feature/maritime-attack-correlation-20261030`. Previous head: `2ac41516`.

## Staging-only change
- `apps/api/core/intel/maritime_attack_relay_lineage.py`: reject an impossible reviewed snapshot captured more than five minutes before its source publication; flag competing alleged originals for the same relay; detect dependency cycles iteratively without recursion. Contradictory but structurally validated edges remain available for **conservative lineage collapse**, not as proof of source independence. `RelayLineageReview.publication_allowed` remains false; rejected reasons must be inspected before any operator decision.
- `tests/test_maritime_attack_relay_lineage.py`: synthetic negative controls for capture-before-publication, multiple competing originals, documentary cycles and a 1,100-document reprint chain. The tests never assert real-world independence.
- No database writes, cron, VM scheduling, historical rewrites, production deploy or incident promotion.

## Candidate incidents and provenance
- **CONTSHIP JET** IMO 9348625, MMSI 636019532: attack 2026-10-28 approximately 10:00 UTC, Black Sea, retrospective (outside rolling 72h). Bulgarian MoD https://www.mod.bg/news9664 documents the impacts but not IMO/MMSI. Contships https://contships-management.com/2026/10/29/contships-management-inc-company-update/ identifies IMO and relays a Master's account; the original attestation is not available in the reviewed materials. ZIM https://www.zim.com/za-hant/customer-updates/mv-contship-jet-cj5-v-74w reports owner-sourced information; its earlier posting cannot be attributed to the later Contships press release. Reuters 2026-10-29 https://www.reuters.com/world/europe/greek-container-ship-sinks-after-drone-attack-off-bulgaria-2026-10-29/ reports subsequent sinking: sinking is a distinct consequence/event and must not be mistaken for an additional independent attack witness. Existing AIS speeds 10.2 knots at 09:59:22 and 0.6 at 10:34:46 UTC are *context*, not attack evidence. Actual Oracle receipt clocks remain unaudited.
- **AL MAYEDA** IMO 9397298, reported MMSI 538003356: Nakilat https://nakilat.com/al-mayeda-vessel-incident-in-the-arabian-gulf/ says unidentified objects struck the vessel evening 2026-10-30; exact UTC and coordinates unknown. No perpetrator or weapon inference. Qatar MoFA condemnation is not automatically independent of the operator's report. Do not merge with MSCIO 162/26 without vessel/time/position proof.
- **MSCIO 159/26**, 2026-10-29 22:12 UTC, Hormuz; https://mscio.eu/alerts/195 ; ship identifiers require independent source review.
- **MSCIO 162/26**, 2026-10-30 18:00 UTC, Arabian Gulf; https://mscio.eu/alerts/198 ; ship identifiers not verified.
- **MSCIO 158/26**, 2026-10-29 16:00 UTC, Hormuz; https://mscio.eu/alerts/194 ; outside the current rolling 72h but retained in October retrospective.
- **AZINI**, MSCIO 161/26, 2026-10-29, Somalia; later reported location is not the hijack site.
- IMO October retrospective https://www.imo.org/en/mediacentre/hottopics/pages/middle-east-highlighted-incidents.aspx lists 122 confirmed incidents as of 2026-10-30; it is a compilation, not an independent original witness. Multiple episodes of the same vessel must retain distinct event timestamps. An eight-digit malformed IMO for CAMEROON PROSPERITY must be quarantined, not auto-corrected.

## LIVE/PLAY HTTP read-only checks
Requests executed on authorized remote device 2026-11-01 ~18:17 UTC:
- `GET https://play.seacommons.org/api/v1/play/counts` HTTP 200: total 3575; maritime 3446; humanitarian 129; investigation 3435; `generated_at=2026-11-01T17:44:40.127266+00:00`.
- `GET https://play.seacommons.org/api/v1/play/incidents?limit=1` HTTP 200: total 3575; `generated_at=2026-11-01T18:17:52.803289+00:00`. Totals agree but counts cache ~33 minutes older; not a synchronized snapshot.
- `GET https://live.seacommons.org/api/v1/live/pipeline` HTTP 200: `generated_at=2026-11-01T18:17:53.656664+00:00`; AIS, first-party, public feeds live; **partner and radio degraded**. Radio decoder worker alive, DSC accepted 47, `navtex_accepted=0`. Do not equate decoder availability with NAVTEX evidence.
- `GET https://seacommons.org/api/v1/live/signals?mode=maritime` HTTP 200: nine visible maritime features, `generated_at=2026-11-01T18:17:56.930418+00:00`. These checks do not certify the attack category end-to-end.
- Endpoint generated_at is a cache/projection clock, **not** source-event→collector latency. Publication and ingestion latency not established.

## Oracle PostgreSQL read-only access
Attempted a noninteractive, read-only `psql -w -X` transaction. Result: `FATAL: role "ubuntu" does not exist`. **Fresh SQL queries completed: zero**. No credential discovery, privilege change or bypass. The following is a prepared query, NOT an executed result:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '6000ms';
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
AND table_name IN ('intel_events','vessel_tracks','alert_events',
                   'anomaly_events','humanitarian_incidents','forensic_events')
ORDER BY table_name, ordinal_position;
SELECT id, mmsi, ts, received_at, sog, lat, lon
FROM vessel_tracks
WHERE mmsi = '636019532'
AND ts >= TIMESTAMP '2026-10-28 09:30:00'
AND ts < TIMESTAMP '2026-10-28 11:30:00'
ORDER BY ts, id LIMIT 257;
ROLLBACK;
```
A bounded result hitting 257 rows is **incomplete** and must not be used for forensic trajectory inference. A separate read-only query is needed for AL MAYEDA's MMSI and the October/rolling 72-hour audit, after inspecting actual table columns.

## Official availability, licensing and operational caveats
- MARAD 2026-012 https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations is active (expires 2027-03-22). MARAD 2026-011 covers Persian Gulf/Hormuz. Both are risk context, not incident-specific corroboration. MARAD links to NATO Shipping Centre and NAVAREA III warnings.
- IMO https://www.imo.org/en/mediacentre/hottopics/pages/middle-east-strait-of-hormuz.aspx reports confirmed regional incident compilation updated 2026-10-30. Source/collection reuse conditions must be checked before bulk ingestion; official public access does not imply unlimited redistribution.
- No verified bulk-reuse authorization for MSCIO, Contships, Nakilat, commercial registries or Reuters. Only minimal factual metadata and source links are used in this audit.
- UKMTO/MSCIO may share originating reports; different publisher names alone are not proof of independence. No attribution of an aggressor.

## Outstanding release gates
1. Verify GitHub Actions on final functional commit and preserve logs.
2. Obtain a genuinely authorized read-only Oracle database role; query six tables and vessel receipt timestamps.
3. Authenticate original witness artifacts and source-lineage review; retain all publication/event/receipt timestamps and hash provenance.
4. Test PLAY→incident review gate and dedicated attack visual taxonomy against staged API/UI; do not alter humanitarian drift.
5. Production deploy only after explicit approval.
