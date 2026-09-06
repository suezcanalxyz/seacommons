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

Remote Maritime Radio v1, Task 2 — KiwiSDR remote adapter.

Detailed plan: `docs/superpowers/plans/2026-09-06-remote-maritime-radio-v1.md`.

Free/Open AIS Fusion v1 is development-complete/shadow-ready. Humanitarian Verification v1 is development-complete/review-ready through `961c436`; release gates were `141` focused tests and `1350` full backend tests plus green static/web/edge/dependency gates. No production AIS cutover or Humanitarian auto-resolution was authorized.

Tasks 0-1 are complete. Continue with Task 2 using the provider-neutral contract and explicit receiver registry; keep all network I/O injectable and fail closed. `core.sensors.sdr.SDRScanner` is the legacy local RTL-SDR anomaly scanner and must not become the remote receiver architecture.

## Packet boundary

Remote Maritime Radio v1 adds software-only configured receiver identity/capability/health, provider adapters (KiwiSDR/OpenWebRX where terms and automation permit), physical RF lineage, bounded observations, observability, and a disabled-by-default runtime.

Do not add continuous audio/IQ persistence, broad voice transcription, DSC decoding, NAVTEX decoding, Humanitarian incident creation, lifecycle resolution, or public allegations in this packet. Those belong to later packets.

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
