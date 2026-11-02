# SeaCommons maritime attack correlation — ABLE damage assessment and spatial evidence integrity

Audit time: 2026-11-02 08:31–08:36 UTC. Branch: feature/maritime-attack-correlation-20261030. Previous head: 30677231. No production deployment, production writes, historical modifications, new cron/timer/scheduler or persistent VM loop.

## Staging-only changes

- Added **damage_assessment** as a distinct non-attack source kind in the official bulletin adapter, canonical preview and case-review context. It is never an independent attack witness.
- Added source-checked metadata-only Bulgarian Defence Ministry 9 October inspection of **ABLE**, original report BG_MOD:news9637 (https://www.mod.bg/news9637). The report confirms inspection of drone-related damage, fire and flooded engine room, but does **not** supply IMO, MMSI or the exact clock of the 6 October strike. The structured observation therefore uses **event_date=2026-10-09** for the inspection, **publication_date=2026-10-09**, no coordinates, no IMO/MMSI and no attack candidate. Ministry footer allows free copying with explicit source attribution; re-use review remains false.
- Expanded the staging evidence-ledger fingerprint to include the original-source reported location (lat, lon, role, uncertainty) and reported vessel identifiers. This prevents a location revision from leaving the derived ledger fingerprint unchanged. Invalid, NaN, out-of-range or negative-uncertainty geometry fails closed. This hash is **not** a cryptographic attestation of the original document.
- Added regression tests for the ABLE inspection, the non-merger of ABLE/ALFA WATAN/CONTSHIP JET, spatial-ledger revision sensitivity, invalid coordinates and an isolated PostgreSQL persisted-row roundtrip with rollback.
- Added the new manifest to GitHub Actions staging path triggers.

**Important:** The 6 October attacks on ABLE and ALFA WATAN remain separate retrospective leads. The inspection notice is not a direct, minute-precise attack report. The vessel IMOs 9001136 (ABLE) and 7510884 (ALFA WATAN) were reported separately by BTA/BGNES and must not be attributed to the Bulgarian Defence Ministry source: https://www.bgnes.com/politics/drones-strike-two-ships-in-bulgarian-waters-ferry-rescues-crew-of-one-as-other-sinks . No perpetrator attribution.

## Oracle PostgreSQL read-only audit

At 2026-11-02 08:31:06 UTC, 72h cutoff 2026-10-30 08:31:06 UTC. Used existing application PostgreSQL URL with PGOPTIONS default_transaction_read_only=on and statement_timeout=7000. No credentials logged.

| Table / query | Count | Previous 07:25 UTC |
|---|---:|---:|
| intel_events (timestamp_utc ISO prefix >= 72h cutoff) | 10,169 | 10,093 |
| vessel_tracks (ts >= 72h cutoff) | 804,220 | 803,439 |
| alert_events | 0 | 0 |
| anomaly_events | 0 | 0 |
| humanitarian_incidents updated_at | 21 | 21 |
| forensic_events | 11 | 11 |
| official maritime source_observations since 1 Oct (target issuers/types) | 0 | 0 |
| maritime_episodes attack/piracy/explosion/sinking families | 0 | 0 |

Counts are moving-window snapshots, not proof of new ingestion. CONTSHIP JET MMSI 636019532: 28 Oct 09:59:22 UTC 10.2 knots, 10:34:46 UTC 0.6 knots; five AIS fixes in the 09:45–11:10 window. AIS gap and slowdown are context, never independent proof. Bulgarian MOD https://www.mod.bg/news9664 reports attack at 10:00 UTC; VTMIS https://www.vtmis.bg/wx/wx_eng.htm NAVWARN 768/26 documents a later sinking at 20:30 UTC, not a second attack.

A broad substring search for ABLE produced false hits from the word **cable**. Corrected read-only search using word boundaries yielded only four earlier CONTSHIP JET sudden-stop anomaly titles (5 and 16 October), **none on 28 October** and no ABLE/ALFA WATAN title matches. These earlier AIS anomalies are not attack evidence.

## Public API and sources

- PLAY counts: 3,578 total (3,449 maritime; 129 humanitarian), generated_at 07:25:48 UTC. This run did not establish a consistent full-catalog snapshot.
- LIVE signals (3 days): 14 returned, zero attack/piracy category hits.
- LIVE pipeline at 08:31 UTC: AIS, first-party, public feeds live; partner degraded; radio degraded, DSC accepted 60, NAVTEX accepted 0. Radio decoding of NAVTEX is not certified.
- One-off GET from VM: Bulgarian MOD ABLE HTTP 200 (525 ms), MOD CONTSHIP 200 (252 ms), VTMIS 200 (162 ms), MSCIO 162/26 200 (1,257 ms); UKMTO/MARAD/NATO Shipping Centre/ONI 403; GDELT TLS handshake timeout (9.1 s). These are HTTP response times, **not** source-publication-to-ingestion latency. No bypass of restrictions.
- Current 72h lead: MSCIO 162/26, 30 October ~18:00 UTC, reported attack/fire on unidentified vessel (https://mscio.eu/alerts/198). No verified vessel crosswalk or independent originating witness; not publishable. The 1 November reported Hormuz tanker explosions also remain unverified without vessel IDs. Retrospective: CONTSHIP JET, ABLE, ALFA WATAN, MSCIO 159/26, AZINI.

## Gate and next work

Staging-only source inspection is validated as **context**, not promoted to attack. The evidence ledger now fingerprints geometry and vessel identifiers, but source authenticity and independent eyewitness origins remain unverified. The blocking operational dependency remains an isolated persistent staging DB/review interface and legally authorized official bulletin collectors. No historical edits or production deployment.
