# SeaCommons Live Fixes Roadmap

> **For agentic workers:** implement one phase at a time. Do not combine unrelated phases in one change. Every phase requires a regression test, a focused commit, and verification on the public Live host before moving on.

**Goal:** make `live.seacommons.org` trustworthy, readable and operationally coherent, with Humanitarian data treated as first-class content rather than as a thin overlay on top of generic AIS/MDA data.

**Baseline:** this plan starts from the 31 Aug 2026 production fixes that added physical DB indexes for `intel_events`, serialized Tesseract execution, corrected civil NGO vs state-authority identity, introduced EasyOCR/Tesseract cross-checking, and added the two-level Humanitarian / Maritime Security signal selector. Do not regress those fixes.

## Global constraints

- Humanitarian distress is the primary product lane. Security/MDA volume must never crowd it out.
- Never fabricate coordinates. Missing, regional or disputed locations must stay visibly uncertain.
- A coordinate marked `disputed` or `needs_review` must never silently trigger public SAR Drift.
- Civil NGO vessels and state SAR authorities are separate public identities even when both are useful responder context internally.
- Preserve the public privacy boundary: no private raw message text, sender identifiers or provider delivery identifiers on Live.
- Do not solve CPU pressure by increasing VM size before fixing unbounded work or inefficient queries.
- Mobile Safari is a first-class acceptance target.
- Do not broadly rewrite `main.jsx` while fixing one concern. Extract focused components only where the phase needs them.
- Existing durable records matter: fixes must work after restart and must not depend only on the 600-item in-memory deque.

## Execution summary

| Phase | Priority | Deliverable |
| --- | --- | --- |
| 0 | P0 | Stable Live latency and bounded OCR work |
| 1 | P0 | Humanitarian cards with visible time and truthful location state |
| 2 | P0 | Complete NGO/SAR fleet surface and correct vessel identity |
| 3 | P0/P1 | Safe geolocation confidence and Drift gating |
| 4 | P1 | Controlled repair of existing Humanitarian records |
| 5 | P1 | Explicit Humanitarian vs Maritime Security compartment mapping |
| 6 | P1 | Source-time, lifecycle and correlation hardening |
| 7 | P1/P2 | Mobile Live hierarchy and viewport cleanup |
| 8 | P2 | Migrations, end-to-end tests and deploy smoke checks |

---

# Phase 0 — Stabilize Live before adding behavior

**Priority:** P0

## 0.1 Verify the `0 SIGNALS` regression is closed

**Observed bug:** fresh public loads intermittently showed `0 SIGNALS` / `Connecting to live feed...` even when the DB contained valid events.

**Known root cause:** production `intel_events` had no physical indexes although SQLAlchemy models declared `index=True`; Live polling therefore performed full-table scans and sometimes exceeded the frontend timeout.

**Files**
- `apps/api/core/db/models.py`
- `apps/api/core/db/session.py`
- `apps/api/core/intel/store.py`
- public Live fetch hook used by `apps/web/src/main.jsx`

**Concrete work**
- Keep `_ensure_indexes()` at startup as the emergency compatibility path.
- Verify production indexes exist for `timestamp_utc`, `type`, `severity`, `source`.
- Run `EXPLAIN ANALYZE` against the actual `persisted_events()` query shapes.
- Add composite indexes only if the plan shows a measurable benefit. Primary candidates: `(source, timestamp_utc)` and `(type, timestamp_utc)`.
- Add lightweight duration logging for `/api/v1/live/signals` and `/api/v1/live/ngo-vessels`.
- The frontend must distinguish `request failed / retrying` from a legitimate empty FeatureCollection.

**Acceptance criteria**
- 20 consecutive public `/api/v1/live/signals` requests complete below the existing 12 s fetch timeout.
- Median response under normal load is below 3 s on the pilot VM.
- A fresh private-browser load never displays `0 SIGNALS` when the endpoint returns events.
- A transient timeout produces a degraded/retrying state, not a false empty state.

**Do not regress:** durable DB-backed events must remain visible even after they fall out of the in-memory deque.

## 0.2 Replace unbounded OCR threads with a bounded queue

**Observed bug:** EasyOCR/Tesseract cross-checking created simultaneous heavy OCR sweeps, saturating the 2-vCPU VM and slowing Live requests.

**Current mitigation:** Tesseract execution is serialized with a lock.

**Remaining bug:** `_schedule_media_ocr()` can still create an unbounded number of waiting daemon threads.

