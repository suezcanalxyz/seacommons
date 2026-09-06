# Observation → Episode → Hypothesis v1 — Design

Date: 2026-09-06
Branch: `spec/observation-episode-hypothesis-v1`
Base: `fbcdb55471af4b19f45dfc927146e7ea26dc08b2`

## 1. Problem

SeaCommons already has immutable observations, a bounded runtime episode builder, and a persisted `InvestigationHypothesis` lifecycle. The remaining problem is semantic authority: episodes are not persisted as first-class analytical objects, while the live hypothesis engine can still create hypotheses directly from weak or same-lineage AIS indicators.

Production audit on 2026-09-06 found 3,151 persisted hypotheses, 3,141 with exactly one evidence link, and 2,856 `dark_transit` candidates. None of that is evidence of public leakage, but it proves that the internal hypothesis layer is being used too early in the reasoning chain.

The v1 correction is not a parallel subsystem. It is a non-destructive cutover of the existing M5/M6 wiring to the canonical chain:

`Observation -> persisted MaritimeEpisode -> hypothesis eligibility -> InvestigationHypothesis -> Review -> publication policy`

## 2. Goals

- Persist bounded maritime episodes as derived, replayable analytical objects.
- Make episode identity deterministic and idempotent across replay.
- Carry evidence lineage, behavioural context, and deterministic alternative explanations at episode level.
- Stop low-specificity single-lineage AIS patterns from creating intelligence hypotheses.
- Link every new v1 hypothesis to exactly one persisted episode.
- Preserve all pre-v1 hypotheses without destructive rewrite or automatic expiry.
- Preserve Humanitarian privacy, Safety neutrality, and existing public publication gates.
## 3. Non-goals

- No new detector thresholds in this packet.
- No ML risk score, vessel reputation score, whitelist, or blacklist.
- No automatic deletion, expiry, or reclassification of the 3,151 legacy hypotheses observed in production.
- No public UI redesign.
- No Review v0 implementation yet.
- No generic event-sourcing rewrite or full Evidence Graph rewrite.
- No fleet-wide historical episode backfill during migration.

## 4. Authority model

`SourceObservation` and raw `IntelEvent` evidence remain immutable source facts. `MaritimeEpisode` is a derived, revisable grouping of observations/features. `InvestigationHypothesis` is an interpretation about one episode and must never become a second store for raw facts.

Behavioural context is descriptive evidence context only. `expected`, `unusual`, and `insufficient_history` never assert intent. Evidence lineage determines independence. Two algorithms over the same AIS lineage remain one source lineage.

Safety is never a fallback category. Unknown or unmapped maritime signals become `unclassified_episode`; `safety_episode` is created only from explicit Safety semantics such as `not_under_command` or another mapped Safety state.

## 5. Migration 0021

Add `maritime_episodes` with: `episode_id`, `episode_family`, `subject_ids`, `start_at`, `end_at`, `status`, `geometry`, `observation_ids`, `feature_ids`, `independence_groups`, `verification_status`, `behaviour_context`, `alternative_explanations`, `evidence_fingerprint`, `method_version`, `revision`, `created_at`, and `updated_at`.

Add nullable indexed `episode_id` and nullable `method_version` to `investigation_hypotheses`. Existing rows remain NULL and therefore explicitly legacy/pre-v1. No migration-time hypothesis rewrite is allowed.
## 6. Episode identity and persistence

The runtime `build_episodes()` boundary rules remain the starting authority: subject continuity, family, time gap, spatial continuity, and explicit resolution. V1 replaces sequence-number episode IDs with a stable ID derived from sorted subject IDs, episode family, the first causal observation ID, and episode method version.

Each persisted row also carries an evidence fingerprint over ordered observation/feature IDs plus the derived lineage/context inputs used by the episode method. Replaying identical evidence must reproduce the same episode ID and fingerprint without duplicate rows.

A continuing episode may update the same row with a new fingerprint and incremented `revision`; raw observations are never rewritten. A boundary change that yields a different first causal observation produces a different episode ID rather than silently changing historical identity.

