# Live Humanitarian/Maritime + Radio Pipeline Design

**Date:** 2026-09-07
**Status:** approved design

## Goal

Make Live expose the actual evidence pipeline rather than legacy source buckets. The public UI has two semantic compartments only: **Humanitarian** and **Maritime**. Remote radio is not a third feed: configured receivers contribute observations/evidence into the same pipeline, and published output appears in the appropriate compartment only after existing domain gates.

## Current problems

1. Live still carries legacy UI semantics around source/type groupings and `Maritime Security`; Safety observations such as `aground`, `not_under_command`, and `restricted_manoeuvrability` are not presented as first-class Maritime items.
2. `RemoteRadioRuntime` persists `RadioObservation`, but there is no automatic routing from receiver observations into structured DSC/NAVTEX ingestion.
3. Receiver/station/channel health exists only as coarse operator status; the public UI cannot explain which evidence came from which station/channel.
4. Structured radio runtime is disabled-by-default and instantiated independently, so there is no single long-lived radio pipeline controller.
5. The UI must not infer publication eligibility. Humanitarian/Maritime membership and publication decisions stay backend-authoritative.

## Canonical compartment model

Public Live exposes:

- `humanitarian`: distress/SAR and humanitarian verification output that is already public-eligible.
- `maritime`: all public-eligible Maritime Safety plus reviewed/published Maritime Intelligence context.
- `all`: union of the two above.

`security` and `safety` remain internal backend domains where useful, but the public UI groups both under **Maritime**. This is a presentation grouping only; it must not weaken the distinct publication gates for Safety versus Maritime Intelligence.

## Safety semantics

`aground`, `not_under_command`, `restricted_manoeuvrability`, and comparable navigational-status events are Maritime Safety observations. They must be shown under Maritime with their operational meaning as the primary label. Source (`AIS`, `radio`, official feed, etc.) is secondary provenance.

A Safety observation never becomes Humanitarian by fallback. A Maritime Intelligence hypothesis never becomes public merely because it is in the Maritime group.

## Radio as pipeline input

Canonical flow:

`receiver/station -> RadioObservation -> channel classifier/decoder bridge -> DSCObservation | NAVTEXObservation | bounded radio evidence -> SourceObservation persistence -> Safety candidate / context -> cross-modal evidence -> assessment/episode -> review/publication gate -> Humanitarian or Maritime public projection`

Remote radio is therefore infrastructure + provenance, not a public feed category.

### Receiver activation

Only descriptors with `enabled=true`, `terms_status=allowed`, and explicit `source_terms` may start. Physical lineage deduplication remains mandatory. Audio acquisition remains separately gated by `AUDIO_EVIDENCE_ENABLED` and is not enabled by this project.

### Channel routing

A configured receiver channel declares a bounded purpose:

- `dsc`: decoded DSC messages feed `StructuredRadioRuntime.ingest_dsc()`.
- `navtex`: decoded NAVTEX blocks feed `StructuredRadioRuntime.ingest_navtex()`.
- `monitor`: signal/health observations only; no claim extraction.

The bridge must never pretend raw RF/audio is already decoded DSC/NAVTEX. It accepts only provider payloads that explicitly identify a decoded structured message, or a decoder adapter output.

## Runtime controller

Introduce one long-lived `RadioEvidencePipeline` owned by bootstrap. It composes:

- `RemoteRadioRuntime`
- one shared `StructuredRadioRuntime`
- receiver/channel configuration
- observation routing
- bounded per-receiver health and last-observation state

`get_remote_radio_status()` becomes pipeline status rather than a provider-only aggregate.

## Public provenance contract

Published Live items may expose bounded provenance:

- `input_modality`: `ais | radio | public_feed | partner | other`
- `receiver_id` only for public-safe radio lineage
- `station_label` (operator-configured public label, not raw URL)
- `channel_kind`: `dsc | navtex | monitor`
- `frequency_hz`
- `provider`: `kiwisdr | openwebrx | other`
- `observed_at`

Never expose receiver credentials, frontend URLs, session IDs, raw radio payloads, source terms text, private messages, Humanitarian MMSI/IMO/callsign dossier fields, or audio/transcript bodies.

## UI design

The Live sidebar macro selector becomes:

- `All`
- `Humanitarian`
- `Maritime`

Humanitarian nested categories retain distress/NGO/IOM/etc. Maritime nested categories include:

- `Safety` (Aground, Not Under Command, Restricted Manoeuvrability, DSC distress candidate, other safety)
- `Maritime context` (NAVTEX/public maritime context)
- `Reviewed intelligence` (only already-public hypotheses/episodes)

Source is shown as provenance on cards, not as a macro category.

### Pipeline visibility

A compact `Pipeline` status row belongs in the same Live panel, not as a separate Radio feed. It shows acquisition state contributing to the current feed:

- AIS
- Public/first-party feeds
- Radio receivers

For radio it may expand to public-safe receiver rows: station label, provider, connection state, channel/frequency, last observation age. These rows describe data acquisition; clicking/filtering them must not bypass Humanitarian/Maritime grouping or publication policy.

## API contracts

1. `GET /api/v1/live/signals?...&mode=maritime` returns the union of public Safety + public Maritime Intelligence/context.
2. Backward compatibility: `mode=security` may remain accepted temporarily as an alias to `maritime` for existing clients, but new UI code uses `maritime` only.
3. `meta.mode_counts` exposes `humanitarian` and `maritime` as canonical public counts. Optional internal detail may live under `meta.domain_counts`, never required by the UI.
4. Add a public-safe `GET /api/v1/live/pipeline` endpoint returning bounded acquisition status and radio receiver/channel rows. It must not require operator credentials because Live needs it, but it must expose only the allow-listed fields above.

## Cross-modal integration

DSC/NAVTEX persisted observations must become available to existing cross-modal packet construction through their canonical evidence references. Radio-derived evidence never counts as independent merely because multiple frontends expose the same physical receiver. Derived decoder/transcript output does not create an extra independent group.

## Rollout

1. Implement contracts and UI while radio runtime remains disabled.
2. Configure a small receiver allow-list with terms explicitly marked `allowed` and public station labels.
3. Enable `STRUCTURED_RADIO_ENABLED=true` first and verify ingestion with fixture/decoder input.
4. Enable `REMOTE_RADIO_ENABLED=true` with bounded receivers.
5. Keep `AUDIO_EVIDENCE_ENABLED=false`.
6. Verify public `/live/signals?mode=maritime`, `/live/pipeline`, Humanitarian privacy, receiver lineage, and no publication bypass.
7. Roll back by disabling remote/structured radio flags; UI remains functional with acquisition status offline.

## Success criteria

- Live UI has no `PUBLIC FEEDS`, `DIRECT`, or `Maritime Security` primary grouping; canonical grouping is Humanitarian / Maritime.
- Aground/NUC/restricted manoeuvrability appear under Maritime Safety with correct labels.
- At least one terms-allowed remote receiver can be connected and visible in pipeline health with station/channel metadata.
- Decoded DSC/NAVTEX data reaches canonical structured evidence persistence and cross-modal evidence references.
- Radio evidence can contribute to Maritime/Humanitarian assessments only through existing domain rules.
- No radio path directly creates Humanitarian truth, resolves lifecycle, or publishes intelligence.
- Public Humanitarian output remains free of MMSI/IMO/callsign/tracker dossier data.
- Audio capture remains disabled unless separately authorized.
