# Humanitarian Verification v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans task-by-task. Every behavior change is TDD; watch RED before implementation and verify GREEN before commit.

**Goal:** Turn non-origin humanitarian NGO evidence plus reconciled SAR AIS behaviour into replayable claims, association decisions, mission assessments, and resolution assessments for existing Alarm Phone incidents without creating a second truth path.

**Architecture:** Reuse `ClaimDB`, `AssessmentDB`, `CorrelationDecisionDB`, `IncidentWatchDB`, `HumanitarianIncidentDB`, `ngo_response`, and evidence-lineage. Add stable source identity/role policy before incident creation; verification sources extract deterministic claims, associate to existing incidents, then update derived assessments only. Canonical lifecycle remains separately gated.

**Tech Stack:** Python 3.12, FastAPI runtime, SQLAlchemy/PostgreSQL-compatible existing schema, pytest, current AIS Fusion/SAR Mission layer.

**Spec:** `docs/superpowers/specs/2026-09-06-humanitarian-evidence-pipeline-design.md`

## Global Constraints

- Alarm Phone is the current `operational_origin` and the only source role allowed to open a v1 Humanitarian incident.
- MSF, SOS Méditerranée, Sea-Watch and equivalent operational NGOs remain `service=humanitarian`, role `verification`.
- IOM Missing Migrants is `archive_reference` and cannot open Live incidents.
- Source identity is independent from transport: X/email/RSS/webhook can resolve to the same identity.
- Verification claims never mutate founding observations.
- Weak association never changes lifecycle.
- AIS evidence can reach at most `rescue_activity_probable`; never `rescue_confirmed` alone.
- Public Humanitarian output must not expose MMSI/IMO/callsign/tracker/private transport metadata.
- No new database migration unless an existing durable object cannot represent the required assessment truthfully.
- No production deploy or lifecycle auto-resolution enablement in this packet.

---### Task 0: Source identity, source role, and incident-opening authority

**Files:**
- Create: `apps/api/core/intel/source_identity.py`
- Modify: `apps/api/core/intel/humanitarian_incident.py`
- Modify: `apps/api/core/intel/source_catalog.py`
- Test: `tests/test_source_identity.py`
- Test: `tests/test_humanitarian_incident.py`

**Interfaces:**
- Produces `SourceIdentityPolicy(identity_id, service, source_role, may_open_incident, independence_group)`.
- Produces `resolve_source_identity(source_name, metadata=None)` and `may_open_humanitarian_incident(event)`.

- [ ] Write RED tests: Alarm Phone aliases across `transport=x|email` resolve to identity `alarm_phone`, role `operational_origin`; SOS/MSF/Sea-Watch resolve to role `verification`; IOM to `archive_reference`; unknown/AIS/nav sources never gain Humanitarian authority.
- [ ] Add RED regression proving a verification-source event classified Humanitarian does not create `HumanitarianIncidentDB`, while equivalent Alarm Phone origin does.
- [ ] Implement stable alias/policy resolver; source role comes from policy, never wording.
- [ ] Gate `_on_intel_event()` incident creation on `may_open_humanitarian_incident(event)` while leaving legacy Alarm Phone aliases compatible.
- [ ] Run focused service/source/incident/privacy tests GREEN.
- [ ] Commit `feat: add humanitarian source identity and authority policy`.

### Task 1: Explicit humanitarian action/outcome Claim v1

**Files:**
- Create: `apps/api/core/intel/humanitarian_claims.py`
- Modify: `apps/api/core/intel/claims.py`
- Test: `tests/test_humanitarian_claims.py`

**Interfaces:**
- Produces immutable `ExtractedHumanitarianClaim` values before association.
- Produces `extract_humanitarian_claims(event, source_policy) -> tuple[ExtractedHumanitarianClaim, ...]`.
- Produces idempotent `persist_associated_claims(incident_id, event, claims)` using existing `ClaimDB`.

