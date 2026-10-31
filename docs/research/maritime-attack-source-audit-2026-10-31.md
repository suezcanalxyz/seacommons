# Maritime attack correlation: source audit (2026-10-31 UTC)

Staging research record only. No source was imported into production, no database
record was changed, and no publication decision is implied. An incident's
reported facts and a source's independent corroboration are different questions.

## Gulf of Aden / Somali Basin: AZINI, MSCIO 161/26 (31 October review)

- Official alert: https://mscio.eu/alerts/197 ; classification **PIRACY**.
- Reported hijacking of fishing vessel **AZINI** on 2026-10-29 at approximately
  09:00 UTC off northeastern Somalia. Vessel IMO/MMSI and exact hijacking
  coordinates are **not established** by this alert. Crew welfare unknown.
- The 09°42'N, 053°55'E coordinate is explicitly a **last reported position
  at 2026-10-30T04:00:00Z**, not a geocoded hijacking event. UPDATE01 gives
  09°47'N, 055°45'E as a later reported position **without a verified UTC fix
  timestamp**. Do not calculate speed, interpolate a trajectory, create a
  drift polygon, or substitute either position for the incident location.
- The public alert page displays 2026-10-31 09:24, timezone not established;
  the original release and update clock times and SeaCommons collector receipt
  remain unknown. No ingestion-latency estimate is justified.
- Potential use as a pirate mothership is a **warning, not an observed attack**.
  ATALANTA is investigating. Do not merge this case with MSCIO 160/26's
  separate armed-skiff approach on 30 October, and do not map it as a military
  `maritime_attack`. This remains a **single-source piracy candidate**.
- Source terms: https://mscio.eu/terms-of-service/ prohibit general
  redistribution/publication of site contents. Store the link and limited
  structured references for internal review; do not mirror the text or
  automatically publish an incident without legal and evidentiary review.

## Pure correlator consistency patch (31 October)

- `maritime_attack_correlation.py` now applies the same cosmetic-separator
  authority equivalence as PLAY and the canonical provenance audit:
  `Bulgarian_Navy`, `bulgarian navy`, `BULGARIAN-NAVY` represent one
  original authority. Internal group keys retain underscore formatting.
- Reviewed `SourceObservation` conversion validates both `published_at_utc`
  and `published_at` where present, rejects contradictory UTC instants
  (more than five minutes apart), and retains an `_utc`-only timestamp.
- Six new pure-Python regression cases cover authority aliases, genuinely
  independent origins, publication aliases, and AZINI's piracy classification.
  These changes are **staging-only**. CI and database runtime validation must
  be reported separately; no production ingest or promotion is implied.

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

## Black Sea: CONTSHIP JET, prosecutorial record (29 October)

- Bulgarian Prosecutor's Office, Military District Prosecutor Sofia, dated
  2026-10-29:
  https://prb.bg/bg/news/aktualno/80101-voenno-okrazhna-prokuratura-sofiya-obrazuva-dosadebno-proizvodstvo-za-napadeniet
- Opened pre-trial proceedings concerning the naval-drone attack on the
  Liberian-flagged CONTSHIP JET in Bulgaria's Black Sea EEZ. The case was
  referred by Military Police Varna; investigators intend to interview crew
  members and establish ownership, cargo, route and damage.
- This is **an independently published procedural development**, not proof
  that the prosecutor independently observed the original attack. Do not count
  it as a second original attack witness without examining the underlying
  investigation records. No perpetrator is identified or proven.
- Source availability checked 2026-10-31. Exact article publication clock time,
  licensing for full-text republication and SeaCommons collector receipt are
  unknown. Preserve the link and extracted facts, not a full-text copy.

## Staging guard update (31 October)

- Canonical provenance audit and reviewed-observation correlation now strip
  surrounding whitespace and casefold the `service` field before rejecting
  `humanitarian`. This prevents a padded value such as ` HUMANITARIAN ` from
  being relabelled as attack evidence. Two regression tests cover both paths.
- This is staging-only, does not modify historical rows, and does not change
  LIVE/PLAY publication policy. CI and Oracle runtime verification must be
  reported separately.

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