**Files**
- `apps/api/core/intel/twikit_monitor.py`
- `apps/api/core/intel/x_media_utils.py`
- `apps/api/core/intel/map_pin_geolocate.py`

**Concrete work**
- Use one bounded executor/queue for heavy media OCR.
- Default `max_workers=1` on the pilot VM; allow an explicit environment override for larger hosts.
- Bound pending heavy OCR jobs to 16. Reject/defer additional stale jobs instead of growing memory/thread count indefinitely.
- Deduplicate queued work by canonical source-post + media identifier.
- Keep the current EasyOCR/Tesseract locks as defense in depth until the executor path is proven.
- Expose queue depth, dropped/deferred count and last OCR duration in operator diagnostics.

**Tests**
- enqueue an 8-image burst and assert one heavy worker executes at a time;
- duplicate media is processed once;
- queue overflow follows the explicit defer/drop policy;
- Live signal retrieval remains independent of OCR queue completion.

**Suggested commit:** `fix(perf): bound humanitarian media OCR queue`

---

# Phase 1 — Make Humanitarian event cards truthful and readable

**Priority:** P0

## 1.1 Show event time directly in the left Live panel

**Observed bug:** event timestamps exist and are used for sorting, but mobile cards show only title/type/position. The timestamp currently survives mainly in an HTML `title` attribute, which is ineffective on touch devices.

**Files**
- `apps/web/src/components/IntelDashboard.jsx`
- related Live panel CSS

**Concrete work**
- Add visible event time to every Live row.
- Use `source_timestamp_utc` when available; otherwise `timestamp_utc`.
- Never substitute `received_at` as the event time. `received_at` is ingestion diagnostics only.
- Mobile compact format: `20:04 CEST · 8 min ago`.
- Detail format: `31 Aug 2026 · 20:04 CEST`; UTC may be shown secondarily.
- Use one formatter for list, timeline and report views.

**Tests**
- valid ISO timestamp renders visible time;
- missing/invalid timestamp renders `time unavailable`;
- ordering remains newest source event time first.

**Acceptance criteria:** every visible Alarm Phone / distress row exposes its event time without hover or opening the detail panel.

## 1.2 Replace generic `position unavailable` with semantic location state

**Observed bug:** the UI collapses every geometry-null case into the same string even though public metadata already describes why a location is uncertain or absent.

**Files**
- `apps/web/src/components/IntelDashboard.jsx`
- `apps/api/core/live/projection.py` only if an already-safe metadata field is missing from the public projection

**Concrete work:** add one location-presentation helper with these minimum outputs:

- `POSITION · 35.8303, -0.6897 · ±400 m`
- `REGION ONLY · <region>`
- `LOCATION · OCR PROCESSING`
- `LOCATION · OCR NOT EXTRACTED`
- `LOCATION · OCR DISPUTED · REVIEW REQUIRED`
- `LOCATION · UNPOSITIONED`

Use, when available:
- `coordinate_source`
- `coordinate_review_status`
- `location_uncertainty_m`
- `location_precision`
- `ocr_attempted`
- `ocr_engine`
- `region`

Do not expose raw OCR text, internal stack errors or private source material.

**Acceptance criteria:** no public distress card renders the undifferentiated text `position unavailable`.

## 1.3 Use a distress-specific card hierarchy

**Observed bug:** Alarm Phone is rendered through the same vessel-oriented row used by vessel/security episodes, producing rows that read like source/channel telemetry instead of Humanitarian incidents.

**Concrete work:** for `kind=distress` / operational tier, render in this order:

1. source + lifecycle badge (`ALARM PHONE · ACTIVE`),
2. visible event time,
3. public title / short description,
4. reported people count when available,
5. semantic location status,
6. source link.

Use vessel-oriented rows only for actual vessel episodes.

**Acceptance criteria:** a non-vessel Alarm Phone event never falls back to `Unknown vessel` and never looks like an AIS vessel card.

**Suggested commit:** `fix(live): make humanitarian event cards time and location aware`

---

# Phase 2 — Make the NGO / SAR fleet a real Live product surface

**Priority:** P0

## 2.1 Preserve the full registry in frontend state

**Observed bug:** `/api/v1/live/ngo-vessels` returns the full known responder registry, including offline `geometry=null` vessels, but `main.jsx` immediately keeps only positioned features.

**Root cause:** one state object is serving two responsibilities: registry/panel data and map-renderable geometry.

**Files**
- `apps/web/src/main.jsx`
- `apps/api/core/intel/ngo_registry.py`