- [ ] RED: explicit first-party wording extracts bounded types `rescue_started`, `rescue_completed`, `people_rescued`, `disembarkation_reported`, `fatality_reported`, `asset_dispatched`, `asset_on_scene`, `case_resolved_statement`, `contradictory_update`.
- [ ] RED contrastives: generic NGO advocacy/news text and AIS motion do not become rescue-completed claims; extraction confidence is extraction-only.
- [ ] Implement deterministic phrase/entity/count extraction with method version and actor/asset/time/place evidence in `value`; no LLM.
- [ ] Persist only after an incident candidate is selected; same observation/type replay keeps deterministic ClaimDB identity.
- [ ] Verify existing PeopleCounts claims remain compatible and GREEN.
- [ ] Commit `feat: extract humanitarian verification claims`.### Task 2: Rich association over existing CorrelationDecision

**Files:**
- Modify: `apps/api/core/intel/correlation.py`
- Modify: `apps/api/core/intel/incident_watch.py`
- Test: `tests/test_correlation.py`
- Create: `tests/test_humanitarian_association.py`

**Interfaces:**
- Consumes extracted verification claims and open Humanitarian incidents.
- Produces deterministic features for temporal, spatial, people-count, actor/asset and source-native linkage where available.
- Keeps `CorrelationDecisionDB` append-only; no incident merge occurs here.

- [ ] RED: temporal-only candidate remains `UNCERTAIN`.
- [ ] RED: strong temporal + spatial + compatible people count + explicit NGO asset/actor reference may produce `SAME_INCIDENT` candidate with review state, but never merges rows.
- [ ] RED: conflicting people count/location adds contradicting features and cannot become strong association.
- [ ] Fix independence to use authoritative evidence/source independence group rather than comparing display source families.
- [ ] Enrich `IncidentWatch.profile_json` from existing claims/coordinates so follow-up adapters can search using real people/actor/asset context.
- [ ] Verify replay writes auditable decisions without lifecycle mutation.
- [ ] Commit `feat: enrich humanitarian incident association`.

### Task 3: Persist SAR Mission Assessment v1

**Files:**
- Create: `apps/api/core/intel/sar_mission_assessment.py`
- Modify: `apps/api/core/intel/ngo_response.py`
- Test: `tests/test_sar_mission_assessment.py`

**Interfaces:**
- Uses existing `AssessmentDB` with `field_type="sar_mission"`; deterministic assessment ID includes incident + asset identity.
- Consumes current `ngo_response` result, reconciled AIS provenance, coverage status and Behavioural context where available.

- [ ] RED mission states: unrelated → possible_response → approaching → on_scene → probable_rescue_activity; add departing/post-rescue only with actual trajectory evidence, otherwise insufficient evidence.
- [ ] RED: provider-degraded caps interpretation; same AIS lineage behavioural flags are context, not a second source.
- [ ] Implement replayable/idempotent persisted assessment with evidence IDs/provenance in value and bounded confidence/reason codes.
- [ ] Ensure public Humanitarian projection never receives internal vessel identifiers from this object.
- [ ] Verify existing `ngo_response` API contracts GREEN.
- [ ] Commit `feat: persist SAR mission assessments`.

### Task 4: Resolution Assessment v1

**Files:**
- Create: `apps/api/core/intel/resolution_assessment.py`
- Test: `tests/test_resolution_assessment.py`

**Interfaces:**
- Uses existing `AssessmentDB` with `field_type="resolution"`.
- Consumes associated claims + SAR Mission assessments + evidence lineage.
- Produces one derived outcome and explicit reason/evidence snapshot; does not directly mutate HumanitarianIncident.

- [ ] RED: no evidence → `no_resolution_evidence`; AIS response → `response_detected`; AIS on-scene/search → at most `rescue_activity_probable`.
- [ ] RED: strongly associated first-party NGO `rescue_completed` claim can yield `rescue_confirmed`; weak association yields `insufficient_evidence`/review requirement.
- [ ] RED: contradictory claims produce `contradictory_evidence`; explicit disembarkation/fatality claims map only when strongly associated.
- [ ] Implement deterministic evidence-stage ordering; provider/detector count never substitutes for independence.
- [ ] Persist supporting/contradicting claim IDs and method version; replay updates the same derived assessment ID.
- [ ] Commit `feat: add humanitarian resolution assessments`.### Task 5: Verification orchestration through IncidentWatch