Episodes are internal analytical objects by default. Safety projection may consume explicit `safety_episode` objects through the existing Safety policy. Public Maritime Intelligence still requires a published `InvestigationHypothesis`; an episode alone is never an allegation.

## 7. Episode semantic contract

Initial families remain: `gap_episode`, `rendezvous_episode`, `identity_integrity_episode`, `spoofing_episode`, `port_call_episode`, `infrastructure_proximity_episode`, and `safety_episode`, plus new fail-closed `unclassified_episode`.

Every episode records its contributing observation IDs, evidence/feature IDs, independence groups, and one derived verification status using the OSINT Evidence Pipeline v1 vocabulary: `single_source_observed`, `single_source_multi_indicator`, or `multi_source_corroborated`.

Source display names never determine independence. `core.intel.evidence_lineage` remains the authority. Multiple AIS detectors, MDA-derived indicators, or transformations of the same platform publication do not manufacture additional independent groups.

## 8. Behaviour and alternatives

Episodes may attach the latest applicable `BehaviourAssessment` and baseline ID. Behavioural deviation can strengthen context but cannot count as an independent source when it derives from the same AIS lineage.

V1 adds deterministic alternative-explanation reason codes, not LLM prose: `EXPECTED_BASELINE_BEHAVIOUR`, `COVERAGE_DEGRADATION`, `PORT_OR_COASTAL_RECEPTION`, `SCHEDULED_SERVICE_PATTERN`, `NAVIGATION_SAFETY_STATE`, and `INSUFFICIENT_HISTORY`. Open alternatives remain visible to hypothesis gates and reviewers; they are not silently converted into certainty.
## 9. Hypothesis eligibility v1

New v1 hypotheses are created only by a gate that consumes one persisted episode plus its linked evidence/context packet. Every new hypothesis stores `episode_id` and `method_version` and uses an ID namespace that cannot collide with legacy pre-v1 rows.

Low-specificity patterns require genuine independent corroboration before a hypothesis object exists. In v1 this applies to `dark_transit`, `covert_rendezvous`, and `infrastructure_pattern`. A same-lineage AIS gap, gap plus infrastructure proximity, or repeated AIS-only rendezvous remains an episode, not a hypothesis.

`position_spoofing` is the narrow high-specificity exception: a deterministic impossible-movement pattern with reproducible raw fixes and explicit counter-evidence checks may create a `candidate` hypothesis from one AIS lineage, but its evidence stage remains `derived` and it cannot advance to `collecting` on detector count alone. Independent corroboration is required for forward progression.

`identity_deception` and `sanctions_evasion_pattern` remain unwired until their cross-source gates can be satisfied correctly. An official sanctions-list match remains a fact; it does not become evasion behaviour.

`candidate -> collecting` is no longer controlled by `len(signal_ids)`. State progression must use gate output plus independent lineage count and required counter-evidence/alternative checks for that hypothesis type.

## 10. Legacy cutover

Migration `0021` leaves all existing hypothesis rows unchanged. `episode_id IS NULL` means legacy/pre-v1. The new engine must never silently attach a new episode to an old row or mutate its evidence links to make it look v1-native.

New v1 hypotheses use deterministic IDs derived from hypothesis type + persisted v1 episode ID + hypothesis method version. Legacy rows remain queryable for audit. Expiry, archival, or cleanup of legacy hypotheses is a separate operator-reviewed maintenance packet.

The production cutover disables new writes through the legacy hypothesis creation path only after v1 episode persistence and replay tests are green. No destructive DB maintenance is part of this packet.
## 11. YOUR WISDOM regression contract

The existing benign-service fixture remains generic evidence, never a production exception. For a recurring scheduled-service-like vessel with expected route/speed/silence behaviour, `AIS gap + infrastructure proximity` from one AIS lineage must produce at most an internal episode with `single_source_multi_indicator`, zero new `InvestigationHypothesis`, zero Case, and zero public Intelligence allegation.

A contrastive scenario for the same identity may become behaviourally `unusual`. It still requires the relevant hypothesis gate: for low-specificity families, independent corroboration must exist before a hypothesis is created. No code may special-case vessel name, MMSI, IMO, ferry class, Malta/Gozo, or any operator.

