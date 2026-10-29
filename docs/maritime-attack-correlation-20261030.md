# Maritime attack correlation: staging design and 28 October regression

Date: 2026-10-30. This is an **unwired, pure-function staging prototype**, not a production integration. No database mutations, schedulers, deployment, LIVE/PLAY promotion, or map-color changes are performed by this branch.

## Verified case: CONTSHIP JET

- Vessel: CONTSHIP JET, IMO 9348625, MMSI 636019532.
- Bulgarian Ministry of Defence, 2026-10-28: three maritime-drone impacts; first impact reported 12:00 Bulgarian local time (10:00 UTC), about 17 nautical miles east of Cape Kaliakra; 18 crew rescued by 13:45 local.
  https://www.mod.bg/news9664
- Bulgarian Military District Prosecutor's Office, 2026-10-29: investigation opened into attack in Bulgaria's Black Sea EEZ.
  https://prb.bg/bg/news/aktualno/80101-voenno-okrazhna-prokuratura-sofiya-obrazuva-dosadebno-proizvodstvo-za-napadeniet
- Reuters, 2026-10-29: ship subsequently sank; attacker identity not established.
  https://www.reuters.com/world/europe/greek-container-ship-sinks-after-drone-attack-off-bulgaria-2026-10-29/
- PostgreSQL production read-only observations: 4,150 vessel_tracks for MMSI 636019532 (2026-08-29 through 2026-10-28); AIS at 2026-10-28 09:59:22, 43.265927N 28.814900E and 10:58:15, 43.256243N 28.810760E. Source: aisstream. The time-zone contract for the naive DB timestamp column must be verified before asserting exact UTC correspondence.
- Last linked intel_events row: aisgap:636019532 at 2026-10-26T12:24:22Z, 35.59084N 28.23322E. **This gap is two days and hundreds of kilometres away from the attack: do not correlate it with the attack.**
- Direct incident search found no attack alert for the vessel in intel_events and zero matching regional alert_events/anomaly_events in the previous manual audit. That is a failure to detect the attack, not a failure to track the vessel.
- A wide source_observations JSON-text scan timed out at 30 seconds. Do not run unindexed broad JSON scans against production. Prefer indexed time/source/identity candidate retrieval followed by bounded matching.

## Proposed evidence model

Persist three distinct times: occurred_at (event), published_at (source), received_at (ingestion). Preserve URL, original authority, source document/observation IDs, content hash, claimed vessel identity, uncertainty radius, original language, retractions, and reviewer actions.

1. News-to-incident claims: extract incident kind (attack, sinking, explosion, collision, piracy), vessel IMO/MMSI/name, incident time, approximate position, source and provenance.
2. Resolve entity with registry: explicit contradictory IMO/MMSI vetoes merge; matching name alone may nominate a candidate but must not establish a confirmed identity.
3. Temporal/spatial candidate search: start with ±6 hours for incident reports, ±2 hours for AIS positions; 35 km plus explicit position uncertainty for source-to-source claims. Revisit thresholds using labeled maritime incidents; never silently enlarge them to force a match.
4. Corroboration: at least two **independent original reporting groups** and a strong vessel identifier. AP and Reuters both quoting one Bulgarian ministry announcement are one underlying group, not two. An independent official investigative statement can supply a second group when it directly confirms the same claim.
5. AIS gap, stop, course change, loss of signal, and SART are supporting *context only*. They cannot originate an attack claim or increase the independent-source count. AIS reception coverage and spoofing flags must be checked before interpreting missing points.
6. Keep separate episode types for attack and later sinking. Keep an auditable link between them rather than flattening distinct event times into one.
7. PLAY -> incident promotion requires explicit operator-reviewed or evidence-policy-approved decision, with preserved original signal, event provenance, and rollback path. Do not overwrite historical raw events.

## Public taxonomy proposal (NOT YET WIRED)

- maritime_incident_candidate: orange
- maritime_attack (corroborated): red
- maritime_sinking (corroborated): bordeaux
- AIS anomalies: existing signal treatment; not an attack
- humanitarian distress/drift: separate taxonomy and unchanged palette

The UI should render a status badge and uncertainty/evidence popover; color alone must not imply certainty. Existing `core.domain.incident_taxonomy` currently has a closed maritime bucket vocabulary and must be updated deliberately alongside the front-end selector tests; do not silently insert a new label into LIVE or PLAY.

## Candidate retrospective incidents to cross-check

- 2026-10-23: KHORYV, reported sunk off Romania. Reuters: https://www.reuters.com/world/romania-blames-russia-drone-that-sinks-cargo-ship-1-killed-3-missing-2026-10-23/
- 2026-10-06: ALFA WATAN (reported sunk) and ABLE (reported hit, crew rescued), Associated Press: https://apnews.com/article/59f61af472f0379ebe7b1eb39b768c45
- 2026-10-25: Russia claimed attacks on two cargo vessels near Ukrainian ports; Reuters explicitly could not independently verify claims. Keep **unverified** until corroborated: https://www.reuters.com/world/russia-says-it-hit-cargo-vessel-ukrainian-logistic-hubs-overnight-2026-10-25/

Do not label these as detected by SeaCommons without checking vessel identity and actual DB event rows.

## Acquisition priorities and constraints

- Bulgarian MoD, Bulgarian Prosecutor, Bulgarian maritime authority, Romanian transport/naval authorities: authoritative primary statements, public pages; verify site-specific robots/terms, rate limits and latency before adapter integration.
- UKMTO official notices: maritime security alerts, especially Red Sea/Indian Ocean; verify accessible structured endpoints and terms before integration. https://www.ukmto.org/
- MARAD MSCI: published alerts/advisories and GovDelivery email subscription (not a documented free push API); do not claim an API exists. https://www.maritime.dot.gov/msci/us-maritime-alerts-and-advisories-subscriptions
- GDELT DOC 2.0: free multilingual news discovery with roughly 15-minute indexing, JSON/RSS article lists. **Discovery only**, not independent corroboration; check API quotas/terms. https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
- GDELT Cloud is a different product requiring API keys/plan access; do not conflate with public DOC 2.0. https://docs.gdeltcloud.com/API_DOCUMENTATION_GUIDE
- NATO Shipping Centre / NGA NAVAREA / MSCIO / ONI: evaluate geographical coverage and official access paths; do not assume that they cover every Black Sea attack.

## Integration checkpoints

- [x] Independent staging branch with pure correlation and negative regression tests.
- [ ] Run tests in isolated checkout and verify full repo compatibility.
- [ ] Add indexed source/identity candidate queries and migration plan after EXPLAIN.
- [ ] Add source ingestion adapters with provenance and content hashes.
- [ ] Implement reversible reviewed PLAY incident promotion with durable audit trail.
- [ ] Extend taxonomy + map markers + mobile LIVE/PLAY tests.
- [ ] Replay 28 October and October candidate set, measure precision/recall and source-to-alert latency.
- [ ] Obtain explicit production deployment approval.
