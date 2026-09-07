# SeaCommons — current agent prompt

Work on `suezcanalxyz/seacommons` from the latest verified branch state. Do not restart completed architecture packets.

## Canonical controller

Read first:

1. `docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md`
2. `docs/current_work.md`
3. `docs/superpowers/plans/2026-09-06-remote-maritime-radio-v1.md`
4. the existing provider/source-observation/runtime patterns referenced by that plan

The master loop controls packet order. Humanitarian Verification v1 is closed for development; do not reopen it unless a regression in the Remote Radio packet proves a boundary defect.

## Current packet

Live Humanitarian/Maritime + Unified Acquisition Pipeline is deployed and awaiting final Tasks 1-8 review. Packets A-G remain closed; do not reopen them except for a demonstrated regression.

Detailed plan: `docs/superpowers/plans/2026-09-07-live-humanitarian-maritime-acquisition-pipeline.md`.
Design: `docs/superpowers/specs/2026-09-07-live-humanitarian-maritime-acquisition-pipeline-design.md`.

Free/Open AIS Fusion v1 is development-complete/shadow-ready. Humanitarian Verification v1 is development-complete/review-ready through `961c436`; release gates were `141` focused tests and `1350` full backend tests plus green static/web/edge/dependency gates. No production AIS cutover or Humanitarian auto-resolution was authorized.

Remote Maritime Radio v1 and DSC + NAVTEX Structured Evidence v1 are closed. Audio Evidence v1 is development-complete/review-ready through `90d08e4`, with bounded metadata-only artifacts, disabled-by-default acquisition policy, migration `0022_audio_artifacts`, and derived-only transcripts. Cross-modal Evidence Fusion v1 is closed. Preserve lineage/modality independence and never let derived evidence become canonical authority.

## Packet boundary

Remote Maritime Radio v1 adds software-only configured receiver identity/capability/health, provider adapters (KiwiSDR/OpenWebRX where terms and automation permit), physical RF lineage, bounded observations, observability, and a disabled-by-default runtime.

Do not add continuous recording, unbounded retention, automatic transcription-driven truth, Humanitarian incident creation, lifecycle resolution, or public allegations. Audio acquisition remains disabled until provider terms/jurisdiction/retention are explicit and allowed.

## Loop after Remote Radio

DSC + NAVTEX structured evidence -> Audio Evidence v1 -> Cross-modal Evidence Fusion v1 -> Review v0/publication controls.

## Non-negotiable invariants

- Source identity != transport adapter != provider/frontend != physical receiver/RF lineage.
- Multiple frontends exposing one physical receiver are one evidence lineage, not independent corroboration.
- Alarm Phone remains the Humanitarian operational-origin authority for now; Humanitarian verification source-role logic is already implemented and must remain intact.
- Observation != incident/episode != assessment/hypothesis != review != public projection.
- Safety/nav/radio status never becomes Humanitarian or Intelligence by fallback.
- Humanitarian public output never exposes MMSI/IMO/callsign/tracker dossier data.
- Derived behaviour, radio decoding, transcription and AI output are context/assistive evidence, never canonical truth alone.
- New adapters fail closed, expose health, preserve provenance/source terms, and normalize before business reasoning.
- Prefer software-only and free/open acquisition; paid providers or SeaCommons-owned hardware are not core requirements.

## Execution loop

For each task: inspect existing code -> write RED test -> run and observe expected failure -> implement minimum change -> run GREEN + focused regressions -> static checks -> commit one semantic unit -> update execution record.

For each packet: run full backend/static and any crossed web/edge gates, privacy/evidence-lineage regressions, review the exact diff, fix Critical/Important findings, update controllers/docs, then advance. Never claim completion from partial tests.

Production migration, restart, destructive maintenance, remote receiver activation, audio capture, or activation of a new canonical feed mode requires explicit operator authorization.

Audio Evidence v1 is development-complete/review-ready through `90d08e4`; production capture remains disabled and unauthorized. Cross-modal Evidence Fusion v1 is also closed; preserve the established lineage and derived-evidence boundaries.

Cross-modal Evidence Fusion v1 is development-complete/review-ready through `52efdd1`. Review v0 is development-complete/review-ready through code HEAD `19dbb7d`: append-only review ledger, audited Humanitarian transitions, Maritime state-machine delegation, bounded observability, and no direct publication transition. The Evidence Fusion loop is complete and production is at schema `0023_review_records`. The Live Humanitarian/Maritime + Unified Acquisition Pipeline packet is deployed at `414a76b` and ready for final review. AIS remains legacy; Structured Radio and one bounded terms-allowed Remote Radio monitor are active; Audio Evidence stays disabled unless separately authorized.
