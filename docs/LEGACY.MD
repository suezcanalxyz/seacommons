LEGACY REMOVAL / ARCHITECTURE CLEANUP

A major goal of this refactor is to reduce legacy complexity.

Do NOT preserve old code paths automatically.

Before implementing new architecture, identify all legacy compatibility layers, deprecated routes, duplicate schemas, fallback fields, wrapper objects, old frontend adapters, obsolete feature flags and dead data transformations.

For each legacy element, classify it as:

A. REQUIRED
Still actively used by a current production consumer.

B. TEMPORARY COMPATIBILITY
Still used, but can be migrated during this refactor.

C. DEAD LEGACY
No active consumer and safe to remove.

D. UNKNOWN
Usage cannot be verified yet.

Do not keep category C.

Do not keep category D by default.
Investigate it first.

The desired final state is ONE canonical implementation for each concept.

Avoid patterns such as:

new_schema
+ old_schema
+ compatibility_schema
+ fallback_schema

when all internal consumers can be migrated to the new schema.

--------------------------------------------------
1. REMOVE LEGACY, DO NOT STACK NEW CODE ON TOP
--------------------------------------------------

Do not solve architecture problems by adding another abstraction layer above old behavior.

Bad:

old MDA event
→ legacy wrapper
→ correlation wrapper
→ new normalized wrapper
→ frontend adapter

Preferred:

raw source
→ canonical normalized model
→ API projection
→ frontend

Remove intermediate legacy layers where they no longer provide necessary behavior.

--------------------------------------------------
2. ONE CANONICAL MODEL
--------------------------------------------------

For each major entity, establish one canonical internal model.

Examples:

Vessel
HumanitarianCase
SourceObservation
MaritimeSecuritySignal
SourceHealth

Do not maintain multiple internal representations of the same entity unless there is a strong technical reason.

External serialization may differ, but internal truth should remain singular.

--------------------------------------------------
3. MIGRATE INTERNAL CONSUMERS FIRST
--------------------------------------------------

If an old field or route exists only because internal frontend/backend code still consumes it:

update those consumers.

Do not keep the old API forever just to avoid touching internal code.

Example:

if frontend still expects:

status = "distress"

for every Live event,

do not preserve this incorrect semantic mapping.

Update the frontend to understand the canonical event type/status model.

--------------------------------------------------
4. DELETE DEAD ROUTES
--------------------------------------------------

Audit all Live API routes.

For every route determine:

- active production usage
- frontend usage
- external usage
- test usage
- documentation usage

If a route has no confirmed consumer and duplicates newer functionality, remove it.

Do not leave deprecated endpoints indefinitely.

If temporary migration is required:

1. mark deprecated explicitly
2. migrate known consumers
3. remove deprecated route in the same refactor if possible

Avoid open-ended deprecation.

--------------------------------------------------
5. REMOVE DUPLICATE EVENT PATHS
--------------------------------------------------

Pay special attention to duplicate MDA / sanctions event representations.

If the same underlying event currently exists as:

raw finding
+
fused event
+
correlated alert
+
Live projection

determine which object should be canonical.

Do not expose all representations to downstream systems.

Maintain one canonical event identity and one projection path.

--------------------------------------------------
6. REMOVE LEGACY SANCTIONS EVENTS
--------------------------------------------------

If sanctions are migrated to vessel enrichment:

remove legacy recurring sanctions-event generation where it no longer has a distinct semantic purpose.

Do not maintain both:

sanctioned vessel as persistent event

and

sanctions property on vessel

unless the event represents a real state transition such as:

new sanctions match
sanctions status changed
sanctions removed

--------------------------------------------------
7. REMOVE FALLBACK MAGIC
--------------------------------------------------

Find and remove dangerous fallback behavior such as:

missing coordinates → 0,0

unknown event type → distress

unknown domain → humanitarian

missing vessel identity → generic duplicate object

unknown source health → active

Fallbacks must not silently invent meaning.

Prefer:

null
unknown
unavailable

