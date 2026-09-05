# Vessel Context + Behavioural Baseline v1 — Design

Date: 2026-09-06
Branch: `spec/vessel-context-v1`
Base: `b44b5f2b72d64c84ffe99b52a959b597d47d71ea`

## 1. Problem

SeaCommons now distinguishes detector count from independent evidence lineage, but AIS-derived anomalies still lack a vessel-specific behavioural frame of reference.

A short AIS gap, infrastructure proximity, dwell, or route change should not be interpreted against one universal threshold. The same observation can be routine for a ferry, unusual for a cargo vessel, or impossible to assess for a vessel with insufficient history.

The system needs a reproducible context layer that can answer: what vessel identity/context is currently observable, what behaviour is historically typical, and how far a new observation deviates from that history.

This packet must not create a vessel reputation score, a whitelist, or a direct allegation engine.
## 2. Goals

- Build `VesselContext` as a deterministic projection over existing authorities: registry, VesselSubject, track history, and derived port calls.
- Persist `BehaviouralBaseline` as an analytical artifact with explicit window, method version, evidence fingerprint, and reproducible statistics.
- Produce `BehaviourAssessment` with only three top-level states: `expected`, `unusual`, `insufficient_history`.
- Make route, speed, port-pattern, and AIS-silence deviations explainable with typed reason codes and supporting numbers.
- Attach behavioural context to AIS-derived observations without opening a case, mutating canonical identity, or asserting intent.
- Preserve Humanitarian privacy, public vessel-marker semantics, and OSINT Evidence Pipeline v1 lineage rules.

## 3. Non-goals

- No ML classifier, opaque anomaly score, vessel risk score, reputation score, or blacklist/whitelist.
- No direct `possible intentional AIS disabling`, sanctions-evasion, sabotage, smuggling, or other allegation from baseline deviation alone.
- No peer-group model in v1.
- No public UI redesign.
- No new truth store for vessel identity.
- No replacement of `VesselSubject`, registry, `VesselTrackDB`, or existing evidence lineage.
## 4. Authority model

The authority chain is:

`AIS/registry observations -> VesselSubject + track history -> VesselContext projection -> BehaviouralBaseline artifact -> BehaviourAssessment -> future Episode -> future Hypothesis`

`VesselContext` is computed, not persisted as canonical truth. It may include observed values and clearly marked derived context labels, but it must preserve provenance and evidence level.

`BehaviouralBaseline` is persistable because it is a versioned analytical product, not an identity record. It must be invalidatable/rebuildable from the source track window.

`BehaviourAssessment` is a deterministic evaluation against one baseline. It is descriptive evidence context only and cannot independently create an intelligence case or public allegation.

## 5. Existing authorities reused

- `core.mda.vessel_subject`: stable subject identity and conflict handling.
- `core.vessels.registry`: current AIS static/dynamic snapshot.
- `core.vessels.track_store` / `VesselTrackDB`: historical AIS positions.
- `core.api.routes.mda._derive_recent_port_calls`: derived port-approach stays.
- OSINT Evidence Pipeline v1: source lineage, corroboration vocabulary, and publication gating.
## 6. VesselContext projection

`VesselContext` should expose:

- `subject_id`, `primary_mmsi`, `primary_imo`;
- current observed `name`, `flag`, `ship_type`, `destination`, `last_seen`;
- identity conflict count / status from `VesselSubject`;
- history availability (`track_points`, `history_start`, `history_end`, `history_days`);
- recent derived port calls;
- recurring port pairs when supported by enough history;
- observed operating bbox / areas;
- derived context labels with explicit `evidence_level=derived` and method version.

Context labels may include `recurrent_port_pair`, `recurrent_corridor`, and `scheduled_service_candidate`. They are descriptive conveniences, never exemptions from detection.

The projection must work even when IMO is absent. IMO continuity wins where a valid IMO exists; MMSI fallback remains explicitly limited by possible reassignment/spoofing.
## 7. BehaviouralBaseline persistence

Add migration `0020_vessel_behavioural_baselines` with an append/version-friendly table rather than mutable identity columns.

Required fields:

- `baseline_id` primary key;
- `subject_id` and `primary_mmsi` indexes;
- `primary_imo` nullable;
- `window_start`, `window_end`;
- `sample_count`;
- `history_days`;
- `route_model` JSON;
- `speed_model` JSON;
- `port_model` JSON;
- `silence_model` JSON;
- `evidence_fingerprint`;
- `method_version`;
- `created_at`.

The baseline ID is deterministic from subject, window, method version, and evidence fingerprint so rebuilds are idempotent. Existing rows are never silently rewritten to represent a different evidence window.
## 8. Baseline dimensions

V1 is deliberately limited to four explainable dimensions.

### Route corridor

