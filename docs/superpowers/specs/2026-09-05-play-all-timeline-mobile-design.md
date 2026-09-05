# Play ALL / Timeline / Mobile Design

Date: 2026-09-05
Status: approved in chat

## Goal

`play.seacommons.org` opens as a map-first archive surface showing the complete
public Play archive by default. The temporal scrubber is inactive at the rightmost
`ALL` position and only becomes a historical filter when the user drags it left.
Mobile must prioritize the map and never compress it beneath permanently visible
case/evidence panels.

## Default ALL mode

The default Play state is `mode=all`.

- Load every public Play incident returned by the Play incident index.
- Render all archived Humanitarian and Maritime incident points on the MapLibre map.
- Preserve each incident's canonical `incident_status` independently from age.
- The rightmost timeline position is a semantic `ALL` sentinel, not a timestamp.
- While at `ALL`, no temporal cutoff hides incidents.
- Selecting an incident opens its dossier without leaving `ALL` mode.
- Satellite imagery/context may be available for the selected incident but does not
  replace the archive point layer or imply a current acquisition.

## Temporal mode

Dragging the scrubber left switches Play to `mode=temporal` with a concrete UTC
cutoff. The map becomes a reconstruction of what was publicly knowable by that time.

- Hide incidents whose first public report is later than the cutoff.
- For visible incidents, show the status effective at the cutoff, not today's status.
- Use only timeline items whose `at <= cutoff` for drift, satellite, AIS, updates,
  attending news, correlations, and resolution evidence.
- Pick the latest eligible evidence item per layer at or before the cutoff.
- Returning the scrubber fully right restores `mode=all` and the full archive.
- The UI must label temporal mode with the selected UTC date/time.

The timeline is therefore global when no incident is selected and incident-specific
inside an opened dossier. The global timeline filters the archive map; the dossier
timeline explains the selected case using the same cutoff.

## Mobile interaction

At viewport widths <=680px Play is map-first:

- Header is compact and shows `PLAY`, current mode (`ALL` or time), and archive count.
- The map occupies the available viewport between header and timeline control.
- The permanent case rail is removed from layout and becomes an optional drawer.
- The permanent evidence rail is removed from layout.
- Tapping an archive point opens a bottom sheet dossier over the map.

- Bottom sheet states: collapsed summary, expanded dossier, dismiss-to-map.
- The bottom sheet must scroll independently and respect safe-area insets.
- The timeline control stays reachable above the bottom safe area.
- No fixed-height rows may force the map below the fold on common iPhone heights.
- Horizontal overflow is prohibited at the document/root level.

Desktop/tablet may retain case list + map + evidence layout, but still opens in `ALL`
mode and uses the same global cutoff semantics.

## Archive map model

The Play incident index must provide enough geometry and status data to render the
archive without fetching every incident timeline. The frontend first renders the
index points, then fetches a selected incident timeline on demand.

Map layers:
- Humanitarian incident points, styled by source/category and status.
- Maritime incident points, styled separately from Humanitarian.
- Selected incident emphasis.
- Selected/historical drift geometry when eligible for the active cutoff.
- Selected satellite acquisition footprint/raster context when eligible.
- Future correlation overlays must be additive and provenance-labelled.

If an incident has no reliable coordinate, keep it searchable in the archive drawer
but do not invent a map location.

## Dossier and explanation contract

The bottom sheet / desktop evidence panel is an incident dossier, not a raw event log.
It groups evidence into stable sections: Summary, Sources, Drift, Satellite, AIS,
Correlations, Status history, and Attending news. Each claim must be traceable to
structured evidence already stored by SeaCommons.

Explanations are deterministic in this tranche: derive short human-readable reasons
from `EventAssessment`, `CorrelationDecision`, claims/assessments, drift metadata,
satellite metadata, and incident transitions. Do not call an LLM/NVIDIA NIM in this
release. If generative synthesis is added later, it must consume these structured
facts and preserve citations/provenance.

## Alarm Phone visibility check

This Play tranche does not change ingest policy, but rollout verification must check
that Alarm Phone remains continuously collected through Twikit priority polling and
RSS fallback. Missing public posts must be classified as one of:
- collected + published;
- collected + intentionally private by public policy;
- collected + merged/correlated to an existing incident;
- genuinely missing from ingestion.

No UI change may hide a published Alarm Phone incident that satisfies the Play/Live
surface rules.

## Acceptance criteria

1. Opening Play with no selection renders all geolocated public Play incidents.
2. The timeline initializes at `ALL`, with no date cutoff applied.
3. Dragging left applies a UTC cutoff and removes future incidents/evidence.
4. Returning fully right restores the complete archive.
5. On <=680px viewport, the map is the primary surface and is not vertically clipped.
6. Case browsing on mobile is drawer-based; dossier is a scrollable bottom sheet.
7. Root/document has no horizontal overflow on mobile.
8. Selecting a point fetches only that incident timeline and shows structured dossier sections.
9. Satellite/drift overlays respect the same selected temporal cutoff.
10. Humanitarian and Maritime points are both represented in ALL mode.
11. Alarm Phone ingestion health is checked during rollout and missing public posts are explained.
12. Full frontend tests/lint/typecheck/build pass before deploy; public mobile/desktop smoke passes after deploy.
