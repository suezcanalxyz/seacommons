# Current work — humanitarian + visualization architecture

> **Branch:** `fix/humanitarian-category-drift`
> **Base:** `c0f526877afd03c3d1d55de70b0045ac04ba5ea5` (verified HEAD at start)
> **Status:** implemented, full backend + web + edge suites green, build green.
>   Not yet deployed — see "Deployment" below.

## The product invariant

SeaCommons **classifies**; it does **not score**.

| Axis | Determined by | Never by |
| --- | --- | --- |
| Visual identity / colour | **semantic CATEGORY** | severity, OCR confidence, lifecycle |
| Temporal / status presentation | **LIFECYCLE** (outline, opacity, badge) | — |
| Confidence / uncertainty | **EVIDENCE QUALITY** (coordinate source + review status + uncertainty) | — |
| Whether drift modelling is allowed | **DRIFT ELIGIBILITY** (a real maritime point, not disputed, in region, at sea, under the uncertainty ceiling) | — |

`severity` (`low` / `medium` / `high` / `critical`) does none of these. It is a
DB-compatibility column only (Stage 1 — see "Severity decommission").

### Alarm Phone rules (authoritative)

| Situation | Public Live behaviour |
| --- | --- |
| Alarm Phone category | **red** (`humanitarian_alarm_phone`), in every lifecycle state, for the maritime point, the land point, the region area, the drift origin and the drift trajectory/cone. |
| Maritime specific point (OCR text / consensus / single engine / pin) | red point + preserved evidence/uncertainty + **automatic drift** computed, persisted, exposed on the Live API and rendered (trajectory + cone + current estimate). Machine OCR is **not** "verified" just because drift is allowed. |
| Land specific point (`humanitarian_case_type = land_humanitarian`) | red point at the reported coordinate, classified land humanitarian, evidence/lifecycle preserved, **no maritime drift**. Land is a visibility condition, not a deletion. |
| Region only | red search area/polygon, no fabricated point, **no drift**. Once OCR extracts a real point it replaces the stale area as the primary geometry. |
| Resolved / archived | still **red**, still identifiable as Alarm Phone; lifecycle shown through opacity + a solid (non-dashed) outline + a badge — never green. The drift cone is withheld (the search is over); `needs_review` keeps its cone (still an open case). |

## What was broken (production trace, read-only)

### 1. Operational Alarm Phone drift never reached public Live — CONFIRMED

`GET /api/v1/live/drifts` returned `{"features": [], "drifts": 0}` although
`drift_results` holds completed OpenDrift runs for the current Alarm Phone
maritime incidents.

* **Backend:** `core.live.feed.public_drift_collection` gated on
  `state == "active"`. Real Alarm Phone incidents sit in `needs_review` (a
  human still has to confirm the outcome) or `resolved`, never literal
  `active`. Fixed: withhold the cone only for `resolved` / `archived`; require
  `is_auto_drift_eligible()` so a stale region-only `drift_result` row can
  never paint a fabricated trajectory.
* **Frontend:** `main.jsx` did `setIntelDrifts({features: []}); return;` on the
  public Live host and ran a **second, competing** in-browser OpenDrift model
  per Alarm Phone incident. Removed the browser model from the operational
  path; public Live now polls `/api/v1/live/drifts` (the persisted result).
  Browser drift remains only as the explicitly user-triggered simulation.
* **Frontend:** `mergeLiveDrifts` also dropped every non-`active` incident's
  drift — fixed to match the backend (`resolved` / `archived` only).

Production evidence after the fix (read-only, new code against the prod DB):

```
event_id | lat | lon | loc_status | coord_src | review | lifecycle | land/sea | eligible | drift_row | proj_live | map_pt
b880275d | 33.68427 | 24.87162 | positioned | media_ocr_text | machine_ocr_unverified | needs_review | SEA  | Y            | completed | Y | Y
165c9662 | 34.874   | 19.93953 | positioned | media_ocr_text | machine_ocr_unverified | needs_review | SEA  | Y            | completed | Y | Y
4ca87604 | 37.759   | 26.970   | region_only| region_area    | not_applicable         | needs_review | SEA  | N (region)   | completed | - | Y (area)
aa91d1a0 | 41.55253 | 26.52697 | withheld   | media_ocr_text | machine_ocr_unverified | active/aged  | LAND | N (land)     | computing | - | Y (red land point)
49f8580d | 35.831   | -0.687   | region_only| region_area    | not_applicable         | needs_review | SEA  | N (region)   | -         | - | Y (area)
136aaf0e | 37.309   | 27.164   | positioned | media_ocr_text | machine_ocr_unverified | resolved     | SEA  | N (resolved) | completed | - | - (out of Live window)
```