Build a robust corridor from historical track points. Store a simplified centerline / corridor representation plus coverage metadata. Assessment reports distance from corridor and whether sufficient historical support exists.

### Speed envelope

Store robust percentiles (for example p05/p25/p50/p75/p95) over valid underway SOG samples. Assessment reports current/episode speed and percentile position. No Gaussian assumption is required.

### Recurring ports / port pairs

Use the existing conservative AIS port-approach derivation. Store recurring ports and ordered port pairs only after a minimum support threshold. Fast transits through approaches do not become port calls.

### AIS silence distribution

Compute observed inter-fix gaps from the same track lineage, with coverage caveats. Store robust percentiles and sample counts. A gap can be `unusual` relative to history but must never be labelled intentional disablement by this layer.
## 9. Minimum history and fail-closed behavior

A baseline is usable only when each dimension has enough support. Minimums must be explicit constants/config, not hidden heuristics.

The top-level assessment is `insufficient_history` when the overall history window or sample count is below the v1 threshold. Individual dimensions may also be unavailable even when others are usable.

Unknown/missing values never become unusual by default. Missing identity, missing port data, or unresolved coverage yields an unavailable dimension plus caveat.

The first implementation should prefer false negatives over manufacturing behavioural certainty from sparse history.
## 10. BehaviourAssessment contract

A `BehaviourAssessment` contains:

- `status`: `expected | unusual | insufficient_history`;
- `baseline_id`;
- `method_version`;
- `reason_codes`;
- per-dimension measurements and thresholds;
- `caveats`;
- `evaluated_at`.

V1 reason codes are limited to:

- `ROUTE_DEVIATION`;
- `UNUSUAL_SPEED_PROFILE`;
- `UNUSUAL_PORT_PAIR`;
- `UNUSUAL_AIS_SILENCE`;
- `INSUFFICIENT_HISTORY`.

`unusual` means at least one supported dimension materially exceeds its historical bound. It does not imply threat, criminality, intent, or case priority.
## 11. Detector integration

AIS-derived producers may request current vessel context/baseline and attach a compact `behaviour_context` block to their observation metadata.

The block may contain `status`, `reason_codes`, `baseline_id`, `method_version`, and the small set of measurements needed to explain the deviation.

Detector integration is advisory only in this packet:

- it may lower confidence in a generic anomaly when behavior is strongly expected;
- it may annotate an anomaly as historically unusual;
- it may not open a Case solely because behavior is unusual;
- it may not publish a same-lineage alert that OSINT Evidence Pipeline v1 keeps internal;
- it may not suppress a high-specificity identity/sanctions fact merely because behavior is expected.

The next `Observation -> Episode -> Hypothesis` packet owns multi-observation reasoning.
## 12. API and operator surfaces

Extend the existing authenticated MDA vessel surface instead of creating a parallel service.

- `GET /api/v1/mda/vessel/{mmsi}` continues to return the existing dossier and gains a `context` section.
- `GET /api/v1/mda/vessel/{mmsi}/baseline` returns the latest usable baseline plus build metadata.
- No new public baseline endpoint in v1.

The existing public `GET /api/v1/live/vessels/{mmsi}/context` must remain privacy-safe and must not expose internal reason codes, historical gaps, identity conflicts, or analyst-only metadata unless explicitly whitelisted by the existing public projection policy.
## 13. YOUR WISDOM regression contract

The existing benign-service fixture remains generic regression evidence, not a production exception.

For a synthetic history representing a recurrent Malta/Gozo fast-ferry service, the baseline should learn a repeated corridor/port pair and normal short reporting gaps. A new in-corridor observation plus a gap within the learned distribution must assess as `expected` or non-actionable, with no intelligence case opened.

A contrastive fixture for the same vessel identity must demonstrate that a material route deviation and/or silence beyond the learned historical bound can assess as `unusual` even though the vessel has ferry/service context.

No code path may special-case `YOUR WISDOM`, MMSI `229113000`, IMO `9848388`, Malta/Gozo, or the ferry class.
## 14. Evidence fingerprint and reproducibility

The baseline evidence fingerprint must be derived from stable, ordered inputs rather than database row IDs alone.

At minimum include subject identity, window bounds, ordered track sample timestamps/positions/speed/nav status/source, derived port-call evidence, and method version.

The builder must produce the same baseline content and ID for the same evidence window and method version. Material track changes or method-version changes produce a different fingerprint/baseline ID.

Raw AIS payload text is not copied into the baseline.
## 15. Build/update lifecycle

V1 uses explicit bounded baseline builds, not a high-frequency scheduler.

A baseline may be built on operator request and from a bounded maintenance command/job for vessels with enough recent history. Rebuilds are idempotent for unchanged evidence.

Production rollout should initially build baselines only for a bounded sample/corpus, verify outputs, then expand. There is no automatic full-fleet backfill in the migration itself.

