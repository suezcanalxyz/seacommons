# SeaCommons — current agent prompt

Work on `suezcanalxyz/seacommons` from the latest verified branch state. Do not restart completed architecture packets.

## Canonical controller

Read first:

1. `docs/superpowers/plans/2026-09-06-evidence-fusion-development-loop.md`
2. `docs/current_work.md`
3. the current packet spec
4. the current packet implementation plan

The master loop controls packet order. Do not jump directly to Review, radio/audio or a later source integration while the current packet still has an open release gate.

## Current packet

Free/Open AIS Fusion v1, Task 8 release gates.

Detailed plan: `docs/superpowers/plans/2026-09-06-free-open-ais-fusion-v1.md`.

Tasks 0-7 are already implemented. Continue from Task 8; do not reimplement the AIS bus, provider contract, AISStream adapter, aiscast adapter, reconciliation, coverage reasoning, SAR Mission enrichment, or `legacy | shadow | fused` runtime.

Current development runtime defaults to `legacy`. Shadow/fused activation is a separate deployment decision.

## Loop after AIS

Humanitarian Verification v1 -> Remote Maritime Radio v1 -> DSC/NAVTEX structured evidence -> Audio Evidence v1 -> Cross-modal Evidence Fusion v1 -> Review v0/publication controls.

At packet completion, update this file, `docs/current_work.md`, the master loop, and the packet execution record before advancing.
## Non-negotiable invariants

- Source identity != transport adapter != physical/provider lineage.
- Humanitarian domain != incident-creation authority.
- Alarm Phone remains the Humanitarian operational-origin authority for now; other humanitarian NGOs are verification sources, not Maritime by reclassification.
- Observation != incident/episode != assessment/hypothesis != review != public projection.
- Safety/nav status never becomes Humanitarian or Intelligence by fallback.
- Humanitarian public output never exposes MMSI/IMO/callsign/tracker dossier data.
- Multiple AIS providers/detectors do not become independent corroboration automatically.
- Derived behaviour, transcription and AI output are context/assistive evidence, never canonical truth alone.
- New adapters must fail closed, expose health, preserve provenance/source terms, and normalize before business reasoning.
- Prefer software-only and free/open acquisition; paid providers or SeaCommons-owned hardware are not core requirements.

## Execution loop

For each task: inspect existing code -> write RED test -> run and observe expected failure -> implement minimum change -> run GREEN + focused regressions -> static checks -> commit one semantic unit -> update execution record.

For each packet: run full backend/static/web/edge gates, privacy and evidence-lineage regressions, review the exact diff, fix Critical/Important findings, then advance the master loop. Never claim completion from partial tests.

Production migration, restart, destructive maintenance, or activation of a new canonical feed mode requires explicit operator authorization.