# Persistent real-time episodes — implementation contract

Status: implementation specification, not a completed pipeline.

## Invariants
- One stable episode_id across LIVE, PLAY, API, feed and dossier.
- First detection timestamp (detected_at UTC) controls PLAY eligibility: detected_at + 24h, irrespective of resolution.
- PLAY inclusion is additive: after 24h, open episodes remain visible and continue to update. No duplicate episode is created during promotion.
- Closing an episode does not remove it from PLAY. Preserve an append-only evidence history.
- Never manufacture endpoint coordinates or interpolate an observed AIS track across an unobserved gap.
- A visual timer is not a sensor refresh. Show last_observed_at and last_processed_at separately.
- DRIFTER out of scope.

## Proposed episode fields
episode_id; episode_type; status (detected, active, resolved, archived); detected_at; started_at; ended_at nullable; last_observed_at; last_processed_at; source_refs; vessel_identity nullable; origin {lat,lon,time,source} nullable; endpoint nullable; evidence_version; classification; confidence; assessment; updated_at.

All times UTC; immutable source observation IDs; idempotent upserts keyed to episode_id.

## AIS gap
1. Detect missing AIS relative to a vessel's last valid observation; store that observation as origin.
2. Keep endpoint null while active. Duration = now - origin.time for an active gap, otherwise endpoint.time - origin.time.
3. Process incoming valid positions in timestamp order; reject stale or conflicting observations for automatic closure.
4. On verified reappearance, set endpoint to first valid post-gap AIS observation, resolve once and append evidence. Preserve uncertainty of the unknown path.
5. On contradictory data, reopen/reassess by explicit revision, never overwrite historical evidence.

## Position integrity
Store triggering observation pair and anomaly metrics; monitor later positions and source consistency. End is an evidence-supported time, not necessarily a geographic endpoint. Retain original anomaly and reassessment history.

## Attacks, maritime safety, humanitarian
Use same episode identity, monitoring, evidence revision and 24h visibility policy. Category-specific closure conditions; do not infer geographic endpoints for event types without them. Humanitarian drift estimates remain modeled positions and carry model timestamp and uncertainty.

## Read API and UI contract
- LIVE query: recent episodes with live updates and status; never freeze cases when PLAY eligibility begins.
- PLAY query: detected_at <= now_utc - 24h, including ACTIVE episodes, with updates to same episode_id.
- If LIVE has a 24h recent-only filter, an open older episode must remain accessible in LIVE's active monitoring layer.
- Client deduplicates by episode_id and evidence_version.
- UTC operational clock; status ONGOING/RESOLVED; elapsed time; observed-vs-modeled styling; origin/endpoint and source links.
- Keep semantic palette: humanitarian red, position integrity purple, AIS gap lime #d4ff3f, maritime safety blue, sanctions pink, attack crosshair overlay.

## Acceptance tests
1. AIS gap at T0 with origin, null endpoint; elapsed time increases while no new AIS arrives.
2. Same episode at T0+23h59 is not yet in PLAY; at T0+24h it appears in PLAY without new ID.
3. At T0+25h still active: PLAY reflects fresh evidence and advancing duration.
4. Valid reappearance at T0+53h: one episode resolved with correct endpoint and duration, still visible in PLAY.
5. Out-of-order AIS, repeated ingest, late evidence and reconnect do not duplicate or regress the episode.
6. Position integrity updates confidence and resolution without erasing the triggering observations.
7. All categories use consistent markers, legends, dossier timestamps and provenance.
8. Test API, migrations, backend workers, LIVE/PLAY browser E2E and MapLibre on mobile before merge.