Every currently-eligible Alarm Phone maritime point (`b880275d`, `165c9662`)
now has its persisted drift projected to `/api/v1/live/drifts` and rendered.

### 2. Land Alarm Phone incidents disappeared from the map — CONFIRMED

`public_geometry_and_precision` dropped any coordinate still on land after the
sea-snap, so `intel:aa91d1a0` (Thrace land-border case) had a card but no map
point. Fixed: a `land_humanitarian` case is projected at its reported
coordinate (`approximate` precision). Maritime drift stays blocked by the
eligibility gate.

### 3. Severity / risk-rating drove colour and UI — CONFIRMED

* `main.jsx` `LIFECYCLE_*` map expressions coloured distress markers green
  (resolved) / amber (needs_review) / grey (archived) and used
  `intel_severity` on the drift cone/line/point layers.
* `classifyEventVisual` fell back to `severity === 'medium'` →
  `needs_review` and `['critical','high']` → `navigation_casualty`.
* `ConePanel.jsx` presented `OBLIGATION_COLOR` / `RISK_COLOR` maps and a
  `Risk level: HIGH` row.
* `core.live.projection` gated context-signal publication on
  `(severity or "low") == "low"`.

All replaced with the category taxonomy (below). Colour now derives only from
`visual_category`; lifecycle drives opacity + outline dash; the panel shows
measured quantities and a semantic `Category` row.

### 4. Manual simulation layers were unmanaged — CONFIRMED

The `sar-case-*` layers were in no `LAYER_GROUPS` entry, so they could not be
toggled and fell outside `PUBLIC_LIVE_LAYER_GROUPS`. New `simulation` layer
group (added to the public allow-list); `enrichCaseGeo` tags every simulation
feature `trajectory_kind: user_simulation` / `auto_drift: false` so it stays
distinguishable from a persisted operational drift while both render.

## The canonical category contract

`apps/api/core/domain/visual_category.py` — one taxonomy, imported by
`core.live.projection`, `core.live.feed`, `core.live_edge_publisher`,
`core.intel.query_service` and `core.scheduler`. Mirrored value-for-value by
`apps/web/src/features/intel/categories.js`.

* `visual_category`, `visual_color`, `category_label` on every public signal
  feature and every drift feature (`origin_category` too on drift).
* Colour is a pure function of category. `classify_visual_category` never reads
  `severity` / `intel_severity` / OCR confidence / lifecycle.
* Frontend maps category → presentation and trusts the backend
  `visual_category` when present; it never infers category from severity.
* Carried across the Cloudflare edge transport (publisher emits it,
  `normalizeEvent` passes properties through verbatim, `edgeEventToFeature`
  keeps it).

### Categories

`humanitarian_alarm_phone` (red), `civil_sar`, `state_sar`, `distress` (red),
`navigation_casualty`, `spoofing`, `ais_gap`, `loitering`, `rendezvous`,
`sanctions`, `infrastructure`, `identity`, `piracy`, `environmental`,
`news`, `social`, `ngo_activity`, `hazard`, `iom`, `context` (neutral).

### Vessel-marker precedence (deterministic, semantic — not numeric risk)

`classifyEventVisual` resolves a multi-signal vessel episode in this fixed
order: Alarm Phone → explicit backend `visual_category` → spoofing → AIS gap
→ loitering → rendezvous → sanctions → infrastructure → identity →
navigation casualty → piracy → environmental → humanitarian distress →
`context` (neutral `#8bf0c5`). A normal AIS vessel with no anomaly evidence
stays neutral.

## Severity decommission (two stages)

**Stage 1 (this branch): the Live product no longer uses `severity`.**

Audit of every backend `severity` / `risk_level` occurrence:

