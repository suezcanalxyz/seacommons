# Humanitarian Evidence Pipeline — Modular Verification Design

Date: 2026-09-06
Branch: `spec/humanitarian-evidence-pipeline`
Base: `0ae4df7cc20c8209acc267eb595129c2dc3961bd`

## 1. Problem

SeaCommons currently has strong but partly disconnected components: Alarm Phone distress ingestion, NGO/news monitoring, immutable `SourceObservation`, humanitarian incidents, incident follow-up, AIS-based NGO response analysis, SAR triangulation, behavioural baselines, and a separate Observation → Episode → Hypothesis pipeline for Maritime Intelligence.

The next step is not to add more collectors independently. It is to make every transport produce the same evidence contract, then let domain-specific verification reason over that evidence. This must support current X/Twikit ingestion and future Alarm Phone email, webhook, RSS, API, radio, or media ingestion without changing incident logic.

The canonical humanitarian chain becomes:

`Transport Adapter -> SourceIdentity -> SourceObservation -> Semantic Evidence/Claim -> HumanitarianIncident association -> VerificationWatch -> SARMissionAssessment + ResolutionAssessment -> Review -> canonical lifecycle -> public projection`

Maritime Intelligence remains parallel after the shared evidence boundary:

`SourceObservation -> MaritimeEpisode -> InvestigationHypothesis -> Review -> publication gate`

## 2. Goals

- Separate source identity from transport/protocol.
- Keep humanitarian source domain separate from incident-opening authority.
- Make Alarm Phone extensible across X, email, webhook, RSS, API, and future channels through adapters.
- Treat MSF, SOS Méditerranée, Sea-Watch, and similar NGO feeds as humanitarian verification sources rather than Maritime Intelligence.
- Extract structured claims from humanitarian reports and use them to verify or resolve existing Alarm Phone incidents.- Turn NGO AIS trajectories and behavioural deviations into auditable SAR mission evidence, never automatic intent claims.
- Add a persistent resolution assessment layer distinct from incident truth.
- Reuse the same evidence lineage rules across humanitarian verification and Maritime Intelligence.
- Create an extension point for future DSC, NAVTEX, EPIRB, SDR, AIS-Catcher, image, audio, and video evidence.

## 3. Non-goals

- No automatic case resolution from proximity alone.
- No claim that AIS anomaly means rescue.
- No generic LLM risk or intent scoring.
- No replacement of Alarm Phone as the current incident-opening authority.
- No streaming/media platform, WebRTC stack, or Jitsi integration in the first packet.
- No migration of all historical NGO events into newly inferred outcomes.
- No merging Humanitarian and Maritime Intelligence truth objects.
- No assumption that two transports from the same source identity are independent corroboration.

## 4. Source identity is not transport

Every ingest adapter must resolve a stable `SourceIdentity` before business logic runs. `Alarm Phone` is one source identity; X/Twikit, email, webhook, RSS, or API are transports.

Example:

`AlarmPhoneXAdapter -> source_identity=alarm_phone, transport=x`

`AlarmPhoneEmailAdapter -> source_identity=alarm_phone, transport=email`

Both must normalize into the same `SourceObservation` contract. Downstream incident creation, correlation, verification, lifecycle, and publication code must never branch on transport when it means to ask who the source is.

Transport metadata remains preserved for provenance, deduplication, replay, and audit.## 5. Source domain and source role

`service=humanitarian` describes the domain of a source/evidence stream. It does not imply authority to open or resolve an incident.

Initial roles:

- `operational_origin`: currently Alarm Phone. May create a `HumanitarianIncident` when distress criteria are satisfied.
- `verification`: MSF, SOS Méditerranée, Sea-Watch, and equivalent humanitarian operational sources. Their observations verify, contradict, update, or resolve an existing case when association is strong enough; they do not automatically open a new case in v1.
- `archive_reference`: IOM Missing Migrants and similar retrospective/reference datasets. They support validation, archive, Play, and historical analysis, not Live incident creation.

Source role is policy/configuration attached to `SourceIdentity`, not inferred from event wording.

## 6. Adapter contract

Each transport adapter has one responsibility: acquire source material and emit normalized evidence. It must not create incidents directly.

Minimum adapter output:

- stable `source_identity`
- `transport`
- source-native delivery/thread/message ID
- observed/published timestamp
- source URL or message reference when available
- raw payload hash and preservation reference
- normalized text/media references
- available coordinates with precision/provenance
- source-native reply/thread linkage
- adapter method version

A future Alarm Phone email adapter should require only mailbox parsing, sender/source authentication, message/thread ID extraction, body/media normalization, and mapping to this contract. No lifecycle or correlation code changes should be required.

## 7. Semantic evidence and claims

After `SourceObservation`, a deterministic extraction layer produces structured `Claim` objects without mutating the raw observation.Initial claim types include:

