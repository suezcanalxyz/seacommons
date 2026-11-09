# PLAY mobile map visual regression — 2026-11-09

Related: #431, #439, #438, #440. Status: **observed visual defect; engineering diagnosis pending**.

## Evidence and research question
The user-provided mobile screenshot shows 3,667 ARCHIVE entries, overlapping cyan triangular markers, thick dark halos and red/blue circles at a Europe–Mediterranean map scale. A screenshot alone cannot establish duplicate records, wrong ship headings or source-data corruption.

**Question:** can zoom-aware aggregation make the historical map legible without dropping or misrepresenting a single underlying observation, and while keeping maritime-security incidents distinct from humanitarian distress?

**Tradecraft:** preserve source observation versus inference, source lineage, timestamp and positional uncertainty; map clustering is a view transformation, never a reduction in forensic evidence.

## Baseline and first diagnostic experiment
Locate the existing PLAY map marker source, layer styling, zoom state and click handlers. For one fixed archived day, log aggregate totals by unique observation ID, vessel identity, event timestamp and rendered feature at three viewport/zoom presets (continental, Mediterranean, vessel detail), on mobile and desktop. Compare rendered feature counts with source counts. Avoid logging private coordinates or vessel identifiers from protected humanitarian records.

Record whether dense triangles are distinct historical observations, multiple vessels, duplicate ingestion records or styling artifacts. Preserve original IDs and source timestamps.

## Acceptance contract for implementation
1. Use existing map library's zoom-dependent clustering/decluttering facilities, with no new authoritative data store or lossy deduplication. Every cluster expands or provides a drilldown to the exact original observations.
2. Remove oversized black marker shadows; use accessible contrast and distinguish vessel AIS, reported maritime incident, analyst-verified attack and humanitarian incident. Do not label an attack without review. Estimated drift is visually distinct from observed position.
3. A date-specific PLAY filter scopes the map and timeline to that day; ALL restores all dates. Category filters preserve the underlying dataset.
4. Keep heading-oriented vessel glyphs only when validated heading/COG exists; no assumed heading from missing values.
5. Screenshot comparison and browser tests at three zoom presets on mobile and desktop; verify cluster expansion, original feature selection, counts, filters, and no private coordinate leakage.
6. Measure before/after visible overlap count, feature-selection success, rendering latency and browser console errors. Do not fabricate baseline values.

## Release and rollback
**Risk:** GREEN only for isolated reversible presentation changes with exact-HEAD CI, browser E2E, privacy checks and live smoke. Incident publication or privacy-policy changes are AMBER and need approval. Restore previous style/feature flag on regression. Log exact commit, URL, screenshot evidence and smoke result. No deployment is asserted by this document.

## Parallel incident/attack track
#440 must evaluate independent corroboration and hard negatives (AIS outages, copied stories, wrong vessel, delayed footage) before any security-event claims. Keep humanitarian distress in a separate taxonomy. P0 #335/#336/#367 continue in parallel; no AIS retention before PostgreSQL + S3-compatible restore proof.

## Research sources and limits
- MapLibre GL JS documentation, https://maplibre.org/maplibre-gl-js/docs/ — implementation reference for GeoJSON clustering, style layers and feature interaction; open-source documentation, actual installed version and API support must be checked before adoption. Decision: **PILOT**.
- Mapbox Supercluster, https://github.com/mapbox/supercluster — spatial point aggregation approach, ISC license; evaluate only if not already included by existing map stack; cluster IDs are view artifacts, not evidence identifiers. Decision: **EVALUATE**, avoid redundant dependency.
- OGC API Features standard, https://www.ogc.org/standard/ogcapi-features/ — interoperability reference for feature identity and query semantics; applicability to existing canonical storage must be checked. Decision: **REFERENCE**, not a migration.
Research accessed 2026-11-09; provider terms and current installed versions require verification. This is a test specification, not a completed experiment.