| Location | Class | Disposition |
| --- | --- | --- |
| `core/live/projection.py` context filter | **A — legacy product severity** | removed — now category/corroboration based |
| `core/live/projection.py` `_public_drift_feature` `intel_severity` | **A** | removed — category fields |
| `core/live/feed.py` `_public_drift_feature(severity=...)` | **A** | removed |
| `core/intel/query_service.py` drift `intel_severity` | **A** | removed — category fields |
| `core/live_edge_publisher.py` `severity` in edge properties | **A / compat** | kept as passthrough (Stage 2), category added alongside; no consumer keys off it |
| `core/scheduler.py` drift WS push `severity` | **A** | removed — category fields |
| `core/domain/live_contracts.py` `LiveSignalProperties.severity` | **compat contract field** | kept (Stage 2) — no product decision reads it |
| `intel_events.severity` DB column | **compat column** | kept (Stage 2) |
| `core/intel/store.py:101` `iom_incident and severity in (critical, high)` → operational tier | **A (internal)** | Stage 2 — iom is excluded from auto-drift and public Live already; low blast radius |
| `core/intel/news_monitor.py:261` `type = distress if severity in {critical, high}` | **A (internal, ingestion)** | Stage 2 |
| `core/scheduler.py:65`, `core/intel/ais_spike_detector.py:450`, `core/intel/fusion.py:394` | **A/D (internal alerting / dedup thresholds)** | Stage 2 |
| `core/zones/classifier.py` `risk_level` | **C — physical/scientific** derivation from Beaufort/survival hours | kept internally; no longer surfaced as a headline rating in `ConePanel` |
| `core/api/routes/alerts.py` `risk_level` (simulation input) | **D — user scenario assumption** for a what-if simulation | kept; candidate for a rename |
| `apps/web` simulation `risk_level` selector (`ScenarioModal`, `contracts.js`) | **D** | kept — simulation scenario assumption, not a rating on real intelligence |

**Stage 2 (follow-up, needs its own dependency audit + Alembic migration):**
decouple the remaining internal ingestion/alerting thresholds, then remove
`LiveSignalProperties.severity` and drop `intel_events.severity` via a
reversible migration once every reader/writer has migrated. Do **not** drop
the column before that proof.

## Humanitarian frontend acceptance test

| Case | Expected | Status |
| --- | --- | --- |
| A — Alarm Phone at sea with OCR point | one red point, correct coord, uncertainty, drift trajectory + cone/positions, event card, no duplicate regional marker | **met** (`b880275d`, `165c9662`) |
| B — Alarm Phone land event | red point on land, humanitarian classification, no drift | **met** (`aa91d1a0`) |
| C — Alarm Phone region only | red approximate area, no fabricated point, no drift | **met** (`4ca87604`, `49f8580d`) |
| D — resolved Alarm Phone | identifiable as Alarm Phone / red; lifecycle shown separately | **partial** — styling met (red + badge, never green). Whether a resolved Alarm Phone stays *on the public map* is governed by the pre-existing `lifecycle.is_within_live_window` invariant ("resolved leaves Live immediately", `test_live_resolved_visibility`). Flipping that is a separate product decision — **needs operator confirmation** (see Open questions). |
| E — manual simulation | compute drift → visible on map → cone opens in panel | **met** — `simulation` layer group + provenance tag; renders on console and demo |

## Open questions for the operator

1. **Resolved Alarm Phone visibility on public Live.** Case D implies a
   resolved Alarm Phone stays visible (red, marked resolved). The current
   tested invariant removes it from Live immediately. Which wins? If it should
   stay, `lifecycle.is_within_live_window` and `test_live_resolved_visibility`
   need to change.
2. **Stuck `drift_results` row.** `intel:aa91d1a0` (land case) has a
   `status = computing` row since 2026-08-31, from before the eligibility gate
   covered `withheld_from_maritime_map`. It is not projected. Cleaning it is a
   production DB row mutation — left for operator approval.
3. **Land coordinate privacy.** Land Alarm Phone points are now plotted at
   their reported coordinate (±uncertainty). Confirm this is acceptable for
   border/detention cases, or gate it behind a coarser precision.

## Deployment (STOP — operator runs these)

Nothing here restarts a service, mutates a DB row, deploys edge infra or
changes a secret. To ship the branch:

```bash
# 1. review + merge
cd /home/ubuntu/seacommons
git checkout main && git merge --ff-only fix/humanitarian-category-drift    # or open a PR

# 2. backend (API + worker + edge publisher share the code)
sudo systemctl restart seacommons-api.service
sudo systemctl restart seacommons-worker.service
sudo systemctl restart seacommons-live-edge-publisher.service
curl -s http://127.0.0.1:8100/health
curl -s 'http://127.0.0.1:8100/api/v1/live/drifts' | python3 -m json.tool | head   # expect drifts >= 2

# 3. frontend (build already verified green on the branch)
cd apps/web && npm ci && npm run build
#   deploy dist/ via the existing web deploy path (Vercel / static host)

# 4. edge worker — only if apps/edge changed functionally (it did not; test-only)
#   cd apps/edge && npx wrangler deploy      # operator decision
```

No Alembic migration in this branch (Stage 1 is code-only).
