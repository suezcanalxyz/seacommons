# OSINT Evidence Pipeline v1 — Design

Date: 2026-09-06
Status: approved for implementation
Scope: maritime intelligence fusion and evidence semantics

## Problem

SeaCommons currently promotes several derived maritime signals too aggressively. A concrete production example is the Malta fast ferry YOUR WISDOM: one AIS-derived infrastructure-proximity signal plus an AIS gap on the same vessel can be treated as corroboration, while the emitted `correlated_alert` is always labelled `multi_source_corroborated` even when all contributing evidence comes from one AIS lineage.

That is analytically incorrect. Multiple detectors over one sensor lineage are multiple indicators, not independent sources.

## Goal

Make the first OSINT pipeline correction evidence-first and source-aware without redesigning the entire product in one PR.

The v1 invariant is:

```text
observation != corroboration
multiple detectors != multiple independent sources
single-source multi-indicator evidence may justify an internal episode
but may not claim multi-source corroboration or auto-open an intelligence case
```

Review v0 remains deferred until this evidence layer is corrected.
## Source lineage

Each fusion signal must expose enough lineage to answer whether two observations are independent:

```text
source_name
source_family
independence_group
sensor_family
parent_event_ids
```

For v1, lineage is derived from existing `source_catalog` where possible and from event metadata for internal producers. Unknown lineage is conservative: it is never counted as independent corroboration.

`AISStream`, MDA detectors derived from AISStream, and SeaCommons AIS-derived transforms belong to the same AIS independence lineage unless an event explicitly proves another independent provider.

## Verification vocabulary

Fusion output uses three distinct verification states:

- `single_source_observed`: one observation/source lineage;
- `single_source_multi_indicator`: two or more materially distinct indicators sharing one independence group;
- `multi_source_corroborated`: at least two distinct independence groups support the same hypothesis.

`multi_source_corroborated` must never be inferred from event count or detector count alone.

Existing public vocabulary may retain older enum values for compatibility, but emitted fusion metadata must use the correct state.
## Fusion and case gating

The first PR changes semantics, not detector coverage.

For AIS-derived grey-zone rules:

- `infra_proximity` remains a neutral contextual observation;
- `AIS gap + infra proximity`, `gap + loiter`, or similar combinations from one AIS lineage may emit an internal `single_source_multi_indicator` episode;
- those combinations do not auto-open a `subsea_infrastructure`, sanctions, or grey-zone intelligence case;
- case opening requires either a truly independent supporting lineage or an already high-specificity evidence producer such as a real sanctions/identity-list match;
- proximity alone is never evidence of interference.

The same independence rule applies to spoofing: two AIS anomalies on the same stream can form a multi-indicator anomaly episode, but they are not `multi_source_corroborated`.

Existing SAR triangulation may keep `multi_source_corroborated` only when its contributing channels are genuinely independent according to their lineage.

## Known-service context

Known service-vessel context is introduced first as a conservative negative regression contract, not as a broad suppress-list.

The YOUR WISDOM fixture represents:

```text
name: YOUR WISDOM
MMSI: 229113000
IMO: 9848388
role: high-speed passenger ferry
operational context: Malta/Gozo scheduled service
observed indicators: AIS gap + infrastructure proximity
independent corroboration: none
expected intelligence case: none
```

Vessel class never globally disables anomaly detection. The fixture proves only that ordinary service context plus same-lineage AIS indicators cannot be promoted to a corroborated intelligence allegation.
## Output contract

Every fused alert/episode must expose:

```text
contributing_event_ids
contributing_sources
contributing_independence_groups
verification_status
evidence_count
independent_source_count
```

The human-readable explanation must agree with those fields. A record with one independence group may not say “multiple independent sources agree”.

## Non-goals

This PR does not yet build the full VesselProfile database, route-learning baseline, PostGIS migration, satellite cross-cue orchestration, or analyst Review UI. It does not change Humanitarian privacy, Live/Play vessel markers, Drift ownership, or Safety/Humanitarian routing.

Those become later packets:

1. Vessel Context + behavioural baseline;
2. Observation → Episode → Hypothesis objects;
3. Review v0 on top of the corrected evidence model.

## Exit criteria

- same-lineage AIS indicators never produce `multi_source_corroborated`;
- same-lineage grey-zone indicators cannot auto-open an intelligence case;
- genuinely independent sources still can corroborate;
- YOUR WISDOM regression stays observation/episode level with no intelligence case;
- existing SAR, Safety, Humanitarian, Live/Play and vessel UI regressions remain green;
- production wording never claims more source independence than the evidence supports.