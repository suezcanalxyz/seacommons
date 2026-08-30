# Architecture audit — vessel vs. event, humanitarian vs. security

Written against `docs/prompt.md`'s section 14 requirements. Every claim below
is a file:line reference or a live production check made today
(2026-08-30), not an assumption.

## A. Current event flow

```
AISStream (WS)  →  core/vessels/aisstream.py (position hooks)
                →  core/vessels/track_store.py (buffered → VesselTrackDB)
                →  core/intel/vessel_incident_monitor.py   (nav-status → IntelEvent, type=vessel_incident/distress)
                →  core/mda/watch.py  MdaWatch._loop() every MDA_SCAN_INTERVAL_S
                       .scan_rendezvous()    → IntelEvent type=ais_rendezvous
                       .scan_infra_loiter()  → IntelEvent type=ais_anomaly, anomaly_type=cable_proximity|loiter
                       .scan_gaps()          → IntelEvent type=ais_anomaly, anomaly_type=gap|long_gap
                       .scan_identity()      → IntelEvent type=vessel_identity, anomaly_type=sdn_match|identity_anomaly
                       .scan_mmsi_duplicate()→ IntelEvent type=vessel_identity, anomaly_type=mmsi_duplicate
                       .scan_spoofing()      → IntelEvent type=ais_anomaly, anomaly_type=circle_spoof|position_jump|static_spoof
                →  core/intel/store.py intel_store.add() (in-memory deque + DB persist)
                →  core/intel/fusion.py normalize() + rule set → FusedAlert → IntelEvent type=correlated_alert
                →  core/live/projection.py _public_intel_feature()  (public eligibility gate)
                →  core/live/feed.py public_signal_collection()     (GET /api/v1/live/signals)
                →  core/api/routes/mda.py collect_mda_anomalies()   (GET /api/v1/mda/anomalies, /api/v1/live/mda-anomalies — built today, bypasses the projection gate entirely)
                →  frontend main.jsx / IntelDashboard.jsx / MdaPanel.jsx
```

RSS/GDACS/IOM/twikit follow a parallel, separate path (`core/intel/news_monitor.py`,
`gdacs_monitor.py`, `twikit_monitor.py`) into the same `intel_store`, not
touched by this audit.

## B. Current vessel representation — no persistent vessel entity exists

There is no `Vessel` object with a stable identity that events attach to.
What exists instead:
- `core/vessels/registry.py` — in-memory `_cache[mmsi]` of static AIS fields (name, IMO, flag, ship_type). Ephemeral, not queryable as an entity, no sanctions field attached.
- `core/mda/identity.py` `screen(mmsi, imo, name, flag)` — a **stateless function** called fresh every time (from `scan_identity()`, and from `GET /api/v1/mda/vessel/{mmsi}`). It re-derives risk_flags/sanctions on every call against the CSV cache; nothing is written back onto a vessel record.
- Consequence (section 1 of the prompt, confirmed exactly): `scan_identity()` (`core/mda/watch.py:309-353`) treats "this vessel is on a sanctions list" as a **recurring IntelEvent**, re-emitted every 24h (`_recently_emitted(f"ident:{mmsi}", 24*3600)` at line 328) for as long as the vessel keeps appearing in AIS traffic — i.e. forever, for a vessel that transits the Med regularly. This is the exact anti-pattern the prompt describes: a persistent attribute modeled as a repeating event.

## C. Current sanctions flow

`scan_identity()` → `IntelEvent(type="vessel_identity", metadata.anomaly_type="sdn_match")` → picked up by `fusion.py:_rule_identity_fraud` (`core/intel/fusion.py:384-412`) → `FusedAlert(alert_type="sdn_match", domain="sanctions")` → `IntelEvent(type="correlated_alert")`.