**Files:**
- Modify: `apps/api/core/intel/incident_watch.py`
- Modify: `apps/api/core/intel/humanitarian_incident.py`
- Create: `apps/api/core/intel/humanitarian_verification.py`
- Test: `tests/test_humanitarian_verification.py`

**Interfaces:**
- Produces `evaluate_incident_verification(incident_id) -> dict` as the single derived verification orchestrator.
- Consumes associated claims, SAR Mission assessments and current watch profile.
- Does not mutate canonical lifecycle.

- [ ] RED: a verification-source observation can enrich an existing incident through claims/association without opening another incident.
- [ ] RED: replay is idempotent for claims and assessments.
- [ ] Implement bounded orchestration after watch/source ingestion; failures remain local enrichment failures.
- [ ] Expose operator-safe verification summary without raw private identifiers.
- [ ] Commit `feat: orchestrate humanitarian verification assessments`.

### Task 6: Observability, audit surface, and privacy gates

**Files:**
- Modify: `apps/api/core/observability.py`
- Modify: `apps/api/core/api/routes/ops.py` or existing audit route as appropriate
- Test: `tests/test_observability.py`
- Test: `tests/test_humanitarian_privacy.py` or nearest existing privacy regression file

**Interfaces:**
- Metrics use bounded labels only: source identity, transport class, source role, outcome, review state, method version.
- Operator response may expose assessment IDs/reason codes, never MMSI/IMO/callsign/private email headers/message bodies.

- [ ] RED: metrics never use source-native message IDs, MMSI, email address or arbitrary station labels.
- [ ] RED: public Humanitarian response remains clean after SAR/verification enrichment.
- [ ] Add bounded metrics/logs for claim extraction, association decision, mission outcome and resolution outcome.
- [ ] Add operator-safe verification/audit summary if an existing route can host it without a new public contract.
- [ ] Commit `feat: add humanitarian verification observability`.
### Task 7: Release gates and loop handoff

**Files:**
- Modify: `docs/DATA_FLOW.md`
- Modify: `docs/OPERATIONS_OVERVIEW.md`
- Modify: `docs/current_work.md`
- Modify: `prompt.md`
- Modify: this plan execution record

- [ ] Run focused Humanitarian source/claim/association/SAR/resolution/privacy regressions.
- [ ] Run full backend suite, Ruff critical gate and canonical mypy gate.
- [ ] Run web tests/lint/typecheck/build and edge tests/Wrangler dry-run if public contracts changed.
- [ ] Review diff for duplicate truth paths, lifecycle mutation, false independence and privacy leakage.
- [ ] Mark packet `review-ready`; no production lifecycle automation is enabled.
- [ ] Advance the master loop to `Remote Maritime Radio v1` only after this packet is green and reviewed.
- [ ] Commit `docs: close humanitarian verification v1 release gates`.

## Exit Criteria

Humanitarian Verification v1 is complete when Alarm Phone transport aliases resolve to one operational-origin identity; verification NGOs remain Humanitarian but cannot open incidents; explicit NGO outcome claims can associate to existing Alarm Phone incidents; AIS mission evidence persists separately and caps below confirmation; resolution assessment is deterministic, replayable and distinct from canonical lifecycle; public privacy remains unchanged; and the entire packet passes release gates without production auto-resolution.

## Rollback Boundary

The packet adds derived policy/claims/assessments and gates incident opening. It does not require a new schema migration and does not enable automatic resolution. Rollback is therefore code/config rollback to the prior incident subscriber behavior; existing immutable SourceObservations, Claims and Assessments remain auditable evidence and must not be destructively deleted.
