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

## Arabian Gulf: UKMTO 188-26 (new external candidate, 30 October)

- UKMTO warning reference **188-26**, reported event 2026-10-30T18:00:00Z,
  approximately 40 NM south of Lavan Island, Iran. Report describes an
  unidentified vessel struck on the port side by an **unknown projectile**,
  followed by a fire; crew reported safe. Vessel name, IMO, MMSI, exact
  coordinates and perpetrator are **not established**.
- Reuters reporting dated 2026-10-30 describes the Lavan Island report
  separately from the 29 October Khasab event:
  https://www.reuters.com/world/middle-east/irans-irgc-navy-says-two-tankers-stopped-south-hormuz-after-incidents-2026-10-30/
- Official UKMTO portal: https://www.ukmto.org/ . The numbered original PDF
  was **not independently retrieved in this research pass**. Do not elevate
  second-hand transcriptions to primary-source verification.
- Keep 188-26 separate from **187-26** (29 October 22:12 UTC, northeast of
  Khasab) and from **186-26** (29 October 16:00 UTC). Similar words
  (`port side`, `fire`) do not prove a common hull.
- Reuters repeating UKMTO does not establish a second independent origin.
  A third-party aggregator categorizing the aggressor as `Military` is not
  an attribution supported by the UKMTO warning. Status: **candidate**;
  no PLAY→incident promotion.
- Publication and SeaCommons receipt timestamps: **not verified**. No
  collector-latency estimate is possible from these sources.

## October Black Sea retro: identity and casualty controls

- **CHELSEA 3**, 13 October 2026, Malta flag: Bulgarian regional authority
  reports a drone strike about 15 NM off Byala, all 15 crew evacuated.
  Source: Bulgarian News Agency quoting Varna regional administration:
  https://www.bta.bg/en/news/bulgaria/1223275-cargo-ship-struck-by-aerial-drone-off-bulgarian-coast
  The official statement and newswire transcription may be one provenance
  chain, not independent corroboration. Vessel IMO/MMSI not verified here.
- **HS DIGNITY**, 13 October 2026: Reuters reports a sinking off Bulgaria
  after a drone strike and five crew rescued, with eleven missing at the
  reporting time. Identity and final casualty figures need fresh primary
  confirmation; do not treat a newswire report as a completed SAR outcome.
  https://www.reuters.com/world/europe/drone-sinks-ship-off-bulgaria-coast-prime-minister-says-2026-10-13/
- Neither retro case has been checked against SeaCommons PostgreSQL.
  Keep both distinct from CONTSHIP JET and KHORYV by vessel identity and
  event date, and do not assign a perpetrator without verified evidence.

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

## Additional official alerts checked 31 October (72-hour window)

- **MSCIO 160/26, Gulf of Aden**, event **2026-10-30T02:25:00Z**,
  position 11°57.4'N 045°04.5'E (approximately 11.956667 N, 45.075 E):
  https://mscio.eu/alerts/196
  Two suspicious craft approached a merchant vessel; one skiff reportedly
  carried a mounted weapon. **No shots fired, no boarding attempted**, vessel
  continued its voyage. Operation ATALANTA is investigating. Classify
  `suspicious_activity`, **not an attack**. No verified IMO/MMSI.
  Site displays 30 October 09:10; publication timezone not established.
  SeaCommons receipt timestamp unknown.
- **MSCIO 162/26, Arabian Gulf**, event **2026-10-30T18:00:00Z**,
  40 NM south of Lavan Island, Iran:
  https://mscio.eu/alerts/198
  Vessel reportedly struck on port side by unknown projectile, causing fire;
  crew safe, environmental impact not reported. Site displays 30 October 22:17
  (timezone not established). This likely refers to the same original report
  as UKMTO **188-26**. Treat as a *single provisional episode*, not two
  independently corroborated reports. Vessel name, IMO/MMSI and SeaCommons
  receipt timestamp unknown. No perpetrator attribution.
- **MSCIO 163/26, Strait of Hormuz**, **time-late** report of an event on
  **28 October 2026**, without exact event hour:
  https://mscio.eu/alerts/199
  Crude oil tanker reportedly struck by unknown projectile on outbound
  transit. Site displays 30 October 22:22 (timezone not established).
  No IMO/MMSI or exact event time. Do not automatically merge with MSCIO
  158/26 (29 October 16:00 UTC), MSCIO 159/26 (29 October 22:12 UTC), or
  MSCIO 162/26 (30 October 18:00 UTC). Missing identity and time must remain
  explicit uncertainty; do not fabricate an exact point or latency.

These three are **external candidates**, not database matches. The MSCIO
site is publicly readable, but its terms restrict redistribution; use only
minimal factual indexing and source links pending legal review. No automated
collector ingestion or PostgreSQL verification was performed.

## 31 October follow-up: canonical outcome-link guard and source chronology

- Staging code review found a discrepancy: PLAY required a verified
  SourceObservation/lineage audit before showing an attack as corroborated,
  while the pure sinking-outcome reconciliation path previously trusted only
  the canonical `multi_source_corroborated` label and two distinct group
  strings. The outcome-link path now **fails closed** unless the caller supplies
  `independence_verified is True`. Its database adapter runs the existing
  bounded read-only provenance audit before accepting a corroborated outcome.
  It does not mutate or publish the episode.
