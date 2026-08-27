# Testing strategy

This document describes what the SeaCommons test suites protect and why. It is
the Phase 7 deliverable of the production-hardening roadmap: a deliberate
testing pyramid plus an explicit map from the highest-risk system flows to the
executable tests that guard them.

The guiding rule is behavioural, not numerical: tests exist to lock in
correctness and safety invariants before refactors, not to chase a coverage
percentage. When a canonical design document and a test disagree, the test
wins until one of them is fixed.

## Pyramid

| Layer | Runner | Location | Count | Scope |
| --- | --- | --- | --- | --- |
| Backend unit + domain invariants | `pytest` | `tests/` | 217 | connectors, normalization, lifecycle, public/private policy, projection, drift kernel, observability |
| Backend API / integration | `pytest` (FastAPI `TestClient`) | `tests/test_live_feed.py`, `tests/test_security.py`, `tests/test_live_resolved_visibility.py` | (subset of above) | route auth, feed shape, resolved-visibility across the HTTP boundary |
| Edge realtime | `node --test` | `apps/edge/src/*.test.js` | 13 | Durable Object state, delivery semantics, restart/reconnect, trust-boundary validation, environment config |
| Frontend domain / service | `node --test` | `apps/web/src/**/*.test.js` | 23 | response normalization, API client error handling, drift scene model, simulation engine |

Run everything the way CI does:

```bash
# backend
python -m pytest -q

# edge
cd apps/edge && npm test

# frontend
cd apps/web && npm test
```

There is no Playwright layer yet. Critical browser flows are currently covered
indirectly through the frontend domain/service tests and the edge integration
tests; an end-to-end layer is tracked as remaining roadmap work.

## The ten highest-risk flows

Each flow below is a place where a regression would either fabricate data,
leak private operational content, or silently corrupt incident lifecycle. Every
row names the tests that must fail if the behaviour breaks.

### 1. Ingest a verified incident

- **Risk:** unofficial or unverified sources entering the operational record;
  fabricated coordinates.
- **Tests:**
  - `tests/test_connectors.py::test_alarm_phone_screenshot_dmm_and_noisy_dms_are_parsed`
  - `tests/test_connectors.py::test_direct_distress_call_classifier_is_conservative`
  - `tests/test_connectors.py::test_media_ocr_requires_numeric_consensus`
  - `tests/test_connectors.py::test_relative_alarm_phone_location_is_geolocated_with_declared_offset`
  - `tests/test_security.py::test_partner_whatsapp_connector_and_signed_webhook`
  - `tests/test_security.py::test_accepts a correctly signed collector request` /
    `::test_rejects a collector request with an invalid signature`

### 2. Publish to Live

- **Risk:** an event reaching the public Live map without an explicit publish
  decision, or a blocked-policy source being exposed because it was flagged
  distress.
- **Tests:**
  - `tests/test_public_policy.py::test_vm_and_edge_paths_agree_on_the_two_privacy_absolute_rules`
  - `tests/test_public_policy.py::test_blocked_source_policy_never_reaches_the_edge_even_if_flagged_distress`
  - `tests/test_live_feed.py::test_manual_event_requires_explicit_publication`
  - `tests/test_live_feed.py::test_row_without_distress_flag_or_explicit_publication_is_not_exported`
  - `tests/test_live_feed.py::test_computed_sar_products_never_enter_received_signal_feed`
  - `apps/edge/src/live.test.js::"drops malformed events at the edge trust boundary"`

### 3. Update an existing incident

- **Risk:** a material change not producing a new version; a stale delayed
  update overwriting a newer observation.
- **Tests:**
  - `tests/test_live_edge_publisher.py::test_material_update_gets_new_version_id`
  - `tests/test_live_edge_publisher.py::test_existing_event_can_be_enriched_with_media_location`
  - `tests/test_live_edge_publisher.py::test_enrich_location_clears_stale_area_on_upgrade_to_a_real_point`
  - `tests/test_live_edge_publisher.py::test_db_duplicate_repoints_live_event_to_canonical_id`
  - `apps/edge/src/live.test.js::"an out-of-order observation cannot replace a newer incident version"`
  - `apps/edge/src/live.test.js::"replaces stale drift features when an operator event update arrives"`

### 4. Resolve an incident

- **Risk:** lifecycle recomputed from stale status instead of source text;
  rescue mentions inside an ongoing pushback wrongly resolving an incident.
- **Tests:**
  - `tests/test_connectors.py::test_lifecycle_recomputes_from_text_instead_of_trusting_stale_incident_status`
  - `tests/test_connectors.py::test_self_reply_marks_the_incident_resolved_without_keyword_overlap`
  - `tests/test_connectors.py::test_resolved_distress_ignores_a_rescue_mention_inside_an_ongoing_pushback`
  - `tests/test_connectors.py::test_unsafe_rescue_reply_does_not_resolve_the_incident`
  - `tests/test_live_resolved_visibility.py::test_alarm_phone_self_reply_resolution_leaves_live_immediately`
  - `apps/edge/src/live.test.js::"restart retains the removal tombstone and reconnect snapshot"` (resolution persists across restart)

### 5. Remove a resolved incident from operational Live

- **Risk:** a resolved incident returning to active Live after a retry;
  drift products for a resolved incident still rendering.