## 31 October, chronology gate and primary-source refresh (staging only)

- **Code safety:** the SQLAlchemy-backed single-episode and batch provenance
  audits now require both `observed_at` and `received_at` for every
  canonical `source_observations` row. A missing pair fails closed with
  `missing_observation_chronology`; a missing half remains
  `invalid_observation_chronology`. Legacy pure fixture callers can opt out
  explicitly; the database adapters always enable the strict gate. No schema
  changes, database writes, or production deployment. Four regressions added.
- **MSCIO 151/26**: reported attack at **2026-10-21T01:45:00Z**, approximately
  **11 NM west of Bukha, Oman**, Strait of Hormuz. A tanker was reportedly
  struck by an unidentified projectile; a fire was extinguished and the vessel
  was at anchor with crew safe. Source:
  https://mscio.eu/alerts/187 . Vessel IMO/MMSI and independent original
  reporting are not established. This is an October retrospective lead, not
  a corroborated database record. Publication is displayed as 21 October
  11:26 a.m. without a reliably established timezone: no UTC source latency
  is inferred.
- **MSCIO 160/26**: reported 30 October **02:25 UTC**, Gulf of Aden,
  **11°57.4'N 045°04.5'E**. The source explicitly reports **no shots fired**
  and **no attempted boarding**. Keep `suspicious_activity`, not
  `maritime_attack`: https://mscio.eu/alerts/196 .
- **MSCIO 162/26**: 30 October **18:00 UTC**, 40 NM south of Lavan Island,
  unnamed vessel struck by unknown projectile, fire onboard, crew safe.
  https://mscio.eu/alerts/198 . Do not treat a UKMTO copy of the same
  original vessel report as an independent corroboration.
- **CONTSHIP JET**: original VTMIS NAVWARN 768/26 remains accessible at
  https://www.vtmis.bg/wx/wx_eng.htm . IMO `9348625`, sinking
  **2026-10-28T20:30:00Z**, wreck at **43.130000 N, 28.756000 E**.
  Preserve this as an outcome of the 10:00 UTC attack, not a second attack.
  AIS positions and the operational database were **not** checked.