**Concrete work**
- Store the complete endpoint response as `ngoFleet`.
- Derive `ngoMapFeatures` only at the MapLibre source boundary with `geometry?.coordinates` filtering.
- Never delete an offline registry entry because it cannot currently be plotted.
- Keep endpoint meta (`total_registered`, `civil_ngo_registered`, `state_authority_registered`, `live_ais`, `offline`) intact in frontend state.

**Acceptance criteria:** an offline Ocean Viking / Humanity 1 remains visible in the fleet UI while producing no fake marker.

## 2.2 Add a Humanitarian Fleet surface

Create a focused component, preferably `apps/web/src/components/HumanitarianFleet.jsx`.

The compact public status should expose:

`HUMANITARIAN FLEET`
`14 CIVIL NGO · N LIVE AIS · N OFFLINE`

Each civil NGO row shows:
- vessel name,
- organisation,
- AIS state,
- speed when live,
- last update/last seen when available.

State assets are grouped separately as `STATE SAR`; they are never included in the civil NGO count.

**Interaction boundary**
- The left Live panel carries the compact fleet status/list.
- Selecting a vessel opens the existing right/floating detail surface.
- Do not turn the left incident feed into a full vessel inspector.

## 2.3 Give selected NGO vessels their real identity

**Observed bug:** selecting Mare Jonio currently produces a generic vessel overlay such as `52 · 0 kn · 247536000` even though `org`, `role`, `operator_type` and `vessel_class` are already known.

**Civil NGO detail must show**
- `MARE JONIO`
- `Mediterranea Saving Humans`
- `CIVIL NGO SAR`
- AIS status
- speed
- MMSI
- last update

**State asset detail must show** `STATE SAR AUTHORITY`, never `NGO`.

**Tests**
- a civil NGO is never presented only as a generic AIS vessel;
- a coastguard/state asset is never labelled NGO;
- an offline civil NGO remains listed without map geometry.

**Suggested commit:** `feat(live): expose complete humanitarian SAR fleet`

---

# Phase 3 — Fix Humanitarian geolocation and Drift gating

**Priority:** P0/P1

## 3.1 Block auto-Drift from disputed or weak locations

**Observed risk:** EasyOCR/Tesseract disagreement can be stored as `machine_ocr_disputed_needs_review`, while the approximate coordinate is retained and can supersede a weaker location. That location must not automatically become an authoritative-looking Drift product.

**Files**
- Humanitarian media enrichment path in `apps/api/core/intel/twikit_monitor.py`
- auto-drift trigger path
- `apps/api/core/live/feed.py`
- dedicated tests

**Concrete rule:** add one canonical `is_humanitarian_location_drift_eligible(...)` gate used by every auto-drift entry point.

Auto-Drift is allowed only for:
- trusted reported coordinates;
- cross-engine OCR consensus;
- independently corroborated coordinates;
- explicit operator-approved coordinates.

Auto-Drift is forbidden when any of these is true:
- review status is `disputed` / `needs_review`;
- the location is only region/centroid geometry;
- the point fails operational-region or sea validation;
- `location_uncertainty_m > 1500` unless explicitly operator-approved.

A disputed marker may still be displayed as uncertain context if public policy permits it. The uncertainty must never be converted into an active Drift cone automatically.

**Tests:** disputed OCR retained as a location cue but no drift job; verified coordinate produces drift job; operator approval overrides the uncertainty threshold intentionally.

## 3.2 Replace degree-based OCR agreement with geodesic agreement

**Observed issue:** a tolerance around `0.03°` is kilometre-scale, yet a successful consensus can be presented with uncertainty of only hundreds of metres.

**Concrete rule**
- Compare EasyOCR/Tesseract candidates by haversine/geodesic distance in metres.
- `<= 500 m`: eligible for `machine_ocr_consensus_verified`.
- `> 500 m`: `machine_ocr_disputed_needs_review`.
- Store `ocr_interengine_distance_m`.
- Verified OCR uncertainty is `max(parser_precision_floor_m, 400, ocr_interengine_distance_m)`; never claim precision better than evidence supports.
- Screenshot/map-pin geolocation keeps its own conservative precision floor and must not inherit printed-coordinate precision.

**Acceptance criteria:** OCR readings kilometres apart can never yield `machine_ocr_consensus_verified` or `±400 m`.

## 3.3 Preserve location provenance through upgrades