- `distress_reported`
- `rescue_started`
- `rescue_completed`
- `people_rescued`
- `people_missing`
- `disembarkation_reported`
- `fatality_reported`
- `asset_dispatched`
- `asset_on_scene`
- `case_resolved_statement`
- `contradictory_update`

Each claim carries actor/entity references, people-count/range when available, time window, place/position evidence, vessel description, linked source observation IDs, extraction method/version, and confidence in extraction only. Extraction confidence is not incident truth confidence.

## 8. Association before lifecycle mutation

Verification-source claims must first associate to one or more open `HumanitarianIncident` candidates. Matching is evidence-based and reviewable.

Association features, in increasing specificity, include:

- exact source-native thread/reply/case IDs
- temporal compatibility
- spatial overlap or compatible uncertainty areas
- route/departure/place compatibility
- people-count range compatibility
- vessel description compatibility
- NGO/authority/asset references
- entity and lexical overlap
- independent evidence lineage

A weak match remains `UNCERTAIN`; it must never mutate canonical lifecycle. Existing `CorrelationDecision` becomes the compatibility layer and should evolve from temporal-only candidate generation into a richer association packet rather than an auto-merge engine.

## 9. Humanitarian VerificationWatch

Each active or `needs_review` Humanitarian incident may have a bounded `VerificationWatch`. This watch collects follow-up evidence; it never owns canonical truth.

Inputs include new verification-source claims, independent operational signals, NGO vessel movement, behavioural assessments, and future radio/media evidence. Every follow-up enters through `SourceObservation` or a derived evidence artifact linked to one.

The watch emits assessments and candidate lifecycle transitions. It does not rewrite founding observations and does not silently merge incidents.## 10. SAR Mission Assessment

`core.intel.ngo_response` already computes NGO vessel distance, course toward incident, ETA, fix age, and motion flags. V1 turns this into a persisted, replayable `SARMissionAssessment` linked to one incident and one NGO vessel identity.

Suggested states are descriptive, not intent claims:

- `unrelated`
- `possible_response`
- `approaching`
- `on_scene`
- `probable_rescue_activity`
- `departing_scene`
- `post_rescue_transit`
- `insufficient_evidence`

Evidence may include decreasing distance to the incident uncertainty area, compatible course/ETA, time on scene, `ngo_search_pattern`, `rescue_cluster`, `sudden_stop`, loiter/search geometry, departure from scene, and subsequent transit toward a plausible port.

Behavioural Baseline v1 provides context: an unusual route/speed/silence pattern may strengthen an assessment, but if it derives from the same AIS lineage it is not an independent source. No single AIS anomaly can assert a rescue.

## 11. Resolution Assessment

A persistent `ResolutionAssessment` evaluates whether the current evidence supports an incident outcome. It is derived and revisable; `HumanitarianIncident` remains canonical truth.

Initial outcomes:

- `no_resolution_evidence`
- `response_detected`
- `rescue_activity_probable`
- `rescue_confirmed`
- `disembarkation_confirmed`
- `fatal_outcome_reported`
- `contradictory_evidence`
- `insufficient_evidence`

An explicit first-party NGO statement may support `rescue_confirmed` only when association to the Alarm Phone incident is strong. Otherwise it remains a confirmed claim with `needs_review`, not automatic incident resolution.

AIS mission evidence may support `response_detected` or `rescue_activity_probable`; AIS alone cannot produce `rescue_confirmed` in v1.

Canonical `resolved` requires either a high-specificity independently sourced resolution packet that satisfies explicit deterministic gates, or an approved Review decision. Time passage alone never resolves a case.## 12. Shared evidence lineage

Humanitarian verification and Maritime Intelligence share provenance rules, not decision rules. `core.intel.evidence_lineage` remains authoritative for independence.

Two Alarm Phone transports carrying the same underlying message/thread remain one source identity and normally one independence group. OCR over an Alarm Phone image is derived evidence from the same publication, not an independent witness. Multiple AIS algorithms over the same receiver/provider lineage remain one AIS source lineage.

Humanitarian verification asks: what happened to this case? Maritime Intelligence asks: what hypothesis is justified about this episode? Their assessment objects must remain separate even when they consume some of the same observations.

## 13. Future sensor adapters

New integrations from `implementation.txt` enter at the evidence boundary rather than creating new truth paths. The first sensor packet is explicitly **software-only, free-to-use, and open-first**: no new hardware dependency and no paid AIS provider may be required for core functionality.

- Free/Open AIS Fusion v1: keep AISStream as an existing live source and add Open Waters/aiscast as the first new software-only provider. Both normalize through one provider adapter contract, preserve provider/station provenance where exposed, and feed one reconciled track layer. Provider multiplicity never counts automatically as independent physical evidence.
- AIS-Catcher: retained as a future decoder/community compatibility target only; it is not required by v1 because the user explicitly requires no hardware.
- DSC: structured maritime distress/urgency/safety communication evidence; may support maritime-emergency candidate creation and humanitarian corroboration when association exists.
- NAVTEX: contextual navigation/SAR-area evidence; not a Humanitarian incident origin by itself.
- EPIRB: high-specificity emergency evidence; may create a maritime-emergency candidate but not automatically classify it Humanitarian.
- Remote SDR: transport for radio observations; receiver/source lineage must be explicit.
- Image/audio/video: `EvidenceArtifact` linked to `SourceObservation`, with hash, source, timestamp, preservation state, optional location, and extracted claims.