Both the raw `vessel_identity` event and the `correlated_alert` wrapper are separate `IntelEvent` rows, separate map points, separate cards — confirmed and partially fixed today (dedup so only the wrapper renders when both exist — `core/api/routes/mda.py:51-73`), but the underlying re-emission-as-event problem (item B) is unfixed: sanctions status is still generated as a stream of events, just deduplicated for *display*, not restructured at the *model* level.

Coordinate handling, also fixed today: `_rule_identity_fraud` used to default to `lat=0.0, lon=0.0` (`fusion.py:403-404`, pre-fix) when no position was known — now `None`, with a display-time backfill from a contributing raw event's position (`core/api/routes/mda.py`).

## D. Current MDA anomaly flow

Six independent scan methods on `MdaWatch` (`core/mda/watch.py`), each with its own cooldown/dedup window (ranging 6h–24h) and its own `IntelEvent` shape. No shared `Signal` schema — every method builds its own `metadata` dict with overlapping-but-inconsistent keys (`anomaly_type` vs. `spoof_reason` vs. `infrastructure`).

## E. Current severity calculation

No unified severity model. Each scan method hardcodes its own rule inline:
- `scan_rendezvous`/`_emit_rendezvous`: `"high" if (tanker or zone or dark) else "medium"` (`watch.py:152`)
- `scan_infra_loiter`: `"high" if hit.kind in ("cable","pipeline") else "medium"` (`watch.py:238`) — always high in practice, since only cable/pipeline hits reach this line (line 231 already filters to only those kinds)
- `scan_gaps`: derived from a `confidence` float combining time-since-last-seen and jamming score (`watch.py:281-282`)
- `scan_identity`: `"high" if serious else "medium"` where `serious = sdn_match` only (`watch.py:336`)
- `_rule_grey_zone` (fusion): `"high" if corroborated else "medium"` (`fusion.py:290`)

None of these currently factor in "is this vessel already flagged" (sanctions/watchlist) the way the prompt's section 8 example describes (gap+STS+sanctioned → HIGH/CRITICAL). Severity and sanctions status are computed in entirely separate code paths that never see each other's output at decision time — `scan_gaps`/`scan_infra_loiter` run before `scan_identity` in the same `scan()` loop (`watch.py:69-77`) and don't consult sanctions state at all.

## F. Current public-domain filtering

`core/intel/public_policy.is_public_domain()` — confirmed live today: of 598 in-memory events, 517 `sanctions` + 77 `grey_zone` (99%) return `False`; only `sar`/`safety` pass. This is why the public `/api/v1/live/signals` ticker shows almost no MDA content while the map (via the new `/api/v1/live/mda-anomalies`, which bypasses this gate entirely) shows hundreds of markers — **two different eligibility rules for the same underlying data, not a mode switch on one rule**, exactly the problem section 3 of the prompt describes.

## G. AIS gap → "distress" misclassification — checked, NOT confirmed

All six `watch.py` emit sites explicitly set `metadata["is_distress"] = False` (verified: `watch.py:172,246,296,353,396,440`). `IntelEvent.tier()` (`core/intel/store.py:92-101`) only returns `"operational"` (which maps to `kind="distress"` in the public projection) when `type=="distress"` or `metadata.is_distress` is truthy. AIS gap/loiter/spoof events therefore do **not** currently render with a distress kind. No fix needed here — flagging as verified-clean rather than silently skipping it.

## H. Origin of "within 0.0 km of X (sts_zone)"

Confirmed, exact:
- `core/mda/reference.py:255-257` `_geom_distance_km()`: `if geom.contains(pt): return 0.0` — a point inside a polygon (STS zone, MPA, etc.) collapses to a bare `0.0`, with no "inside" flag returned to the caller.
- `core/intel/fusion.py:295` `_rule_grey_zone()`: `summary=f"AIS {new.anomaly_type} within {hit['distance_km']:.1f} km of {hit['name']}"` — formats that `0.0` literally, with no inside/outside branch.

## I. Duplicate rendering paths