- **Source reuse:** the Bulgarian Ministry of Defence site states that
  publicly available information may be copied and redistributed with
  explicit source attribution (footer of https://www.mod.bg/news9641).
  UKMTO terms explicitly refer to the Open Government Licence:
  https://www.ukmto.org/terms-and-conditions .
  MSCIO content redistribution remains subject to its own terms; public
  availability alone is not a reuse licence. VTMIS automated reuse remains
  unverified.
- **Access/latency:** the Oracle PostgreSQL connector was previously blocked
  by exhausted quota. No Oracle SQL was executed during this run. Provider
  publication times are not SeaCommons collector-receipt times; collector
  latency and LIVE/PLAY end-to-end behavior remain unmeasured.


## 31 October follow-up: primary transport report, KHORYV reclassification lead, and timestamp aliases

- **Bulgarian Ministry of Transport, 13 October (primary, English):**
  https://www.mtc.government.bg/en/category/1/technical-information-vessels-affected-and-those-provided-assistance-maritime-areas-republic-bulgaria-over-past-24-hours
  Officially identifies **CHELSEA-3** (Maltese flag, 15 crew, 17 NM east of
  Byala, incident reported at **01:15** on 13 October) and **HS Dignity**
  (Guinea-Bissau flag, 16 crew, drone strike at **01:20**, sank 17 NM east
  of Shabla). The publication does not explicitly label these clock times
  as UTC: preserve local-time uncertainty and do not fabricate conversion.
  Five HS Dignity survivors were first assisted by Azov Concord and SCANDI
  ASSERTER. This is a **single ministerial reporting origin**; BTA's
  transcription is not a second independent confirmation.
- **AIS gap causal negative:** the ministry explicitly states that the
  initial HS Dignity sinking report came from a rescued seafarer and
  **coincided with loss of AIS**. The seafarer's report and ministry's
  statement are the evidence of sinking; AIS silence is supporting context,
  never independent evidence of attack or proof of sinking.
- **KHORYV status correction:** NAVWARN 766/26 *alone* still establishes
  only a navigation hazard. However, the Romanian Naval Authority's
  23 October SAR statement (as published by the Romanian national
  news agency) identifies KHORYV, 13 crew, a distress call around 10:00
  **Romanian local time**, 13 NM off Constanta, nine people rescued alive,
  one body recovered and three missing **at the time of publication**:
  https://agerpres.ro/english/2026/10/23/major-rescue-operation-offshore-of-constanta-for-crew-of-vessel-at-risk-of-sinking-one-dead--1606115
  Reuters separately reports a suspected drone strike and a public
  attribution by Romania's president:
  https://www.reuters.com/world/romania-blames-russia-drone-that-sinks-cargo-ship-1-killed-3-missing-2026-10-23/
  These developments mean KHORYV is **not a globally attack-negative
  vessel fixture**. Keep the narrow regression that the VTMIS warning
  *by itself* cannot establish hostile causation, but open a separate
  23 October attack-review candidate; do not merge the 23 October event
  and 28 October hazard without IMO/MMSI and outcome chronology review.
  The president's attribution is a documented statement, **not a
  verified perpetrator finding**. No final casualty update established.
- **UKMTO 189-26 / MSCIO 163/26**, time-late report on **28 October**,
  outbound tanker in Strait of Hormuz hit by unknown projectile. MSCIO
  source https://mscio.eu/alerts/199 is directly accessible. The
  UKMTO 189-26 PDF was **not directly retrieved**; public secondary
  summaries describe the same event. Treat the two notices as a
  probable **shared-report pair**, not independent corroboration.
  Event hour, vessel identity, precise coordinates, originator and
  SeaCommons receipt time remain unknown; do not merge with 29/30
  October Lavan/Khasab incidents.
- **Staging code hardening:** publication timestamps may appear under
  both `published_at_utc` and `published_at`. The canonical
  provenance audit now parses both, rejects malformed/date-only values,
  and fails closed on contradictions greater than five minutes.
  A date without a clock time no longer supplies minute-level proof.
  Four regressions added, including equivalent UTC/offset timestamps.
  This affects only staged verification, not immutable source rows.
- **Operational limitation:** Oracle Desktop Commander quota checked at
  **0% available** on 31 October. No Oracle SELECTs, AIS validation,
  LIVE/PLAY endpoint certification, source ingestion or production deploy.
  GitHub CI for these newest staging commits was not confirmed at
  documentation time.

## 31 October, 13:20 UTC follow-up: immutable-ID collision guard and live source availability

- **Staging safety change:** `correlate()` now rejects a batch if two
  `IncidentClaim` objects reuse one `claim_id` but disagree on any
  field (e.g. authority, original report, event time, vessel identity).
  Replaying the *identical* claim remains idempotent. This prevents
  input order from deciding which purported immutable observation is
  admitted to a multi-source attack cluster. Failure reason:
  `conflicting_duplicate_claim_id:<id>`. This is a pure, fail-closed
  staging guard: no database writes or LIVE/PLAY promotion.
- **Regression coverage:** exact duplicate replay, conflicting original
  authority/report metadata in both input orders, and conflicting event
  timestamps with a second otherwise-independent report. The last two
  are new negative tests. CI must be read from the workflow run for the
  exact test commit, not inferred from earlier green commits.
- **MSCIO source availability, 31 October:** the public index
  https://mscio.eu/alerts/ currently rendered `Recent Incidents (0)`
  in a text-only fetch while individual numbered alert URLs remained
  accessible in previous source audits. **Do not interpret the index's
  empty client-side listing as zero actual incidents.** The collector
  needs an explicit HTML/API availability check and a fallback to
  individual source URLs; no authenticated/private endpoint assumed.
  Direct text-fetch attempts of https://mscio.eu/alerts/196 ,
  https://mscio.eu/alerts/197 , https://mscio.eu/alerts/198 , and
  https://mscio.eu/alerts/199 **failed in this run**. Therefore current
  item-level availability is unverified; this does not prove deletion.
- **UKMTO source availability, 31 October:** the public index
  https://www.ukmto.org/recent-incidents likewise rendered `0 reports`
  in a text-only fetch. This is an extraction/access limitation, not
  proof that warnings 188-26/189-26 or earlier reports were withdrawn.
  Verify individual original warning PDFs before attributing lineage
  or counting independent reports.
- **MARAD current advisories, 31 October:**
  https://www.maritime.dot.gov/msci-advisories publicly lists active
  2026-010 (Indian Ocean piracy), 2026-011 (Persian Gulf/Hormuz),
  2026-012 (Black Sea/Azov), 2026-013 (Red Sea), 2026-014
  (worldwide influence), and 2026-015 (global resources). These are
  regional/context advisories, **not incident-specific attack evidence**.
  The website shows publication/effective dates, not SeaCommons
  collection/receipt latency.
- **New Black Sea negative controls, 31 October:** Bulgaria VTMIS
  https://www.vtmis.bg/wx/wx_eng.htm lists NAVWARN **776/26**
  (scheduled naval diving exercise south of Cape Galata, 3–5 November)
  and **777/26** (hydrographic survey in Burgas Bay, 3–6 November).
  Both are navigation/safety notices, **not reported attacks**. Do not
  convert their military or operational terminology into an incident.
- **Independent background:** IMO's 13 July statement on attacks on
  Black Sea/Azov merchant ships is available at
  https://www.imo.org/en/mediacentre/pressbriefings/pages/statement-on-attacks-in-black-sea-and-sea-of-azov.aspx .
  It is strategic context, not a second CONTSHIP JET witness.
- **Operational access:** Remote Desktop Commander account reported
  `remote_calls_left_pct: 0` again. No Oracle queries were attempted.
  The SQL audit of `intel_events`, `vessel_tracks`, `alert_events`,
  `anomaly_events`, `humanitarian_incidents`, `forensic_events`,
  `source_observations`, `lineage_edges`, and `maritime_episodes`
  remains prepared but **unexecuted**. Collector latency and actual
  LIVE/PLAY incident representation remain unknown. No new cron,
  VM loop, production deployment, or historical record mutation.


## 31 October follow-up: AIS identity, provenance, and read-only SQL

- In the staging-only pure correlator, a valid IMO is **not** enough to
  authorize AIS matching when the subject MMSI is a placeholder or malformed.
  AIS proximity, AIS spatial-conflict checks and gap-context matching now
  require a valid subject MMSI. An invalid MMSI cannot create a spurious AIS
  support signal, even when the incident has two independently attributable
  primary reports. AIS never independently corroborates an attack.
- Structured source evidence now includes optional latitude/longitude and
  **spatial uncertainty in kilometres**, in addition to event time,
  publication/receipt times and time uncertainty. Unlocated incidents retain
  null coordinates; no position is inferred from a later AIS fix.
- The prepared read-only PostgreSQL audit now casefolds/trims maritime_domain
  and service before excluding humanitarian rows. The SQL has **not** been
  executed on Oracle; Desktop Commander reports no available remote calls.
- Official MARAD 2026-013 (active, issued 2026-09-23) explicitly advises
  that operators may turn off AIS when its continued operation compromises
  vessel safety. Therefore an AIS gap is an ambiguous signal, **not** evidence
  of hostile action: https://www.maritime.dot.gov/msci/2026-013-red-sea-bab-el-mandeb-strait-gulf-aden-arabian-sea-and-somali-basin-houthi-attacks
- MARAD 2026-012 remains active for the Black Sea through 2027-03-22 and
  describes general maritime hazards, not independent confirmation of any
  specific CONTSHIP JET attack:
  https://www.maritime.dot.gov/msci/2026-012-black-sea-and-sea-azov-military-combat-operations
- GDELT 2.0's documented 15-minute source update cycle is **not** measured
  SeaCommons ingestion latency. Original documentation:
  https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/
- Two new Python regressions cover invalid subject MMSI with valid IMO and
  preservation of location uncertainty. Code, tests and SQL remain staging-only.
  No collector, scheduler, VM cron, historical record update or production
  deployment was introduced. Verify the latest GitHub Actions run separately.
