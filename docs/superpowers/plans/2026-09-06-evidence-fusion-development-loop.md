# SeaCommons Evidence Fusion Development Loop

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. This document is the canonical loop controller; each packet has its own detailed spec/plan and must pass its release gate before the loop advances.

**Goal:** Evolve SeaCommons from a strong maritime OSINT map into a modular, evidence-first system that ingests heterogeneous sources, reconstructs operational situations, verifies outcomes, and shows why a conclusion is supported.

**Architecture:** All source-specific transports normalize into shared evidence contracts before domain reasoning. Humanitarian incidents and Maritime Intelligence episodes share provenance/lineage infrastructure but keep separate decision semantics. New source types are added as adapters, never as parallel truth pipelines.

**Current packet:** Free/Open AIS Fusion v1 — Task 8 release gates.

**Detailed current plan:** `docs/superpowers/plans/2026-09-06-free-open-ais-fusion-v1.md`

## Canonical loop

Every cycle MUST execute in this order:

1. Read this master loop, `docs/current_work.md`, the current packet spec, and current packet plan.
2. Inspect current branch/main and existing implementations before coding.
3. Finish the smallest current packet task with TDD RED -> GREEN.
4. Run the packet's focused regression gate before committing.
5. Commit one semantic unit with documentation updated in the same packet.
6. At packet completion, run full backend/static/web/edge gates plus relevant privacy/evidence invariants.
7. Run code review and fix Critical/Important findings before merge readiness.
8. Update `docs/current_work.md`, `prompt.md`, this loop, and the completed plan execution record.
9. Only then advance `Current packet` to the next packet below.
10. Production migration/restart/deploy remains a separate explicit operator decision unless already authorized.
## Packet sequence

### Packet A — Free/Open AIS Fusion v1

Status: implementation Tasks 0-7 complete; Task 8 release verification/documentation remains.

Delivers: AISStream + Open Waters/aiscast adapters, normalized provider contract, upstream/station provenance, conservative reconciliation, coverage-aware gap reasoning, SAR Mission context, runtime `legacy | shadow | fused`, bounded observability and rollback.

Exit gate: exact-head backend/static/web/edge suites green, Humanitarian privacy unchanged, no low-specificity hypothesis inflation, docs aligned, review complete. Shadow/fused production activation is not required to advance the development loop unless operator explicitly requests deployment.

### Packet B — Humanitarian Verification v1

Goal: use humanitarian verification sources to double-check Alarm Phone incidents and determine outcome evidence without letting secondary sources create canonical incidents by default.

Core flow:

`Alarm Phone operational-origin observation -> HumanitarianIncident -> VerificationWatch -> NGO/IOM claims + SAR MissionAssessment -> ResolutionAssessment -> Review -> lifecycle`

Source roles:
- Alarm Phone: `operational_origin` for incident creation authority, for now.
- SOS Mediterranee / MSF / Sea-Watch / Open Arms / similar first-party NGO sources: `verification`.
- IOM Missing Migrants and comparable historical datasets: `archive_reference`.

Required outcomes: `no_evidence | response_detected | rescue_activity_probable | rescue_confirmed | contradictory_evidence | insufficient_evidence`. Explicit first-party rescue claims may resolve only with strong incident matching; otherwise `rescue_confirmed + needs_review`.
### Packet C — Remote Maritime Radio v1

Goal: software-only remote receiver ingestion with no SeaCommons-owned hardware.

Delivers a generic `RemoteReceiverAdapter` contract and provider-specific adapters (initially KiwiSDR/OpenWebRX where automation and terms permit), receiver capability/health, station/source provenance, bounded receiver discovery and normalized `RadioObservation`.

No continuous voice recording by default. Receiver/provider availability is operational context, not independent evidence merely because multiple frontends expose the same physical receiver.

### Packet D — DSC + NAVTEX structured evidence

Goal: decode high-signal structured maritime radio before attempting broad voice intelligence.

DSC observations preserve category, MMSI when present, coordinates, timestamp, channel/frequency, receiver identity and raw evidence reference. NAVTEX observations preserve station, message type, area, timestamp, text and source/receiver provenance.

A DSC/EPIRB-style emergency observation may create a maritime emergency candidate, but must never become Humanitarian solely by signal type. NAVTEX is primarily contextual/corroborative evidence unless a future explicit rule says otherwise.

### Packet E — Audio Evidence v1

Goal: support bounded, legally-permitted remote audio as immutable evidence artifacts rather than a second truth store.

Introduce `EvidenceArtifact(type=audio)` with receiver, frequency/channel, start/end, content hash, retention policy and linked observation IDs. Transcript and claim extraction are derived objects. No transcript or model output can directly resolve an incident or publish an allegation.

Before production acquisition, complete jurisdiction/provider-specific legal and retention review. Unsupported or unclear receiver terms remain disabled.
### Packet F — Cross-modal Evidence Fusion v1

Goal: combine independent evidence modalities without collapsing provenance or overstating confidence.

Target evidence packet:

`Alarm Phone distress + NGO first-party claim + reconciled NGO AIS mission behaviour + DSC/NAVTEX/radio evidence -> ResolutionAssessment / MaritimeEpisode context`

Rules: source independence is lineage-based; multiple transports from one source identity do not multiply evidence; AIS providers remain the same AIS modality; derived behaviour never counts as an extra source; contradictions are preserved, not averaged away.

### Packet G — Review v0 and publication controls

Goal: route uncertainty from Humanitarian ResolutionAssessment and Maritime InvestigationHypothesis through one review mechanism without creating a second truth store.

Review records evidence snapshot, decision, rationale, actor/time and transition. Approval may advance canonical lifecycle/publication only through existing domain-specific gates.

## Permanent invariants

- Observation != incident/episode != assessment/hypothesis != review != public projection.
- Source identity != transport adapter != receiver/provider lineage.
- Humanitarian source domain != authority to create a HumanitarianIncident.
- Safety/nav status never becomes Humanitarian or Intelligence by fallback.
- Humanitarian public surfaces never expose MMSI/IMO/callsign/tracker dossier data.
- AI and transcription are assistive/derived only; never canonical truth by themselves.
- Multiple detectors/providers do not equal independent evidence.
- Every durable analytical object must be replayable and provenance-linked.
- Prefer free/open and software-only acquisition; paid or owned-hardware dependencies are not core requirements.
- Every new adapter must fail closed, expose health, document terms and preserve raw-source identity.
