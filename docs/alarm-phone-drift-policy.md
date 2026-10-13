# Alarm Phone humanitarian drift policy

**Product requirement (2026-10-14):** Every received Alarm Phone distress report is a drift investigation candidate. Do not silently discard it merely because its precise coordinates are missing.

## Evidence and observation states

1. **Reported coordinate:** A location explicitly stated in an authentic Alarm Phone report or image is a **source-reported position**, with preserved tweet/media provenance and timestamp. Authenticity of the source does not prove that the vessel is still at that location, nor does it validate an OCR transcription. Parse, normalize and cross-check the coordinate; store uncertainty and QA method. For active maritime distress, a sufficiently extracted point can seed OpenDrift even if only one OCR engine succeeded, subject to land/sea and disagreement gates.
2. **Text-derived area:** With no defensible point, parse the *entire source report* for named sea areas, departure, route, intended destination, notified authorities, timing, persons and vessel description. Distinguish the role of every place reference. A coast guard's location is **not** the boat's location. The geographic polygon inferred from such clues is a **spatial prior**, not a geolocated observation and not a computed drift trajectory.
3. **Physical macro drift:** To make a probabilistic forecast, seed an ensemble across the spatial prior with explicitly documented spatial weights and time uncertainty. Advance each seed through the **same approved ocean forcing and OpenDrift Leeway engine** as the precise-point workflow, including vessel-class and windage assumptions. Aggregate particles into a time-indexed spatial density, normalize probability mass, show contours with timestamp and coverage, and propagate input/data/model uncertainties. Never replace this procedure with a single centroid simulation or assign calibrated probabilities to an unadvected region polygon.
4. **No usable geographic information:** Keep the incident visible in the candidate queue with `geography_unknown`, invite evidence enrichment, and do not paint an invented location.

## Publication and status

- LIVE: active reported positions and active text-derived macro areas only, with visibly distinct legend and provenance. Resolved, archived and retrospective cases remain in PLAY, without active-looking search overlays.
- PLAY: permanent record of original text/media and extraction methods, all candidate regions, location revisions, model versions, ensembles, timestamps, weather/ocean data references and uncertainty assumptions.
- Audit independently: `source_received`, `media_downloaded`, `location_extracted`, `location_inferred`, `drift_queued`, `drift_computed`, `publication_blocked`, with explicit reasons.
- Report the **candidate count**, **spatial-prior count** and **computed drift count** separately. A source's credibility cannot substitute for positional precision.

## Current implementation boundary

`core.intel.macro_drift.spatial_prior_for_event` and the `macro_search_area` projection only implement *candidate recognition, text/place-role clues, and publication of already generated sea-only spatial priors*. They do **not** run a multi-seed OpenDrift ensemble, compute cargo/other maritime findings, or assign a calibrated probability density. Building that ensemble and its scientific validation is a separate required implementation before claiming the full product requirement is met.
