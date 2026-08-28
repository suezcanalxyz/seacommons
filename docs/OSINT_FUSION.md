# OSINT cross-source fusion

Status: **v1 implemented** — observer hook, engine, four rules, auto-case bridge,
notification, operator UI. More rules land as new connectors (GFW, OpenSanctions,
gpsjam) arrive.

## Why

Every OSINT stream (Alarm Phone/X, news, Mastodon/Bluesky, GDACS, IOM, AIS spikes,
AIS anomalies, vessel-incident monitor) funnels through `intel_store.add()`, but
only distress events used to drive anything downstream. Non-distress signals
collapsed into one undifferentiated map circle, nothing correlated sources, and
`intel_events` had no path to a case. The fusion engine closes that gap: it turns
independent signals into **correlated alerts** backed by real spatiotemporal +
vessel-identity computation, and every alert opens a case that shows in the UI.

SeaCommons is multi-vertical — migration is one domain among `sanctions`,
`grey_zone`, `safety`, `piracy` (see `docs/COMPARTMENTS.md`); the fusion engine
treats them equally.

## How it works

```
intel_store.add(event)
  └─ _notify_subscribers(event)         # new fan-out hook (mirrors ingestion.router)
       └─ fusion.evaluate(event)        # off-thread, per event
            ├─ normalize(event) -> FusionSignal
            ├─ feed CorrelationEngine   (ais_anomaly only, for physical-sensor fusion)
            └─ for rule in _RULES:
                 alert = rule(signal, event)
                 if alert:
                   _emit(alert):
                     ├─ dedup on cluster_id (core.geo.cluster_key)
                     ├─ intel_store.add( correlated_alert IntelEvent )
                     ├─ open_case_from_alert → case + case_intel_events links
                     │    (dedups against an existing open case for the cluster)
                     └─ notifications.notify_alert  (rate-limited per cluster)
```

`core/geo.py` provides the shared `haversine_km` / `within_km` / `cluster` /
`cluster_key` used here (and by new call sites elsewhere) instead of the old
per-module private haversine copies.

## v1 rules (`core/intel/fusion.py::_RULES`)

| Rule | Trigger | Alert type | Domain | Case |
| --- | --- | --- | --- | --- |
| `_rule_sar_multisource` | `triangulation.evaluate` finds ≥2 independent channels agreeing on a place/time | `sar_corroborated` | `sar` | yes (`distress_sar`) |
| `_rule_spoofing` | two *distinct* AIS anomalies for one MMSI within `FUSION_SPOOFING_WINDOW_S` / `_RADIUS_KM` | `spoofing` | `sanctions` | yes (`sanctions_watch`) |
| `_rule_grey_zone` | an AIS gap/loiter/dark-entry within `FUSION_INFRA_PROXIMITY_KM` of an offshore platform or subsea corridor | `infra_proximity` | `grey_zone` | yes (`subsea_infrastructure`) |
| `_rule_single_source` | a serious AIS vessel casualty (aground / NUC / adrift); or a high/critical GDACS maritime hazard in the AOI | `vessel_casualty` / `natural_hazard` | `safety` | casualty only |

Rules are independent; one raising an exception never stops the others.

## The correlated_alert event

Emitted through `intel_store.add()` like any event, `type="correlated_alert"`,
carrying in metadata: `alert_type`, `maritime_domain`, `confidence`,
`contributing` (event ids), `contributing_sources`, `cluster_id`, and `case_id`
once the case is opened. `maritime_domain == "sar"` sets `is_distress` so it is
operational-tier.

## Case bridge

`case_signals` only ever linked messaging signals (`ingested_signals`). The new
`case_intel_events` table links a case to the OSINT events behind it.
`core/cases/service.py::open_case()` is the single code path the HTTP route and
the fusion engine share (timeline entry + audit record + links + notification).
`GET /api/v1/cases/{id}` returns the resolved `intel_events`.

## Notifications

`core/notifications.py::notify_alert()` formats one line (domain, type,
confidence, position, sources) and calls the existing `telegram()` / `whatsapp()`
(both already no-op when unconfigured). Rate-limited per `cluster_id`
(`FUSION_NOTIFY_COOLDOWN_S`, default 30 min).

## Operator UI

- **Alert rail** (`components/AlertRail.jsx`) — every `correlated_alert`, severity
  then recency sorted, with domain chip, confidence bar, sources, and
  "On map" / "Open case".
- **`intel-fused` map layer** — pulsing ring coloured by domain, always on top.
- **`intel-spike` map layer** — AIS spikes/anomalies, previously excluded from the
  map outright; now a togglable layer group (off by default).
- New critical alert → pulsing `map-banner` + a short Web Audio chime (mute with
  `localStorage['seacommons_alert_mute'] = '1'`).
- Not rendered on the public Live host; `notify_alert` and the public projection
  are unchanged, so `live.seacommons.org` stays realtime-distress only.

## Config

`FUSION_ENABLED` (default true), `FUSION_NOTIFY_COOLDOWN_S`,
`FUSION_SPOOFING_WINDOW_S` / `FUSION_SPOOFING_RADIUS_KM`,
`FUSION_INFRA_PROXIMITY_KM` / `FUSION_GREY_ZONE_WINDOW_S`.

## Tests

`tests/test_fusion.py` (rule-by-rule + dedup + idempotent register),
`tests/test_geo.py`.