1. Raw MDA finding + `correlated_alert` wrapper for the same underlying signal — fixed today (`core/api/routes/mda.py:collect_mda_anomalies`), but only in that one endpoint's output, not at the event-creation layer.
2. `/api/v1/live/signals` (strict public gate) vs. `/api/v1/live/mda-anomalies` (no gate, built today) — two live endpoints with different eligibility rules serving overlapping data to two different frontend surfaces (ticker list vs. map layer).

## J. Files/components a real fix touches

- `core/mda/watch.py` — `scan_identity()` (stop emitting a recurring event; call a vessel-enrichment write path instead)
- `core/mda/identity.py` — needs a persistence layer (`sanctioned_vessels` table already exists per its own docstring at `identity.py:10-11`; a per-MMSI *current-state* table is the missing piece, distinct from the bulk sanctions-list cache)
- `core/mda/reference.py` — `_geom_distance_km` needs to also return an `inside: bool`
- `core/intel/fusion.py` — `_rule_grey_zone` summary formatting; `_rule_identity_fraud` (stop producing a fresh alert per re-sighting)
- `core/api/routes/mda.py`, `core/api/routes/live.py` — endpoint-level mode split (prompt section 3)
- `apps/web/src/components/MdaPanel.jsx`, `IntelDashboard.jsx`, `features/intel/mdaCategories.js` — card copy, badges, humanitarian/security switch (partially done today via section headers, not yet a server-filtered mode)

## Problems ranked by impact

1. **Sanctions modeled as a recurring event, not a vessel attribute** (B, C) — the root semantic issue named in the prompt; everything else is a symptom.
2. **Two live endpoints, two eligibility rules, no declared relationship** (F, I.2) — actively confusing right now (map full, ticker empty).
3. **"0.0 km" wording bug** (H) — small fix, concrete, user-visible, zero risk.
4. **Severity never consults sanctions/watchlist state** (E) — real gap, needs B fixed first (no vessel state to consult yet).
5. **Per-scan-method inconsistent metadata shape** (D) — technical debt, lower urgency, no user-visible symptom found today.

## Implementation plan (this session)

Given effort budget, executing **Phase 1** (semantic fixes, zero schema risk) and the
**event-creation half of Phase 2** (stop re-emitting sanctions as an event) now.
Deferring the full mode-switch endpoint unification (Phase 3) and the
per-handle source-health rework (Phase 4) to a follow-up — both are larger,
higher-risk changes that deserve their own focused pass rather than being
rushed alongside everything else done today.

## Phase 3/4 follow-up — completed 2026-08-30

Public Live now has one server-filtered truth: `GET /api/v1/live/signals`
with `mode=humanitarian|security|all`. The selected UI mode drives the REST
query, feed cards, map-layer groups, filters and mode-specific cache. Response
metadata carries separate `humanitarian` and `security` counts, so the header
does not infer the inactive count from the currently rendered list.

`GET /api/v1/live/sources` now distinguishes collector-pipeline health from
target availability. Multi-source collectors publish `configured`,
`reachable` and per-target states; partial X-handle or NGO-RSS failure makes
the source degraded while leaving a functioning pipeline active.

### Legacy disposition

| Legacy path | Classification | Action |
| --- | --- | --- |
| `/api/v1/live/signals` | canonical | KEEP; mode-aware public contract |
| Public consumer of `/api/v1/live/mda-anomalies` | duplicate internal truth | MIGRATE to canonical signals feed |
| `/api/v1/live/mda-anomalies` | unused legacy public endpoint | DELETE; operator `/api/v1/mda/anomalies` remains |
| `mdaAnomalyToFeature()` UI adapter | dead compatibility adapter | DELETE |
| Simultaneous Humanitarian/Security feed sections | superseded presentation | DELETE; replaced by top-level switch |
| Channel-only source status | incomplete health model | MIGRATE to pipeline + per-target availability |
| Vercel “configured = active” fallback | misleading magic fallback | DELETE behavior; report `pending/unknown` |