A stale baseline remains readable but assessment must expose the baseline window end and staleness. Consumers must not pretend an old baseline represents current history.
## 16. Failure handling

- Missing registry data: build context from track/subject evidence that exists and mark missing fields.
- Insufficient track history: return `insufficient_history`; do not synthesize a baseline.
- Port derivation unavailable: route/speed/gap dimensions may still be usable; port dimension is unavailable.
- Evidence fingerprint mismatch: never overwrite an existing baseline under the same ID; build a new version.
- Database failure during baseline persistence: return failure and leave source observations untouched.
- Detector lookup failure: detector continues with its existing observation logic and adds a caveat; behavioural context is assistive, not a single point of failure.

## 17. Privacy and publication constraints

Humanitarian privacy remains authoritative. No baseline or context projection may cause Humanitarian MMSI/IMO/callsign/tracker data to appear on a public Humanitarian surface.

`VesselContext`, behavioural models, and assessments are operator/internal by default. Any future public subset must use an explicit projection whitelist.

Derived context must not be phrased as allegation. `scheduled_service_candidate` means a recurring observed service pattern, not an official schedule unless an independent official schedule source is later introduced.
## 18. Planned components

Expected implementation files:

- `core/mda/vessel_context.py` — deterministic context projection;
- `core/mda/behavioural_baseline.py` — builder, fingerprint, persistence service;
- `core/mda/behaviour_assessment.py` — pure assessment logic;
- `core/db/models.py` — `VesselBehaviouralBaselineDB`;
- Alembic `0020_vessel_behavioural_baselines.py`;
- `core/api/routes/mda.py` — context/baseline operator reads;
- narrowly scoped AIS detector integration in `core/mda/watch.py` and/or canonical AIS anomaly producer;
- tests and synthetic fixtures.

Existing `registry`, `VesselSubject`, `TrackStore`, evidence lineage, fusion, and public projection remain authoritative in their domains.
## 19. TDD contract

Required RED/GREEN coverage before implementation is considered complete:

- deterministic context projection from registry + subject + track history;
- same IMO across usable identity observations resolves to stable subject continuity;
- insufficient-history baseline is refused/fails closed;
- deterministic baseline ID/fingerprint for identical evidence;
- fingerprint and baseline ID change on material evidence change;
- robust speed percentiles ignore malformed samples;
- route corridor marks in-corridor synthetic ferry history expected and contrastive deviation unusual;
- recurring port pair requires repeated qualified calls;
- normal AIS silence vs out-of-distribution silence;
- expected context never suppresses high-specificity sanctions/identity fact;
- unusual assessment alone never opens a Case;
- Humanitarian public projection leaks no vessel identifiers or internal behavioural metadata;
- YOUR WISDOM fixture and contrastive deviation contain no production hard-code.
## 20. Verification and release gates

Before merge:

- full backend test suite;
- focused context/baseline/assessment tests;
- Ruff critical gate and canonical mypy gate;
- Alembic upgrade/downgrade/upgrade for `0019 <-> 0020` where supported by migration tests;
- Humanitarian privacy/publication regressions;
- fusion/triangulation evidence-lineage regressions;
- vessel marker, Live, Play, API, map, simulation suites;
- web lint/typecheck/build;
- edge tests and Wrangler dry-run;
- dependency audits and `git diff --check`;
- exact-head Full CI + CodeQL.

Production rollout requires PostgreSQL backup before migration, migration to `0020`, supervised process restart, `/ready`, operator baseline smoke, Live/Play smoke, and a bounded production baseline audit before any wider backfill.
## 21. Production audit and backfill policy

Migration `0020` creates schema only. It does not build fleet-wide baselines.

After deploy, run an audit-only query to identify vessels with sufficient retained history. Build a small bounded cohort first, including the benign-service regression class and contrastive non-service examples. Inspect baseline windows, sample counts, route geometry, port-pair support, speed/gap percentiles, and assessment outcomes.

Only after that audit is clean may a wider idempotent baseline build be run. The build must be resumable, bounded per batch, and safe to stop. Existing AIS tracks and registry rows are never rewritten.

## 22. Exit criteria

The packet is complete only when:

- vessel context is explainable without a new identity truth store;
- baseline rows are deterministic, versioned, provenance-linked, and reproducible;
- expected/unusual/insufficient-history states are testable and numerically explained;
- YOUR WISDOM-like recurring service behavior does not create an intelligence case merely from normal AIS-derived indicators;
- the same contextual vessel can still be marked unusual on a real behavioural deviation;
- no baseline result alone can allege intent or open a Case;
- OSINT Evidence Pipeline v1 lineage/publication rules remain intact;
- Humanitarian privacy and Live/Play vessel contracts remain regression-clean.