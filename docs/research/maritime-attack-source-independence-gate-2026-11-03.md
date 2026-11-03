# Maritime attack correlation — source independence and publication gate (2026-11-03)

Status: investigative staging specification; NOT production ingestion, NOT evidence of an attack. No automatic promotion.

## Newly observed official-source ambiguity
- UKMTO Recent Incidents (https://www.ukmto.org/recent-incidents) lists warning 191-2026 on 2026-11-01: a merchant vessel master relayed a VHF channel 16 Mayday from a different vessel reportedly struck by an unknown projectile in the Strait of Hormuz.
- MSCIO alert 164/26 (https://mscio.eu/alerts/200), published 2026-11-01, describes a merchant vessel master receiving a VHF channel 16 Mayday for another vessel reportedly struck by an unknown projectile, incident approximately 15:09 UTC.
- Candidate relation: SAME UNDERLYING RELAY, unverified. Neither bulletin names the vessel or identifies an independent first-hand witness. Two publisher URLs are NOT two independent origins. Set independent_origin_count=0 until the original testimony provenance is established; do not auto-publish as corroborated.
- UKMTO Recent Incidents also lists two differently located 2026-11-02 attack notices with confusingly similar warning text 192-26 / 192-2026: one 72 NM east of Ras Al Khafji (tanker struck twice port side), another 9 NM northeast of Lima/Limah, Oman (hole starboard side). Never deduplicate by bulletin number alone; preserve separate publisher item IDs and original URLs, and verify chronology/identity.

## Correlation and review gate
1. Persist raw source records append-only with source_url, publisher, publisher_item_id, retrieved_at_utc, published_at_utc (nullable), claimed_event_time_utc (nullable), timestamp_precision, original text digest, license/redistribution policy, original_reporting_entity (nullable), reporting_chain, evidence_kind and provenance.
2. Extract entities: IMO (validated check digit), MMSI (9 digits), call sign, vessel name aliases, flag, coordinates (datum/precision), vessel type, geotemporal uncertainty, report modality (first-hand master, second-hand relay, authority investigation, press quoting bulletin).
3. Candidate matching requires vessel identity AND plausible space/time, or manual review when vessel IDs absent. Strong IMO identity may still require track plausibility. Same bulletin IDs without matching publisher are never globally unique.
4. Independence graph: connect derivative reports to common original observer or originating authority. Count connected origin groups, not URLs/domains; unresolved reporting chains count as UNKNOWN, not independent. An AIS stop/gap is a behavioral signal, never a witness or an attack confirmation. Reprinted media are not independent.
5. Classification: reported, corroborated, verified, rejected, needs_review. Promotion to confirmed attack requires a primary verified authority/first-hand statement plus a genuinely independent supporting origin, or documented equivalent review policy. Record reason, operator/reviewer, source snapshots, source versions and event-time uncertainty. Do not infer attacker.
6. Publish only reviewed, sufficiently located events. LIVE if within 24h by event time or active with a documented update; PLAY for historical events. Single stable incident ID across LIVE/PLAY, no duplicate records. Missing location -> investigation queue, not arbitrary map pin. Distinguish maritime_attack from humanitarian_distress/drift.
7. Regression fixtures: CONTSHIP JET IMO 9348625 / MMSI 636019532 / 2026-10-28 10:00 UTC (requires fresh authoritative incident + AIS evidence); MSCIO164/UKMTO191 shared relay; two UKMTO192-like notices separate; AIS blackout without attack = false positive; reported attack with continuous AIS = false negative; time-late bulletin publication vs event time; corrected/withdrawn bulletin; vessel-name alias collision.

## Source expansion and constraints
- Official incident feeds: UKMTO, MSCIO, IMO confirmed incident lists, flag/coastal state maritime authorities, national transport/defence ministries, coast guards, NAVAREA/NAVTEX, MARAD, NATO Shipping Centre, ONI. Verify each page's access method, terms and permissible storage before automated ingestion.
- Independent modalities: AIS positional behavior (not proof), vessel operator/flag-state statement, maritime rescue radio logs where lawful, port authority and harbour master notices, verified geolocated imagery (Sentinel-1 SAR / Sentinel-2 optical via Copernicus Data Space subject to revisit/cloud/latency), satellite fire/thermal hotspots (NASA FIRMS subject to spatial false positives), independent ship photography and authenticated eyewitness reports.
- News discovery: GDELT and reputable media to surface candidates; deduplicate syndication and direct quotation of the same official notice.
- Measure both HTTP latency and publication-to-retrieval latency separately; HTTP 200 is not proof of open license, and HTTP 403 is not proof that a source lacks public material.

## Before integration
Read-only audit of intel_events, vessel_tracks, alert_events, anomaly_events, humanitarian_incidents, forensic_events and LIVE/PLAY endpoints; staging-only storage and end-to-end tests; verify API schema/UI layer, date routing, source attribution, evidence policy, nonpromotion of unverified reports. Never change production database or deploy without explicit approval.