and handle these states explicitly.

--------------------------------------------------
8. REMOVE OBSOLETE TAXONOMY
--------------------------------------------------

Audit old domain/status/type values.

Examples may include:

grey_zone
distress used generically
legacy sanctions domain
old MDA labels

Keep internal specialist terminology only where it is still meaningful.

Do not expose obsolete taxonomy through new APIs merely for compatibility.

Create an explicit migration mapping and then remove obsolete usage internally.

--------------------------------------------------
9. FEATURE FLAGS
--------------------------------------------------

Audit all feature flags related to Live/MDA/Humanitarian behavior.

Remove flags that:

- are permanently enabled
- are permanently disabled
- protect code paths no longer used
- refer to completed migrations

A feature flag should represent an actual current runtime choice, not historical archaeology.

--------------------------------------------------
10. DEAD CODE
--------------------------------------------------

After migration, remove:

- unused functions
- unused imports
- dead adapters
- unused serializers
- obsolete tests
- old schema definitions
- commented-out implementations
- duplicate helper functions
- unused config keys
- stale environment-variable references

Do not leave commented legacy implementations in the repository.

Git history already preserves them.

--------------------------------------------------
11. TEST THE NEW CANONICAL PATH
--------------------------------------------------

Tests should target the canonical architecture.

Do not preserve obsolete tests purely because they encode legacy behavior.

If a test asserts incorrect old semantics, replace it.

Example:

OLD TEST:
AIS gap status == distress

should be removed/replaced if the new canonical behavior is:

domain == maritime_security
type == ais_gap

--------------------------------------------------
12. EXTERNAL COMPATIBILITY EXCEPTION
--------------------------------------------------

Only retain compatibility when there is confirmed external dependency.

If an external consumer exists:

document:

- consumer
- deprecated field/route
- migration requirement
- removal condition

Keep compatibility at the API boundary only.

Do not allow compatibility requirements to contaminate the core internal model.

Preferred architecture:

canonical internal model
→ optional legacy API serializer

NOT:

legacy model
→ new model
→ legacy model again

--------------------------------------------------
13. NO "JUST IN CASE" LEGACY
--------------------------------------------------

Do not keep old code because it "might be useful".

Every retained legacy component must have a documented active consumer or migration reason.

If no reason exists, delete it.

--------------------------------------------------
14. REQUIRED LEGACY AUDIT
--------------------------------------------------

Before modifying code, produce a table:

Legacy component
File/function
Current purpose
Confirmed consumer
Replacement
Risk of removal
Action

Action must be one of:

KEEP
MIGRATE
DELETE
INVESTIGATE

After implementation, provide a second table showing the final result.

--------------------------------------------------
15. DELETION BUDGET
--------------------------------------------------

This refactor is allowed and expected to delete code.

Do not optimize for minimum diff size if that leaves duplicated architecture.

Optimize for minimum conceptual complexity.

Prefer:

-20 obsolete files/functions
+5 canonical implementations

over:

+15 adapters
+10 compatibility layers
0 deletions

provided behavior and required external compatibility are preserved.

--------------------------------------------------
16. STOP CONDITIONS
--------------------------------------------------

Do not delete something when:

- there is confirmed active external usage
- its usage cannot yet be determined
- removal would destroy historical data
- it is required for rollback during an unfinished migration

In these cases, report the blocker explicitly instead of silently retaining everything.

--------------------------------------------------
17. FINAL CLEANUP PASS
--------------------------------------------------

After all migrations:

search the repository again for:

- deprecated field names
- deprecated endpoint names
- old event type strings
- old domain strings
- old feature flags
- compatibility helpers
- old frontend selectors
- obsolete config keys

The refactor is not complete while stale references remain unintentionally.

--------------------------------------------------
FINAL PRINCIPLE

Do not build SeaCommons v2 on top of SeaCommons v1.

Migrate SeaCommons v1 into the new canonical architecture, then remove the obsolete architecture.

The final repository should be easier to understand than before the refactor.