- Regression fixture corrected to the *actual* CONTSHIP JET NAVWARN 768/26
  sinking time **2026-10-28T20:30:00Z** and wreck coordinates **43.130000 N,
  28.756000 E**, 10 hours 30 minutes after the 10:00 UTC attack. The older
  synthetic fixture used 29 October 10:00 and did not test the documented
  chronology. Source: https://www.vtmis.bg/wx/wx_eng.htm .
- The Bulgarian Ministry of Transport's 28 October statement specifies a
  distress report received at **12:01 Bulgarian local time** (10:01 UTC),
  abandonment at **12:13 local** (10:13 UTC), and eight seafarers picked up at
  **12:53 local** (10:53 UTC); the remaining ten were in the ship's lifeboat.
  This is the **authorities' response timeline**, not SeaCommons ingestion
  latency. Source:
  https://www.mtc.government.bg/bg/category/1/18-chlenniyat-ekipazh-na-konteynerovoza-contship-jet-e-spasen
- The Bulgarian VTMIS live in-force page still displays NAVWARN 768/26 and
  KHORYV NAVWARN 766/26. The latter describes a capsized navigational hazard
  but gives no proof of hostile action. No additional independent attack
  corroboration is inferred from these navigational notices.
- No Oracle PostgreSQL read or LIVE/PLAY end-to-end check was possible in
  this run; no observed SeaCommons receipt timestamp is available. New
  candidate promotion remains blocked pending real lineage and AIS review.

## 31 October follow-up: batch preflight and retroactive negative controls

- Batch provenance audit now applies the same canonical eligibility preflight
  as the single-episode audit: attack-family episode, exact
  `multi_source_corroborated` state, and at least two distinct normalized
  independence-group labels. Ineligible episodes are returned with
  `canonical_verification_incomplete` **before** any observation or lineage
  database read. This reduces needless read-only PostgreSQL work and does
  not promote an incident. Three staging regressions cover rejected,
  duplicate-label, and mixed eligible/ineligible batches.
- **MSCIO 149/26**, Gulf of Aden, **2026-10-17**, approximately
  **12°54'N 047°56'E**: the source labels the case `Suspicious Activity`
  but describes a small craft opening fire and armed security returning
  warning shots. This is a **manual-review candidate for hostile-fire
  classification**, not a proven boarding, sinking or identified-vessel
  attack. Do not rely exclusively on the source category or a headline
  keyword; preserve both the reported shots and the source's own label.
  No IMO/MMSI or independent eyewitness lineage verified.
  https://mscio.eu/alerts/185
- **MARAD 2026-012** remains an active Black Sea / Sea of Azov risk
  advisory through **2027-03-22**. It points to NATO Shipping Centre and
  NAVAREA III warnings, but is **not evidence of a particular vessel attack**:
  https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations
- MARAD explains that its alerts/advisories use a **whole-of-government**
  publication process. Do not count a MARAD advisory and an agency
  reprint of that same advisory as independent confirmations merely because
  multiple departments participated in its preparation:
  https://www.maritime.dot.gov/msci/maritime-security-communications-industry-msci-web-portal
- Public source pages were accessible during this review; neither MSCIO
  ingestion rights nor SeaCommons receipt latency were established. The
  remote Oracle connector reported **0% available calls**, so no database
  queries, AIS verification, or LIVE/PLAY end-to-end certification occurred.

## 31 October: authority-alias hardening and newly checked primary sources

- Staging corroboration now canonicalizes cosmetic whitespace, underscore and
  hyphen differences in **authority identity labels** in both PLAY preflight
  and SourceObservation origin verification. For example, `Bulgarian_Navy`,
  `BULGARIAN-NAVY` and `bulgarian navy` count as **one authority**.
  Original report IDs, raw source URLs and provenance metadata are preserved;
  report IDs are **not** aggressively punctuation-normalized. This is a
  conservative false-positive guard, not a proof of independent origin.
  Four new regression cases cover preflight, direct audit and batch preflight.
- **Bulgarian Ministry of Defence, 13 October 2026:** a public statement
  explicitly refers to **two merchant vessels struck overnight** in the
  Black Sea. This is a useful *official retrospective discovery lead*, not
  two independently resolved vessel incidents: names, IMO/MMSI, exact event
  positions and independent source lineage are not established by this
  statement alone. Do not create two canonical attacks from this statement
  without matching primary reports:
  https://www.mod.bg/news9641
- **MSCIO 148/26**, event **2026-10-16T19:22:00Z**, approximately **78 NM
  northeast of Al Jubayl, Saudi Arabia**: a tanker was reportedly attacked
  by a rocket-propelled grenade from a small boat, with aft-port-quarter
  damage and crew safe. Original public notice:
  https://mscio.eu/alerts/184
  The vessel IMO/MMSI and independence of the originating report are not
  verified. Treat as an **October retrospective candidate**, not a
  corroborated database incident.
- **MSCIO 162/26** (30 October 18:00 UTC, south of Lavan) and
  **MSCIO 159/26** (29 October 22:12 UTC, northeast of Khasab) remain
  separate incident candidates. A second provider repeating the same
  initial vessel report is not automatically an independent source.
  Original notices: https://mscio.eu/alerts/198 and
  https://mscio.eu/alerts/195 .
- **MARAD 2026-012** is active through 2027-03-22, but is a regional
  advisory rather than incident-level evidence:
  https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations
- PostgreSQL Oracle, AIS, LIVE/PLAY and collector-receipt latency were not
  measured: the authorized remote connector still reports 0% available
  monthly calls. This is a documented access limitation, not evidence of a
  database outage. No historical record, scheduler or production service
  was modified. Full CI for these new commits is not yet certified.