When an event progresses `region-only -> OCR point -> reviewed/corroborated point`, preserve:
- previous coordinate source,
- new coordinate source,
- review status,
- uncertainty,
- update time.

A simple bounded `location_history` metadata array is sufficient; do not create a new relational subsystem only for this phase.

Keep the existing rule that a newly verified point removes stale `area_geojson` that would otherwise override the point after restart.

**Suggested commit:** `fix(humanitarian): gate drift on verified location quality`

---

# Phase 4 — Repair existing Humanitarian data, not only future events

**Priority:** P1

New ingestion fixes are insufficient while recent persisted Alarm Phone rows remain unpositioned or carry stale metadata.

## 4.1 Add a controlled reprocessing command/job

**Target:** recent Humanitarian/Alarm Phone durable events with one or more of:
- no geometry,
- `ocr_attempted=false`,
- legacy OCR metadata,
- disputed coordinate,
- stale region-only location,
- missing lifecycle/thread enrichment.

**Requirements**
- dry-run is the default;
- explicit `--apply` for writes;
- configurable age window and batch size;
- default batch size 50;
- idempotent updates;
- never rewrite source timestamps;
- never downgrade a higher-ranked verified coordinate;
- bounded OCR queue from Phase 0 is reused;
- report before/after counts.

**Report**
- scanned,
- newly positioned,
- still unpositioned,
- disputed,
- consensus verified,
- lifecycle changed,
- newly drift-eligible,
- skipped because a better coordinate already exists.

## 4.2 Verify durable projection after reprocessing

Repaired rows must project from the database even if absent from the 600-item memory deque.

**Acceptance criteria:** process restart preserves repaired locations and lifecycle state.

**Suggested commit:** `feat(humanitarian): add idempotent recent-event reprocessing`

---

# Phase 5 — Make Humanitarian / Maritime Security classification explicit

**Priority:** P1

## 5.1 Remove complement-based mode classification

**Observed bug:** the current feed effectively behaves as `security if domain in SECURITY_MARITIME_DOMAINS else humanitarian`. Because `piracy` is public but not in the fixed security set, it can fall into Humanitarian.

**Files**
- `apps/api/core/intel/public_policy.py`
- `apps/api/core/live/feed.py`
- frontend category helpers only if required by the backend contract change
- contract tests

**Concrete mapping:** define fixed mode-domain sets and use them everywhere.

`HUMANITARIAN_FEED_DOMAINS`
- `sar`
- `safety`
- `environmental`

`MARITIME_SECURITY_FEED_DOMAINS`
- `piracy`
- `sanctions`
- `grey_zone`
- `iuu_fishing`
- `smuggling`

No domain is assigned by `else humanitarian`. An unknown domain is not silently published into either mode; log/drop it until explicitly mapped.

## 5.2 Keep Drift stricter than public mode visibility

`HUMANITARIAN_DRIFT_DOMAINS` remains exactly `{sar}`. Safety/environmental visibility does not make those events SAR Drift candidates.

**Tests**
- piracy -> security;
- vessel safety incident -> humanitarian context;
- environmental maritime incident -> humanitarian context;
- sanctions/grey-zone/IUU/smuggling -> security;
- unknown domain -> neither mode;
- only SAR passes the Humanitarian Drift domain gate.

**Acceptance criteria:** piracy never contributes to the Humanitarian macro count and never generates a Humanitarian Drift cone.

**Suggested commit:** `fix(live): make maritime mode classification explicit`

---

# Phase 6 — Lifecycle, source time and correlation quality

**Priority:** P1

## 6.1 Make source event time canonical

For public cards and lifecycle:
- `source_timestamp_utc` = source post/report time when known;
- `received_at` = first SeaCommons ingestion time;
- sorting uses source time;
- visible card time uses source time;
- ingestion delay is diagnostics only.

Reprocessing must never replace source time with reprocessing time.

## 6.2 Treat one Alarm Phone thread as one incident

Verify the whole path:
- original distress post opens incident;
- own-account reply/update attaches to the same incident;
- repost/echo does not create another marker;
- explicit rescue/resolution language changes lifecycle;
- ambiguous updates become `needs_review` rather than falsely resolved;
- unresolved items archive after the configured live window.

## 6.3 Correlate nearby SAR vessels without claiming causality

If an NGO/state SAR vessel is geographically near a distress event, expose it only as context:
- distance,
- AIS observation time,
- responder identity.

Never label it `responding`, `rescuing`, `intercepting` or equivalent unless an authoritative source supports that claim.

