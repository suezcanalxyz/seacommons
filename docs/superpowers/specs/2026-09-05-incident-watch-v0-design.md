# IncidentWatch v0 Design

**Baseline:** `main` at `ccef5022d220b67d309707e179fc7b264209ec3c`.

**Status:** design only. No production deployment, migration, service restart, or runtime mutation is authorized by this document.

## Purpose

SeaCommons already persists immutable `SourceObservation` records, canonical `HumanitarianIncident` state, lifecycle transitions, current Drift ownership, source coverage metadata, correlation candidates, circular-reporting lineage, and a typed entity graph. The next missing platform primitive is active case follow-up.

`IncidentWatch` makes a Humanitarian incident capable of requesting bounded follow-up collection without allowing the watch itself to change incident truth.

The invariant is:

```text
HumanitarianIncident
  -> IncidentWatch
  -> eligible existing connector/search adapter
  -> new SourceObservation
  -> existing extraction/correlation/incident pipeline
  -> possible incident update / review / resolution / reopening
```

A watch never writes lifecycle, location, people counts, Drift, publication status, correlation decisions, or canonical assessments directly.

## Selected approach

Use a persisted, scheduler-driven watch record that only references existing platform evidence and invokes existing bounded source adapters through narrow watch queries.

This is preferred over:

1. **In-memory watches** — simpler but not restart-safe, not auditable, and not replayable.
2. **A new general search/agent service** — too broad for v0, duplicates the connector subsystem, creates uncontrolled cost and unclear provenance.
3. **Persisted IncidentWatch + bounded adapters** — chosen because it preserves the current evidence architecture, survives restarts, exposes operational state, and can be tested without new paid providers.

## Scope

IncidentWatch v0 is Humanitarian-only.

It covers:

- creating/updating one watch per canonical Humanitarian incident;
- deriving a bounded watch profile from already persisted incident/evidence data;
- lifecycle-aware priority and cadence;
- deterministic due-watch selection;
- invoking only explicitly eligible existing connectors/adapters;
- persisting every newly found source item only through `record_observation()` or the adapter's existing canonical SourceObservation path;
- preventing duplicate queries and retry storms;
- degrading/expiring watches according to canonical incident state;
- operator observability and deterministic tests.

It does not add a new external provider, general web search crawler, LLM search agent, paid API, PostGIS dependency, public UI, or automatic incident mutation.

## Canonical object

Add one durable `IncidentWatchDB` row per Humanitarian incident.

Minimum fields:

```text
watch_id
incident_id
status
priority
lifecycle_snapshot
incident_status_snapshot
profile_json
profile_version
next_run_at
last_run_at
last_success_at
last_error_at
consecutive_errors
run_count
last_query_fingerprint
lease_until
lease_owner
created_at
updated_at
expires_at
```

Recommended values:

```text
status = active | degraded | paused | expired
priority = highest | high | medium | low
```

`incident_id` is unique. Re-syncing an incident updates the watch row rather than creating a second active watch.

`profile_json` is a versioned snapshot of query inputs, not a second incident truth store. `lease_until`/`lease_owner` are execution coordination only, never case state.

## Watch profile

The profile contains only evidence already associated with the incident or explicitly derived from it:

```text
schema_version
incident_id
source_thread_ids[]
source_item_ids[]
source_names[]
coordinates[]
uncertainty_m
named_places[]
route_terms[]
departure_terms[]
destination_terms[]
people_min
people_max
vessel_description_terms[]
actor_names[]
keywords[]
language_hints[]
source_observation_ids[]
profile_method_version
```

Rules:

- no MMSI/IMO/callsign is inferred from a Humanitarian incident;
- no vessel identity is added unless already linked by explicit evidence and allowed by internal policy;
- exact sensitive Humanitarian coordinates remain internal and are passed only to adapters whose policy permits them;
- absent evidence stays absent; the profile never invents route, people count, language, or vessel details;
- profile regeneration is deterministic from the same persisted inputs.

## Lifecycle and compatibility policy

Watch scheduling reads both canonical `incident_status` and `lifecycle`. `incident_status` wins when the two encode different migration-era semantics.

This is required because current SeaCommons can persist a silent unresolved case as:

```text
incident_status=outcome_unknown
lifecycle=archived
```

That combination means “outcome unknown and retired from Live”, not “stop follow-up forever”. IncidentWatch must not treat it as an explicit resolved archive.

Policy:

