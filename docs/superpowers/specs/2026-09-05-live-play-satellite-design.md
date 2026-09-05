# Live / Play / Satellite Architecture

Date: 2026-09-05
Status: approved in chat

## Goal

SeaCommons separates operational awareness from historical reconstruction.
`live.seacommons.org` is a rolling 24-hour operational surface. `play.seacommons.org`
is a temporal OSINT reconstruction surface containing the complete incident history,
including source updates, AIS, drift products, satellite observations, and later news.

## Core rule

`archived` is not a real-world incident outcome. It describes retirement from the
operational Live surface. Public incident outcome and public surface are separate.

Canonical public incident statuses:
- `active`
- `needs_review`
- `resolved`
- `outcome_unknown`

Canonical public surfaces:
- `live`
- `play`

The existing persisted `lifecycle=archived` value remains readable for migration
compatibility, but new public contracts must expose `incident_status` separately.
## Live semantics

Live contains only material that is operationally current.

- Hard operational window: 24 hours from latest incident activity.
- `active` and `needs_review` may appear while inside that window.
- `resolved` leaves Live immediately, regardless of age.
- An `active` case with no update for 24 hours leaves Live and becomes
  `incident_status=outcome_unknown` in Play unless later evidence resolves it.
- A late post does not automatically return an incident to Live.
- A late linked source post is recorded as `attending_news`, `corroboration`, or
  `resolution` in Play.
- A genuinely renewed operational distress signal may explicitly reopen the case.

Live UI must not contain an ARCHIVED section. It presents current signals only.

## Drift semantics

There is one authoritative operational Drift chain:

`IntelEvent -> HumanitarianIncident -> current_drift_id -> DriftResult`

The backend/worker owns model computation. The frontend only renders products.
A drift must always be labelled as a model forecast, never as an observed track.
Resolved or retired incidents do not show operational drift in Live, but their
historical drift products remain available to Play at the time they were produced.
## Play semantics

Play is not a simulation surface and not a dumping ground for expired markers.
It is an incident-centric temporal reconstruction.

Each Play incident exposes a timeline of observations and derived products:
- founding source report;
- source updates and attending news;
- incident-state transitions;
- AIS observations/context;
- drift computations and later refreshes;
- satellite acquisitions and detections;
- corroboration and resolution evidence.

Moving the Play time cursor changes the map to the evidence available at that
point in time. Historical products are timestamped and never presented as current.

Cesium/Unreal simulation is removed from public Play. Play uses MapLibre and
raster/vector evidence layers. Existing simulation APIs may remain for operator
or research use, but are no longer the public Play product.

## Satellite role

Satellite data starts collecting when a geolocated incident is created, but it is
not the default Live basemap. Live shows a compact satellite-evidence summary only
when useful. Play preserves the complete satellite observation timeline.
The initial free provider stack is:
- Copernicus Data Space STAC for Sentinel-1/2/3 acquisition discovery;
- NASA Worldview/GIBS daily imagery for VIIRS optical context;
- Global Fishing Watch SAR detections when a token is configured and use is
  compatible with its non-commercial API terms.

`SatelliteObservation` is provider-agnostic and records at minimum:
- observation id, incident id, provider, mission, product id;
- acquisition time, discovery time, footprint/bbox;
- sensor type, resolution, cloud cover or polarisation when available;
- temporal relation: `reverse`, `nearest`, or `forward`;
- temporal delta from incident;
- source URL / asset reference and provenance;
- evidence status and optional vessel detections.

The resolver has three directions:
1. `reverse`: query acquisitions before T0 across the reachable corridor;
2. `nearest`: select the best acquisition around T0;
3. `forward`: keep collecting later acquisitions for the Play timeline.

For Humanitarian cases, satellite vessel association is conservative:
`candidate -> corroborated_candidate -> insufficient/disputed`.
A small-vessel target is never automatically asserted to be the distress vessel.
For Maritime cases, SAR detections may be reconciled against historical AIS and
labelled `ais_matched` or `ais_unmatched`, never `dark vessel confirmed` by default.
## UI contract

Live:
- left rail: current 24h feed only;
- center: operational MapLibre map;
- right panel: one consistent scrollable detail panel;
- detail blocks: status, source, coordinates, drift, AIS, satellite context;
- no simulation controls and no archived-feed language.

Play:
- MapLibre evidence map;
- bottom or side temporal scrubber;
- incident status always visible and independent from archive age;
- timeline event types use a stable vocabulary (`report`, `update`, `drift`,
  `ais`, `satellite`, `attending_news`, `resolution`, `corroboration`);
- satellite raster is selectable by acquisition time, never implied to be live.

## Data retention and audit

Leaving Live never deletes an incident. Canonical incident rows, transition rows,
claims, drift results, source observations, and satellite observations remain
queryable. Public Play receives only privacy-safe projections.

## Acceptance criteria

1. No Humanitarian Live feature older than 24h.
2. No `resolved` feature remains in Live.
3. Play retains the same incident with explicit `incident_status`.
4. A late linked post appears in Play without automatically re-entering Live.
5. Operational drift is selected only by `current_drift_id`.
6. Play can retrieve historical drift geometry for timeline replay.
7. Play public bundle contains no Cesium or Unreal renderer dependency path.
8. Satellite resolver can return reverse/nearest/forward metadata without credentials.
9. VIIRS daily context can be represented by dated GIBS layer metadata.
10. All external observations carry timestamp and provenance.