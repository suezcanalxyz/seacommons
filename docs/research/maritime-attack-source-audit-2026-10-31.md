# Maritime attack correlation: source audit (2026-10-31 UTC)

Staging research record only. No source was imported into production, no database
record was changed, and no publication decision is implied. An incident's
reported facts and a source's independent corroboration are different questions.

## Black Sea: CONTSHIP JET

- Vessel: CONTSHIP JET, IMO 9348625, MMSI 636019532 (MMSI is the regression
  identifier, not independently verified by the linked official documents).
- Bulgarian Ministry of Defence, dated 2026-10-28:
  https://www.mod.bg/news9664
  Reports strike at 12:00 Bulgarian local time (10:00 UTC), three observed
  impacts, Navy surveillance and a French patrol aircraft. The observations
  may be distinct sensors but the ministry press release is **one published
  provenance chain**; it does not prove two independent reporting origins.
  Exact publication/SeaCommons receipt timestamps: unknown.
- Bulgarian VTMIS, NAVWARN 768/26:
  https://www.vtmis.bg/wx/wx_eng.htm
  Sinking at 2026-10-28T20:30:00Z, 43-07.80N 028-45.36E
  (43.130000 N, 28.756000 E); more than 20 containers adrift.
  **Sinking is an outcome of the existing attack, not another attack.**
  The warning does not establish a publication or SeaCommons receipt time.
  No exact location for each drifting container is supplied.
- Bulgarian Ministry of Transport, dated 2026-10-28:
  https://www.mtc.government.bg/bg/category/1/18-chlenniyat-ekipazh-na-konteynerovoza-contship-jet-e-spasen
  Confirms all 18 crew rescued through coordinated agencies; do not count
  Defence and Transport press releases as independent merely because their
  ministry names differ.
- Do not infer a perpetrator from a drone type, geography or AIS gaps.

## Black Sea: KHORYV (negative causal control)

- Bulgarian VTMIS NAVWARN 766/26, same VTMIS page above.
- IMO 8138712, sighted capsized, semi-submerged, uncrewed and unlit at
  2026-10-28T18:00:00Z, 43-30.60N 028-43.69E
  (43.510000 N, 28.728167 E).
- The navigational warning establishes a hazard, **not the cause** of the
  capsize. Do not label as attack solely from this source.

## Strait of Hormuz: 187-26 / 159/26

- UKMTO original warning 187-26, incident 2026-10-29T22:12:00Z, 25 NM
  northeast of Khasab; initially **SUSPICIOUS ACTIVITY**, source **Third
  Party**, fire cause unknown:
  https://www.ukmto.org/-/media/ukmto/products/20261029-ukmto_warning-187-26.pdf
- UKMTO update 001, marked **ATTACK**, update time 2026-10-30T01:50:00Z;
  reports two hull-attached explosive devices, engine-room fire, crew safe,
  vessel underway, no environmental impact:
  https://www.ukmto.org/-/media/ukmto/products/20261029-ukmto_warning-187-26-update-001.pdf
- MSCIO 159/26, published 2026-10-30 07:44 (site timezone not explicitly
  confirmed in the page; do not automatically treat as UTC), incident
  2026-10-29T22:12:00Z, same 25 NM northeast of Khasab:
  https://mscio.eu/alerts/195
- Likely same episode. UKMTO and MSCIO may share the underlying third-party
  report, so **not automatically two independent confirmations**. Neither
  warning identifies a verified IMO/MMSI. LOUISE 1 remains an external
  identity hypothesis pending authoritative vessel matching.
- Event-to-UKMTO-update elapsed time: 3h38m. This is not collector latency.
  Publication and SeaCommons receipt timestamps are not available for UKMTO;
  SeaCommons receipt timestamp is not available for MSCIO.

## Reuse and ingestion policy

- UKMTO: Open Government Licence, with attribution/terms:
  https://www.ukmto.org/terms-and-conditions
- Bulgarian MoD page explicitly permits copying/distribution with source
  attribution (footer): https://www.mod.bg/news9664
- MSCIO: the current terms restrict third-party publication and redistribution
  of site contents. **Do not mirror or republish MSCIO alert text** without
  permission/appropriate legal review; store minimal factual references and
  source links, subject to policy review:
  https://mscio.eu/terms-of-service/
- VTMIS: public navigation warning is accessible; a specific bulk
  redistribution licence was not established. Link and store minimal facts.
- Availability was checked manually from public source pages on 2026-10-31.
  No automated fetch latency, rate limit or production ingestion was tested.

## Pending read-only database verification

A connected PostgreSQL session was not available in this run. Once access
is restored, inspect table schemas before any parameterized queries and
use a read-only transaction with a short statement timeout. Check
intel_events, vessel_tracks, alert_events, anomaly_events,
humanitarian_incidents, forensic_events, source_observations, lineage_edges
and maritime_episodes for 2026-10-28 through 2026-10-31 and all of October.
Compare LIVE/PLAY public projections and the incident review trail.
No production write or deploy is authorized.
