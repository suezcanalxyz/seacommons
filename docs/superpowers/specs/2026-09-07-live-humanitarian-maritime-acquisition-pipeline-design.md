# Live Humanitarian/Maritime + Unified Acquisition Pipeline Design

**Date:** 2026-09-07
**Status:** approved design

## Goal

Make Live expose one canonical SeaCommons data pipeline instead of legacy source buckets or source-specific sub-pipelines. Acquisition adapters such as AIS, remote radio, first-party/NGO feeds, official/public feeds, partner inputs and future connectors all normalize into shared observation/evidence contracts before domain reasoning. Public Live has exactly two semantic compartments: **Humanitarian** and **Maritime**.

## Core architecture

Canonical flow:

`acquisition adapter -> normalized observation -> canonical SourceObservation/evidence -> association/fusion -> assessment/episode -> review/publication gate -> Humanitarian | Maritime public projection`

There is one pipeline. Radio is one acquisition adapter family inside it, exactly like AIS or public/first-party feeds. It must not introduce a parallel truth store, parallel review mechanism, parallel publication surface, or separate public feed category.

## Acquisition families

The unified acquisition layer may include:

- `ais`: AISStream, aiscast/Open Waters and future AIS adapters.
- `radio`: KiwiSDR/OpenWebRX receiver adapters plus explicit decoded DSC/NAVTEX inputs.
- `first_party`: Alarm Phone, NGO first-party sources and equivalent operational/verification sources.
- `public_feed`: official/public datasets, RSS/news/context feeds, IOM/archive/reference sources where allowed.
- `partner`: authenticated partner/webhook inputs.
- `other`: future adapters that still obey the same normalization boundary.

Source family is provenance, not a public compartment.

## Public compartment model

Public Live exposes only:

- `humanitarian`: public-eligible distress/SAR and humanitarian verification output.
- `maritime`: public-eligible Maritime Safety plus reviewed/published Maritime Intelligence/context.
- `all`: union of the two.

`security`, `safety`, `sar`, provider names and transport names remain internal classification/provenance where needed. They are not top-level public UI groupings.

## Maritime Safety semantics

`aground`, `not_under_command`, `restricted_manoeuvrability` and comparable navigational-status events are Maritime Safety observations. They render under **Maritime** with their operational meaning as the primary label. Provenance such as `AIS`, `radio`, `official feed` or `partner` is secondary metadata.

A Safety observation never becomes Humanitarian by fallback. A Maritime Intelligence hypothesis never becomes public merely because it belongs to Maritime.

## Radio adapter semantics

Radio contributes through the same acquisition interface as every other source family:

`receiver adapter -> RadioObservation -> optional explicit decoder output -> canonical structured observation/evidence`

Only descriptors with `enabled=true`, `terms_status=allowed`, and explicit `source_terms` may start. Multiple provider frontends exposing one physical receiver remain one evidence lineage.

Raw RF/audio is never assumed to be DSC/NAVTEX. Structured routing occurs only when a provider/decoder explicitly emits a decoded DSC or NAVTEX message. Ordinary `RadioObservation` remains acquisition/health evidence.

Audio acquisition remains separately gated by `AUDIO_EVIDENCE_ENABLED`; this project does not enable it.

## Unified runtime status

Do not create a radio-only public controller. Extend the existing acquisition/runtime status model so every source family can expose bounded health through one shape, for example:

- adapter/source family
- configured/enabled state
- live/degraded/offline state
- last observation time
- bounded public-safe provenance

Radio-specific station/channel/frequency fields may appear only inside a radio adapter's provenance payload. AIS may expose provider/coverage state; public feeds may expose source health; all remain entries in the same acquisition-status collection.

## Public provenance contract

Published items may expose bounded provenance such as:

- `input_modality`: `ais | radio | first_party | public_feed | partner | other`
- `source_label`
- `observed_at`
- public-safe adapter/provider label
- for radio only: `receiver_id`, `station_label`, `channel_kind`, `frequency_hz`

Never expose credentials, frontend URLs, session IDs, raw radio payloads, source-terms text, private messages, raw audio/transcripts, or Humanitarian MMSI/IMO/callsign/tracker dossier fields.

## Live UI

The Live selector becomes:

- `All`
- `Humanitarian`
- `Maritime`

Humanitarian nested categories retain distress/NGO/IOM/etc. Maritime nested categories include Safety, maritime context and reviewed intelligence.

The UI may show a compact **Acquisition** health section for the same pipeline, listing active source families/adapters such as AIS, first-party/public feeds and radio receivers. This is observability/provenance only; it is not another content feed and cannot change publication eligibility.

## API contracts

1. `GET /api/v1/live/signals?...&mode=maritime` returns public Safety + public Maritime Intelligence/context.
2. `mode=security` may remain a temporary compatibility alias to `maritime`, but new UI code uses `maritime` only.
3. `meta.mode_counts` exposes only canonical public counts: `humanitarian`, `maritime`.
4. Add or extend one public-safe acquisition-status endpoint (`GET /api/v1/live/pipeline`) whose schema represents all acquisition families, not just radio.

Example shape:

```json
{
  "generated_at": "...",
  "sources": [
    {"family":"ais","state":"live","label":"AIS"},
    {"family":"first_party","state":"live","label":"First-party feeds"},
    {"family":"radio","state":"live","label":"Radio","receivers":[]}
  ]
}
```

## Evidence integration

All normalized observations enter existing evidence contracts. DSC/NAVTEX evidence may produce canonical `EvidenceReference` objects with modality `radio` and physical receiver lineage. AIS provider multiplicity remains one AIS modality. Derived decoders/transcripts never add independence by themselves.

No acquisition adapter may directly mutate Humanitarian lifecycle, hypothesis state, review state or publication state.

## Rollout

1. Implement Humanitarian/Maritime public contract while acquisition adapter behavior remains unchanged.
2. Introduce the unified acquisition-status contract and adapters for existing AIS/public/first-party sources.
3. Add radio status into that same contract and connect explicit decoded DSC/NAVTEX outputs to existing structured evidence ingestion.
4. Configure a bounded terms-allowed receiver set.
5. Enable structured radio ingestion, then remote receiver acquisition, while keeping audio disabled.
6. Verify one end-to-end acquisition/evidence/publication path per relevant source family without inventing source independence.

## Success criteria

- Public Live has no `PUBLIC FEEDS`, `DIRECT`, `Maritime Security`, or `Radio` top-level content grouping.
- Canonical content grouping is only Humanitarian / Maritime.
- Aground/NUC/restricted manoeuvrability appear under Maritime Safety.
- AIS, radio, first-party/public and partner inputs all use the same acquisition -> observation -> evidence boundary.
- At least one terms-allowed remote receiver can report truthfully through unified acquisition health.
- Decoded DSC/NAVTEX reaches canonical structured evidence and cross-modal references.
- No source adapter directly creates Humanitarian truth, resolves lifecycle or publishes intelligence.
- Humanitarian public privacy remains intact.
- Audio capture remains disabled unless separately authorized.