## 12. Replay and observability

Episode persistence must be replay-safe on a populated database. The same input set cannot create duplicate episodes or duplicate v1 hypotheses. Structured logs and metrics must carry stable `observation_id`, `episode_id`, and `hypothesis_id` where applicable.

Required metrics include episode creation/update counts by family, episode verification status, hypothesis eligibility rejected/created counts by type/reason, and legacy-vs-v1 hypothesis counts. Metrics describe system behaviour, not vessel risk.

## 13. Privacy and publication

Humanitarian public output must continue excluding MMSI, IMO, callsign, tracker URLs, vessel dossiers, behavioural baselines, and internal episode/hypothesis metadata. Nearby Humanitarian context remains annotation only and never merges Maritime and Humanitarian truth objects.

Safety remains neutral and can be publicly projected through its existing policy without an Intelligence hypothesis. Maritime Intelligence public output remains impossible unless the linked v1 hypothesis passes `can_publish()` and the existing publication policy.

## 14. TDD contract

Required RED/GREEN coverage includes: persisted deterministic episode identity; replay idempotency; same-lineage detector multiplicity remaining one independence group; unknown anomaly mapping to `unclassified_episode`, never Safety; explicit Safety still mapping to `safety_episode`; one AIS gap creating no `dark_transit` hypothesis; two same-lineage AIS gap indicators still creating no `dark_transit` hypothesis; genuinely independent evidence satisfying the low-specificity gate; high-specificity spoof candidate not advancing on detector count; behaviour expected/unusual never counting as a second source; legacy rows remaining untouched with NULL `episode_id`; v1 hypotheses always carrying an episode ID; YOUR WISDOM benign contract; Humanitarian privacy; public hypothesis gate; and end-to-end replay without duplicate episodes/hypotheses.
## 15. Expected implementation surface

- `core/db/models.py`: `MaritimeEpisodeDB`, plus v1 link/version fields on `InvestigationHypothesisDB`.
- Alembic `0021_maritime_episodes.py`: additive schema only.
- `core/live/episode_builder.py`: stable family fallback and deterministic episode identity inputs.
- `core/live/vessel_episodes.py`: episode evidence/lineage/context projection and persistence integration.
- New focused episode store/service module rather than adding DB concerns to the pure builder.
- `core/intel/hypothesis_engine.py`: episode-backed eligibility and lineage-aware progression.
- `core/intel/hypothesis.py`: only gate-contract changes that are necessary for v1 semantics.
- `core/mda/watch.py`: cut over live evaluation to persisted v1 episodes after successful episode persistence.
- Tests/fixtures for episode persistence, hypothesis eligibility, replay, privacy, and YOUR WISDOM.

## 16. Release gates

Before merge: targeted RED/GREEN cycles, full backend, Ruff/mypy, migration upgrade/downgrade/upgrade, SQLite compatibility, deterministic replay, Humanitarian privacy, evidence-lineage/SAR regressions, Live/Play/API/map/simulation tests, web lint/build, edge tests/Wrangler dry-run, dependency audit where configured, `git diff --check`, and exact-head Full CI + CodeQL.

Production rollout requires a PostgreSQL backup before `0021`, migration verification against the real service environment, supervised restart only with operator approval, `/ready`, Live/Play smoke, new-v1 episode/hypothesis counters, and a bounded audit proving new low-specificity single-lineage observations no longer inflate hypothesis counts.

No cleanup of legacy hypotheses is bundled with rollout.

## 17. Exit criteria

The packet is complete only when observations, episodes, and hypotheses are distinct persisted/derived layers; replay is idempotent; new low-specificity hypotheses require the specified independent corroboration; high-specificity single-lineage candidates cannot masquerade as corroborated or advance on detector count; unknown maritime signals cannot fall into Safety; every new v1 hypothesis links to one persisted v1 episode; legacy hypotheses remain auditable and untouched; YOUR WISDOM-like normal service behaviour produces no intelligence hypothesis from same-lineage indicators; public Intelligence still requires the hypothesis publication gate; and Humanitarian privacy remains regression-clean.