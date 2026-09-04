# Production release runbook

docs/fixes.md M13. This is a documented operational procedure, not code
-- follow it manually (or automate against it later) when cutting a
SeaCommons release. Nothing in this document is enforced by CI; it exists
so the deploy sequence and rollback policy are written down once,
consistently, rather than reconstructed from memory each release.

## PR-required checks (already enforced, `.github/workflows/ci.yml`)

Every PR against `main` already blocks on: backend pytest (full suite,
which includes the M12 replay scenario catalogue,
`tests/test_replay_scenarios.py`, and the publication-policy contract
tests, `tests/test_publication_policy.py` -- both run unconditionally, so
"replay subset relevant to changed lane" and "privacy/publication
contract when projection touched" are satisfied by the full suite being a
superset of either), ruff (critical-correctness gate), migration safety
(`db migrations apply cleanly` against a fresh database on every PR,
regardless of whether that PR itself touches a migration), web lint,
typecheck, web tests, and web build. No new PR gate was needed for this
list; it was already complete.

## Nightly / extended checks (`.github/workflows/nightly.yml`)

Scheduled daily (03:00 UTC) plus manual dispatch: full replay corpus, full
backend suite, the alert-recognition scorer report (historical corpus +
AIS behaviour/integrity, printed to the job log), a migration dry-run
against a fresh database, and a Drift-maintenance dry-run report
(`core.intel.backfill_drift_maintenance.run(apply=False)`, M8) -- stuck/
invalid Drift rows are counted and reported, never written, in this
nightly step.

Not yet automated in this workflow (needs a real deployed environment to
run against, not CI's own fresh/empty database): migration/backfill
dry-run against a **sanitized production DB snapshot**, and edge/VM
parity fixtures compared against a live edge deployment. Both stay manual
until that environment access exists.

## Production deploy sequence

Follow in order. Each step should be confirmed complete before starting
the next; stop and do not proceed past a failed step.

1. **Backup DB / verify migration head.** Confirm the current production
   `alembic_version` matches what this release expects to upgrade from,
   and that a recent backup/snapshot exists and is restorable.
2. **Deploy code with compatibility reads.** The new code must be able to
   read data written by the *previous* release's schema/write path --
   every M1-M9 addition this cycle (SourceObservation, LocationEvidence
   extensions, episodes, hypotheses, publication policy) is additive-only
   and none has replaced an existing write path yet, so this step should
   be a no-op risk-wise for this release; confirm that remains true for
   whatever is actually being deployed.
3. **Run migrations.** `alembic upgrade head` against production. Every
   migration in this codebase to date is additive (new tables/columns,
   `checkfirst`-guarded against `0001_baseline`'s own `create_all`) except
   `0004_lossless_event_ids`, which is explicitly widening-only and
   documents why its downgrade is blocked.
4. **Run bounded backfill/replay checks.** `core.intel.backfill_drift_maintenance.run(apply=False)`
   first (dry-run counts); only re-run with `apply=True` once the counts
   look sane for the current production state. Same posture for any other
   backfill command in scope for the release.
5. **Verify source freshness.** Check `INTEL_SOURCES`/`INTEL_SOURCE_EVENTS`
   (`core.observability`) or the equivalent `/health/data` summary
   (`core.observability_health.build_data_health_summary`, M11) once
   that route exists -- no source should show `down`/`unknown` immediately
   post-deploy.
6. **Verify Humanitarian Live representative records.** Spot-check a
   handful of real Humanitarian Live records against
   `core.intel.publication_policy.project_public_humanitarian()`'s rules:
   no MMSI/IMO/dossier fields, no raw private text, lifecycle and location
   precision both present.
7. **Verify Safety lane.** Confirm neutral Safety records still publish
   without requiring a hypothesis (`project_public_safety`) and that
   `is_auto_drift_eligible()` still rejects every non-`sar`-domain record.
8. **Verify no unreviewed Intelligence allegation is public.** Every
   published Maritime Intelligence item must trace back to an
   `InvestigationHypothesis` that passed `can_publish()` (M6) --
   spot-check that `project_public_maritime_assessed()` is the only path
   Intelligence content reaches a public projection through.
9. **Verify workers and edge queues.** Confirm worker heartbeats are
   fresh (`WORKERS` gauge) and the live-edge outbox/heartbeat gauges
   (`LIVE_OUTBOX_DEPTH`, `LIVE_EDGE_HEARTBEAT_OK`) show a healthy,
   draining queue, not a growing backlog.
10. **Record release SHA + scorer/replay report.** Attach the deployed
    commit SHA and this release's nightly scorer/replay report (or a
    fresh manual run of the same two, if deploying off-schedule) to the
    release record.

## Rollback

Roll back **application reads/writes only** -- deploy the previous
release's code against the *same*, already-migrated database. Never run
a downgrade migration as part of a rollback unless the specific migration
being rolled back is explicitly reversible (check its own `downgrade()`;
several in this codebase, e.g. `0004_lossless_event_ids`, refuse to
downgrade by design) and the rollback has been separately decided to need
it.

**New evidence tables are never deleted as part of a rollback.**
`source_observations` (M1.1), the `drift_results.origin_evidence_id`/
`model_version` columns (M3), and any future evidence table stay in
place, append-only, even while the application temporarily stops writing
to or reading from them. Retaining that data is exactly what lets a later
forward-fix recover state a straight `DROP TABLE`/data-deleting rollback
would have destroyed.