```text
incident_status=active OR lifecycle in {reported, active, reopened}
  priority=highest
  cadence target=15 minutes

incident_status=needs_review OR lifecycle=needs_review
  priority=high
  cadence target=30 minutes

incident_status=outcome_unknown OR lifecycle=unresolved_stale
  priority=medium
  cadence target=2 hours for first 7 days since last update
  cadence target=12 hours for days 7-30
  expire dedicated polling after 30 days unless reopened

incident_status=resolved OR lifecycle=resolved, age <=24h
  priority=high
  cadence target=1 hour

resolved age >24h and <=7d
  priority=medium
  cadence target=12 hours

resolved age >7d and <=30d
  priority=low
  cadence target=24 hours

explicit archived state with known outcome, or resolved/outcome-known age >30d
  status=expired
  no dedicated polling
```

The scheduler may run more frequently than these cadences, but it selects only watches whose `next_run_at <= now` and whose lease is absent/expired.

A lifecycle/status change re-synchronizes priority, expiry policy and `next_run_at`. It does not delete prior run history.

## Connector boundary

IncidentWatch does not call arbitrary HTTP endpoints itself.

Introduce a narrow watch capability on top of existing adapters, conceptually:

```python
class WatchQuery:
    incident_id: str
    profile: dict
    since: datetime | None
    budget: int

class WatchResult:
    source_name: str
    source_items_seen: int
    observations_created: int
    observations_replayed: int
    checkpoint: str | None
    error_class: str | None
```

An adapter is eligible only if it explicitly declares watch support. Unsupported adapters are skipped, never guessed.

For v0, use only adapters already present in the repository whose existing acquisition semantics can accept a bounded follow-up query without introducing a new scraping architecture. A connector migration is not bundled into this feature.

## SourceObservation authority

Every discovered item must enter through the existing canonical source boundary.

No watch code may directly create:

- `IntelEventDB` as the only record of a new source item;
- `HumanitarianIncidentDB` updates;
- lifecycle transitions;
- claims or assessments;
- correlation decisions;
- Drift jobs;
- public Live features.

The watch calls an adapter, the adapter records the source item through its existing `SourceObservation` path, and the existing downstream pipeline remains responsible for interpretation.

Duplicate collection is harmless because SourceObservation remains idempotent by stable source identity.

## Query deduplication and budgets

A watch adapter execution has a deterministic query fingerprint derived from:

```text
profile_version
eligible adapter id
query-relevant normalized profile fields
bounded time window
```

The same fingerprint must not execute twice inside its cadence window. `last_query_fingerprint` records the most recently attempted fingerprint; detailed per-run audit can remain structured logging in v0 rather than introducing a second run-history table.

Per-run safeguards:

```text
max adapters per watch run: 3
max newly accepted source observations per watch run: 25
max execution time per adapter: existing connector timeout, never increased globally
max consecutive errors before degraded: 3
```

A degraded watch remains eligible at a slower retry cadence and must not spin in a tight loop.

A failing connector never marks the incident resolved, empty, stale, archived, or reviewed.

## Scheduling and leases

Reuse the existing background scheduling infrastructure rather than introducing another worker framework in v0.

Add one bounded scheduler job that:

1. selects due active/degraded watches in priority order;
2. atomically claims a small batch using a short `lease_until`/`lease_owner`;
3. executes one watch at a time in v0;
4. records run state and errors;
5. clears/advances the lease on completion;
6. calculates the next run from current canonical incident state;
7. exits cleanly when there are no due watches.

The lease protects against accidental duplicate execution if scheduler instances overlap or a deployment briefly has more than one process. An expired lease is reclaimable after a crash.

The scheduler must not perform long unbounded work on the FastAPI event loop. Existing synchronous/network adapter behaviour should use the repository's established isolation pattern rather than blocking async request handling.

## Watch creation and synchronization

A watch is synchronized from the canonical Humanitarian incident after incident persistence succeeds.

Rules:

- non-Humanitarian events never create watches;
- one incident has at most one watch;
- creating a watch is idempotent;
- an event/thread update refreshes the profile and cadence of the same watch;
- resolved/outcome-unknown/archived transitions update watch policy immediately;
- incident synchronization continues to succeed if watch synchronization fails; the watch path is best-effort and observable, not allowed to break ingestion.

## Correlation semantics

A watch result is not proof that a new observation belongs to the incident.

Existing correlation rules remain authoritative:

```text
new SourceObservation
  -> candidate generation
  -> CorrelationDecision
  -> SAME_INCIDENT / RELATED_INCIDENT / NEW_INCIDENT / UNCERTAIN
```

v0 must not silently merge a cross-source follow-up into an incident merely because the watch query that found it originated from that incident.

The watch origin may be stored as provenance such as:

```json
{
  "collection_trigger": "incident_watch",
  "watch_id": "...",
  "candidate_incident_id": "..."
}
```

