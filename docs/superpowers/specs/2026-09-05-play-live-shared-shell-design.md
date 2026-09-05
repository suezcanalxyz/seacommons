# Play / Live Shared Shell Design

## Goal

Make `play.seacommons.org` use the same public UI system as `live.seacommons.org`, while preserving Play's archive/timeline semantics and fixing the currently blank Play map.

The visual target is not "similar". Play must reuse the same shell primitives, spacing, typography, panel treatment, map controls, mobile behavior, vessel symbology, and detail-panel language as Live.

## Public-surface contract

Live remains the rolling operational surface for the last 24 hours. Play remains the historical/temporal reconstruction surface.

Only data semantics differ. The public shell and interaction grammar are shared.

Live continues to expose real counters while transporting a bounded map payload. Play exposes the full archive total while loading map features progressively.
## Shared shell

Create reusable public-shell primitives instead of maintaining independent Live and Play visual systems.

Shared primitives must cover: top/header treatment, left rail/panel frame, map-stage frame, glass panel surface, counter cards, filter chips, close/minimize controls, dossier sheet, loading/error states, and responsive breakpoints.

Play may compose different controls inside those primitives, but it must not maintain a separate typography, border, background, spacing, or panel language.

Desktop Play uses the same dark left rail and dominant map canvas as Live. The current white archive list is removed.

Mobile Play uses the same `map-top + panel-bottom` pattern as Live when a case is selected. The archive/filter controls collapse into the same drawer/sheet language rather than occupying a permanent narrow column.
## Play map behavior

Play opens in `ALL` mode with a visible satellite basemap and archive points immediately. The default basemap is global VIIRS true-colour satellite imagery. OSM remains underneath only as a fail-safe fallback so a missing satellite tile can never leave the canvas blank. The map must never depend on a selected incident before it renders.

The first archive page is rendered as soon as it arrives; later pages merge progressively in the background. A loading state may overlay the map but must not replace or hide the basemap.

Map initialization must set its GeoJSON source only after the MapLibre style is loaded, and every later incident-page update must update that source safely whether it arrives before or after `load`.

The OSM raster basemap is the guaranteed fallback. Sentinel/VIIRS evidence is an overlay, never the only visible map source. Provider failure must leave the basemap and archive points usable.

After first data render, the map fits the visible archive extent once, with bounded padding. Subsequent pagination must not repeatedly recenter the user.
## Play controls and timeline

Play starts at the rightmost global timeline state, `ALL`.

The shared rail exposes Play-specific filters: `ALL`, `HUMANITARIAN`, `MARITIME`, `CORRELATED`, and `SATELLITE`. These controls use the same chips/buttons as Live.

Moving the bottom timeline away from `ALL` activates temporal mode and filters both visible incidents and selected-case evidence to what was knowable at the chosen cutoff.

Returning the control fully right restores `ALL` without resetting the user's map viewport unless the user explicitly requests a reset.

Selecting an incident opens the shared dossier shell. Play extends the dossier with historical timeline, drift, satellite observations, correlations, and evidence/provenance without changing the base panel layout.
## Vessel and incident symbology

A vessel identity is always rendered as the shared heading-oriented triangle used by Live, regardless of speed or stationary state.

Normal vessels use the neutral vessel accent. Civil NGO/SAR vessels are the only vessel class with a distinct core color.

Anomaly, sanctions, spoofing, safety, or lifecycle meaning must not recolor the vessel core. Those meanings belong in rings, overlays, tracks, labels, or the dossier.

Non-vessel incidents remain incident markers. A humanitarian distress point without an identified vessel must not be converted into a ship triangle.

Play must use the same vessel marker helper/symbol definition as Live rather than maintaining its own vessel identity rendering.
## Attribution and public chrome

The persistent MapLibre attribution control is hidden on the public Live and Play surfaces.

Required provider attribution remains in source/style configuration and project documentation; the public map does not show a permanent attribution box over the operational canvas.

Operator/internal surfaces may keep explicit attribution controls.

## Visual verification

The implementation is not complete based on unit tests alone. Before PR merge, capture fresh headless-browser screenshots of the candidate build at desktop and mobile sizes for both Live and Play.

Minimum screenshots: Play desktop ALL, Play desktop selected case, Play mobile ALL, Play mobile selected case, Live desktop, Live mobile selected case.

Visual acceptance: basemap visible; archive/vessel markers visible; no white Play archive rail; shared Live/Play typography and glass panels; no persistent attribution box; no clipped mobile report; no blank map stage.
## Testing and rollout gates

TDD is required for the Play map initialization/data race, shared-shell contract, public attribution removal, and vessel-symbol reuse.

Required local gates before PR: `npm run lint`, TypeScript, all frontend suites, unified production build, `git diff --check`, and candidate screenshot capture.

After local verification, open a PR and require Full CI + CodeQL green with no unresolved review threads. Deploy only after merge.

After Vercel propagation, verify the actual public asset hashes and capture public Live/Play screenshots again. If public visual smoke differs from the candidate screenshots, rollback or fix before calling the tranche complete.

Backend services are not restarted for frontend-only changes unless the implementation discovers and changes an API contract.