- **Tests:**
  - `tests/test_live_resolved_visibility.py::test_concluded_report_is_resolved_and_removed_from_operational_live`
  - `tests/test_live_resolved_visibility.py::test_stale_unresolved_report_turns_archived_not_removed`
  - `tests/test_live_resolved_visibility.py::test_event_past_the_live_window_is_marked_for_removal`
  - `tests/test_drift_trajectory.py::test_drift_not_shown_for_resolved_or_archived_incidents`
  - `tests/test_live_edge_publisher.py::test_removed_payload_is_a_valid_incident_removed_event`
  - `apps/edge/src/live.test.js::"restart retains the removal tombstone and reconnect snapshot"`

### 6. Drift simulation

- **Risk:** non-spatiotemporal or speedless trajectories published as
  operational SAR products; antimeridian corruption; time desynchronization.
- **Tests:**
  - `tests/test_drift_trajectory.py::test_live_only_publishes_spatiotemporal_opendrift_with_speed_samples`
  - `tests/test_drift_trajectory.py::test_representative_path_preserves_all_times_and_handles_antimeridian`
  - `tests/test_drift_trajectory.py::test_trajectory_properties_include_physical_speed_time_and_curvature`
  - `tests/test_drift_trajectory.py::test_forcing_units_and_direction_are_converted_to_opendrift_vectors`
  - `tests/test_drift_scene.py` (deterministic scene model)
  - `apps/web/src/features/drift/sceneModel.test.js`

### 7. Provider / upstream failure

- **Risk:** stale source health interpreted as fresh data; a proxy HTML error
  surfacing as application JSON; a dead provider silently dropping the feed.
- **Tests:**
  - `tests/test_aisstream_health.py::test_separates collector heartbeat health from event recency`
  - `tests/test_observability.py::test_publisher_heartbeat_is_separate_from_event_delivery`
  - `tests/test_live_feed.py::test_live_feed_merges_durable_alarm_phone_events_after_memory_eviction`
  - `apps/web/src/services/api/client.test.js::"does not expose an HTML proxy error as application JSON"`
  - `tests/test_drift_trajectory.py::test_public_demo_drift_has_explicit_degraded_fallback`

### 8. Reconnect after a realtime interruption

- **Risk:** missed events on reconnect; duplicate delivery on replay; head-hash
  divergence after a process restart.
- **Tests:**
  - `apps/edge/src/live.test.js::"duplicate delivery is idempotent and broadcasts only once"`
  - `apps/edge/src/live.test.js::"restart retains the removal tombstone and reconnect snapshot"`
  - `tests/test_live_edge_publisher.py::test_outbox_survives_reopen_and_remembers_delivery`
  - `tests/test_live_edge_publisher.py::test_was_ever_delivered_tracks_by_incident_not_exact_version`
  - `apps/web/src/features/live/normalize.test.js` (snapshot normalization)

### 9. Unauthorized operational access

- **Risk:** operational mutations reachable without a validated token; default
  roles applied before token validation; production booting without OIDC.
- **Tests:**
  - `tests/test_security.py::test_production_fails_closed_without_oidc`
  - `tests/test_security.py::test_oidc_default_roles_apply_only_after_token_validation`
  - `tests/test_security.py::test_live_routes_remain_public_when_internal_reads_require_auth`
  - `tests/test_security.py::test_public_demo_allows_simulation_but_blocks_operational_mutations`
  - `tests/test_security.py::test_public_play_simulation_is_bounded_while_workspace_mutations_require_auth`
  - `tests/test_security.py::test_telegram_rejects_wrong_secret`

### 10. Public / private publication boundary

- **Risk:** private operational content in the public projection; an explicit
  private status being overridden by an approved source policy.
- **Tests:**
  - `tests/test_public_policy.py::test_explicitly_private_overrides_everything_else`
  - `tests/test_public_policy.py::test_explicit_private_status_overrides_approved_source_policy`
  - `tests/test_live_feed.py::test_public_projection_excludes_sensitive_content`
  - `tests/test_live_feed.py::test_sensitive_public_position_is_stable_and_approximate`
  - `tests/test_live_feed.py::test_user_signal_is_private_by_default`
  - `tests/test_live_contracts.py::test_invalid_legacy_public_values_fail_closed`

## Cross-runtime contract tests

Three suites exist specifically to stop the Python core, the JSON Schema
catalogue and the Cloudflare edge from drifting apart:

- `tests/test_live_contracts.py` — canonical lifecycle / precision vocabulary,
  fail-closed projection.
- `tests/test_runtime_contracts.py` — `test_live_domain_schema_matches_backend_enums`,
  `test_normalized_federated_event_matches_shipped_schema`.
- `apps/edge/src/live.test.js` — `"preserves lifecycle and explicit area precision from the edge"`.

## Remaining gaps

- No browser end-to-end (Playwright) layer; the ten flows above are covered at
  the domain/service/edge level only.
- Runtime-level concurrent / multi-region edge replay needs a Miniflare
  integration harness; the current edge suite uses an in-memory Durable Object
  harness covering deterministic state transitions and persisted
  restart/reconnect behaviour.
- Frontend React component tests are minimal by design; presentation components
  are treated as low-risk relative to the domain layer.