No future adapter may bypass `SourceObservation` to mutate incidents, episodes, hypotheses, or lifecycle directly.

## 14. Privacy and publication

Humanitarian public output remains privacy-first. Internal AIS-to-distress association, NGO MMSI/IMO/callsign, tracker URLs, behavioural baselines, raw email addresses, private message headers, source-native private identifiers, and evidence artifacts are not automatically public.

A public case may expose a safe statement such as `response activity detected` or an approved first-party resolution statement without exposing the internal vessel-tracking dossier used to reach it.

Email ingestion must separate authentication/provenance metadata from public content at ingest time. Raw email headers and sender addresses are restricted evidence unless an explicit policy says otherwise.

## 15. Compatibility with current work

The unmerged `fix/humanitarian-source-boundary` worktree contains a direction that reclassifies non-Alarm-Phone humanitarian organizations as Maritime. That semantic change must not be merged. Useful UI work that replaces provenance-first sections with `Humanitarian / Maritime intelligence` may be salvaged later only after it consumes the corrected source-domain contract.

Existing `IncidentWatch`, `CorrelationDecision`, `ngo_response`, `triangulation`, Behavioural Baseline v1, Observation → Episode → Hypothesis v1, and future Review v0 should be extended/reused rather than replaced.## 16. Implementation packets

This architecture must be delivered as independent packets, each releasable and testable on its own:

1. `SourceIdentity + adapter contract + source roles`
   - establish identity/transport separation;
   - keep Alarm Phone as current incident-opening authority;
   - keep NGO verification sources in `service=humanitarian`.

2. `Humanitarian Claim v1 + association`
   - structured claim extraction;
   - richer `CorrelationDecision` features;
   - no lifecycle mutation yet.

3. `SAR Mission Assessment v1`
   - persist NGO vessel response/behaviour assessments;
   - replay-safe and lineage-aware.

4. `Resolution Assessment v1`
   - combine claims, mission evidence, and independent observations;
   - candidate outcomes only;
   - deterministic gates for any automatic lifecycle transition.

5. `Review integration`
   - analyst approve/reject/needs-more-evidence decisions bind exact evidence snapshots.

6. `Free/Open AIS Fusion v1`
   - generic AIS provider adapter contract;
   - AISStream wrapped without changing its current feed behaviour;
   - Open Waters/aiscast adapter;
   - provider/station provenance, health, reconciliation, and coverage-aware gap reasoning;
   - feed the reconciled track into Behavioural Baseline and SAR Mission Assessment.

7. `Remote radio expansion`
   - software-only DSC/NAVTEX/remote-SDR adapters through the same evidence boundary;
   - no continuous VHF recording requirement in the first radio packet.

8. `Rich evidence artifacts`
   - image/audio/video/document preservation and claim extraction without building a streaming platform.

## 17. TDD contracts

Required regression coverage includes: same Alarm Phone source identity through X and synthetic email produces equivalent normalized source semantics; replayed email/message delivery is idempotent; two transports of the same Alarm Phone publication do not count as independent corroboration; a non-Alarm-Phone humanitarian verification source cannot open a v1 incident; it remains `service=humanitarian`; explicit SOS/MSF/Sea-Watch rescue claims create structured claims and association candidates; weak association cannot resolve; AIS approach alone cannot confirm rescue; AIS approach + on-scene behaviour can reach at most `rescue_activity_probable`; strongly associated first-party rescue statement can reach `rescue_confirmed`; canonical resolve obeys review/automatic gate; source-role changes are policy-driven, not wording-driven; Humanitarian privacy remains clean; replay cannot duplicate claims, mission assessments, or resolution assessments.

## 18. Observability

Metrics/logs should expose source identity, transport, source role, adapter method version, observation/claim IDs, association decisions, mission assessment transitions, resolution assessment outcomes, and review state. Labels must avoid private email addresses, MMSI/IMO, message bodies, or other sensitive identifiers.

Operational dashboards should distinguish collector health from evidence usefulness: a source may ingest successfully while producing zero relevant verification claims.

## 19. Exit criteria

The architecture is complete when a new Alarm Phone transport adapter can be added without editing incident/lifecycle logic; source identity and transport are independently represented; humanitarian verification NGOs remain Humanitarian but cannot open incidents by default; follow-up claims and NGO AIS behaviour can be associated to existing Alarm Phone incidents through replayable evidence; rescue activity and rescue confirmation remain distinct; lifecycle mutation is gated and auditable; shared lineage prevents false multi-source corroboration; new sensors can enter through adapters without new truth paths; and public Humanitarian output remains privacy-safe.