but this is candidate context, not a correlation decision.

## Privacy and safety

Humanitarian privacy rules remain unchanged and precede watch convenience.

- no public endpoint exposes watch profiles;
- watch profiles are operator/internal only;
- exact location evidence is never copied into public output by the watch layer;
- no migrant interception, border-enforcement targeting, military targeting, or commercial surveillance workflow is introduced;
- no professional-vessel dossier is inferred from Humanitarian evidence;
- source terms/licence and preservation policy remain enforced by the adapter/SourceObservation layer.

## Observability

Add an operator-only audit endpoint returning aggregate and per-watch operational state without raw sensitive source text.

Minimum fields:

```text
watch_id
incident_id
status
priority
lifecycle_snapshot
incident_status_snapshot
next_run_at
last_run_at
last_success_at
consecutive_errors
run_count
profile_version
eligible_adapter_names[]
lease_until
```

Add metrics/logging sufficient to answer:

- how many watches are active/degraded/expired;
- how many are overdue;
- which adapters fail most often;
- observations created versus replayed;
- watch-run latency;
- whether one watch is repeatedly executing the same fingerprint;
- whether any lease remains stuck beyond its expiry.

## Persistence and migration

Use one additive Alembic migration for `incident_watches`.

Requirements:

- SQLite-test compatible;
- PostgreSQL-safe;
- migration revision identifier <= 32 characters;
- reversible downgrade;
- unique `incident_id` constraint;
- indexes justified by actual query paths: `(status, next_run_at, priority)` plus unique `incident_id` are sufficient for v0.

No destructive migration and no production mutation in the implementation PR.

## Failure semantics

Failures are local to the watch run.

```text
adapter timeout/rate limit/5xx
  -> record failure class
  -> increment consecutive_errors
  -> schedule bounded retry/backoff
  -> do not change incident truth

malformed source item
  -> adapter rejects/quarantines it under existing rules
  -> watch continues within budget

SourceObservation DB failure
  -> adapter/watch run reports error
  -> no fallback direct IntelEvent write added for the watch

scheduler/process restart
  -> persisted next_run_at/run state survives
  -> expired lease becomes reclaimable
  -> due watch is retried idempotently
```

## Test contract

The implementation is not complete until tests prove at least:

1. Humanitarian active incident creates exactly one watch.
2. Re-syncing the same incident updates the watch, never duplicates it.
3. Maritime Safety/Intelligence events never create IncidentWatch rows.
4. Same incident history produces the same watch profile/fingerprint.
5. Missing evidence is omitted rather than invented.
6. Lifecycle/status changes deterministically change priority/cadence.
7. `incident_status=outcome_unknown` remains follow-up eligible even when compatibility `lifecycle=archived` is present.
8. Explicitly expired/old resolved incidents receive no dedicated polling.
9. Scheduler selects only due/unleased watches and respects priority.
10. An active lease prevents duplicate selection; an expired lease is reclaimable.
11. One failing adapter does not mutate incident state.
12. A discovered item is persisted through canonical SourceObservation semantics.
13. Replaying the same discovered source item creates no duplicate observation.
14. Watch provenance does not force `SAME_INCIDENT`; normal correlation authority remains intact.
15. Query fingerprint prevents duplicate runs within a cadence window.
16. Three consecutive adapter failures degrade the watch and back off.
17. Migration upgrade -> downgrade -> re-upgrade is green on SQLite and schema matches model metadata.
18. Full backend suite and ruff are green on the exact PR head.
19. No public Humanitarian projection gains MMSI/IMO/callsign or watch-profile fields.

## Expected implementation boundaries

Likely new files:

```text
apps/api/core/intel/incident_watch.py
apps/api/core/db/migrations/versions/<short_revision>_incident_watch.py
apps/api/tests/test_incident_watch.py
```

Likely modified files:

```text
apps/api/core/db/models.py
apps/api/core/intel/humanitarian_incident.py
apps/api/core/scheduler.py
apps/api/core/api/routes/audit.py
apps/api/tests/test_alembic_migrations.py
```

Only add adapter-specific changes when an existing adapter can support the bounded watch query cleanly. Each materially different adapter integration should remain a separate reviewable follow-up packet if it expands scope.

## Release gate

IncidentWatch v0 may merge only when:

- migration roundtrip is green;
- targeted deterministic watch tests are green;
- full backend suite and ruff are green;
- watch execution cannot directly mutate canonical incident truth;
- no duplicate polling loop is introduced;
- public privacy regression tests remain green;
- CI is green on the exact head SHA;
- no deploy, DB migration, or production restart is included in the PR.

After merge, production rollout remains a separate operator-approved action.