**Suggested commit:** `fix(humanitarian): harden incident time and lifecycle correlation`

---

# Phase 7 — Mobile Live UI cleanup

**Priority:** P1/P2

## 7.1 Preserve useful map context when panels open

On mobile:
- opening the Live feed must not auto-fit the entire global signal set;
- default/public framing stays within the Mediterranean operating area;
- selecting an event or fleet vessel may intentionally focus the map;
- closing/reopening panels preserves the previous useful camera state.

## 7.2 Keep critical Humanitarian fields above the fold

Small-screen row priority:
1. status/source,
2. event time,
3. short title,
4. location state,
5. people count / verification where available.

Move secondary channel jargon and low-value metadata into the detail panel.

## 7.3 Validate mobile control overlap

Test Safari/iPhone CSS widths 390 px, 402 px and 430 px:
- Live toggle,
- layer control,
- SAR reopen button,
- selected vessel overlay,
- left Live panel,
- right/floating detail panel.

No critical control may obscure another.

**Suggested commit:** `fix(web): tighten mobile public Live hierarchy`

---

# Phase 8 — Production hardening and migration discipline

**Priority:** P2

## 8.1 Introduce real DB migrations

Runtime `_ensure_indexes()` is an emergency compatibility fix, not a long-term schema-management strategy.

Introduce Alembic before the next non-additive production schema change. The initial migration must baseline the existing production schema without recreating tables or dropping data.

## 8.2 Add end-to-end public Live contract tests

Minimum scenarios:
1. active Alarm Phone distress with verified point;
2. Alarm Phone distress with no coordinates;
3. OCR disputed location;
4. resolved Alarm Phone thread;
5. civil NGO with live AIS;
6. civil NGO offline in registry;
7. state SAR vessel;
8. Maritime Security AIS anomaly;
9. piracy-domain event;
10. durable Humanitarian event outside the memory deque after restart.

Assert backend projection and frontend-visible semantics where practical.

## 8.3 Add deployment smoke checks

After each deployment verify:
- `/api/v1/live/signals?mode=all` returns a valid contract;
- `/api/v1/live/ngo-vessels` returns registry metadata;
- public page does not render zero when the endpoint is non-zero;
- a known live NGO vessel is identified as a civil NGO when present;
- an offline NGO remains in the fleet list;
- a geometry-null distress renders a semantic location state;
- timestamp is visible on mobile;
- disputed OCR never exposes an active auto-Drift cone;
- piracy is in Maritime Security, not Humanitarian.

**Suggested commit:** `test(live): add public humanitarian smoke coverage`

---

# Recommended execution order

Do not execute all phases in one agent pass.

1. **Phase 0** — performance and bounded workload.
2. **Phase 1** — timestamp, location semantics and distress card.
3. **Phase 2** — complete NGO/SAR fleet state and selected-vessel identity.
4. **Phase 3** — OCR precision and Drift safety gate.
5. **Phase 4** — repair existing data only after the new location rules are stable.
6. **Phase 5** — explicit Humanitarian/Security compartment mapping.
7. **Phase 6** — lifecycle/time/correlation hardening.
8. **Phase 7** — mobile polish after information architecture is stable.
9. **Phase 8** — migrations, E2E and deploy hardening.

# Commit discipline

Each phase ends with its own verification checkpoint. Never submit one large `fix live` commit.

Recommended commit sequence:
- `fix(perf): bound humanitarian media OCR queue`
- `fix(live): make humanitarian event cards time and location aware`
- `feat(live): expose complete humanitarian SAR fleet`
- `fix(humanitarian): gate drift on verified location quality`
- `feat(humanitarian): add idempotent recent-event reprocessing`
- `fix(live): make maritime mode classification explicit`
- `fix(humanitarian): harden incident time and lifecycle correlation`
- `fix(web): tighten mobile public Live hierarchy`
- `test(live): add public humanitarian smoke coverage`

# Definition of done

The roadmap is complete only when a fresh mobile user can open `live.seacommons.org` and answer all of these from the interface without knowing SeaCommons internals:

- What happened?
- When did it happen?
- Where is it, or why is the position uncertain?
- Is the incident active, resolved, under review or archived?
- Which source reported it?
- Is a displayed vessel a civil NGO, a state SAR authority or a generic AIS vessel?
- Which NGO vessels are part of the monitored fleet even when currently offline?
- Which information is observed/reported and which is modelled?

If any answer requires hidden hover text, guessing from marker colour, or treating a model output as observed fact, the corresponding phase is not done.