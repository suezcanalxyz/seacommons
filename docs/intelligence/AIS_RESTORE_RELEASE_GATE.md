# AIS archive/restore release gate — 2026-11-08

Relates #431 #335 #336 #367. Risk: GREEN documentation/test specification only. **This document does not authorize retention or destructive operations.**

## Research question and tradecraft
Can a canonical `TrackStore.prune()` archive be proven *recoverable and semantically equivalent* after PUT/GET and PostgreSQL faults, rather than merely byte-consistent? Intelligence evidence-preservation tradecraft requires reproducible chain of custody, negative controls and independently checkable recovery. This is a proposed experiment, not an observed production capability.

## Primary-source evidence / decision
- PostgreSQL, *Explicit Locking*: https://www.postgresql.org/docs/current/explicit-locking.html (accessed 2026-11-08; PostgreSQL License; locks protect concurrent updates only while the transaction holds them; ADOPT).
- PostgreSQL, *Transactions*: https://www.postgresql.org/docs/current/tutorial-transactions.html (accessed 2026-11-08; PostgreSQL License; rollback cannot undo an external object-store PUT; ADOPT).
- Amazon S3, *Checking object integrity*: https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html (accessed 2026-11-08; AWS documentation, proprietary terms; S3-compatible providers may differ; PILOT against configured object store).
- Python, *gzip*: https://docs.python.org/3/library/gzip.html (accessed 2026-11-08; PSF License; decompression must be bounded by caller; ADOPT for adversarial fixtures).

## Baseline / competing hypotheses
Observed in default-branch `apps/api/core/vessels/track_store.py`: `_RETENTION_RELEASE_AUTHORIZED = False`; existing prune archive path uses object store and PostgreSQL. Existing PR #453 adds disposable PostgreSQL concurrency tests but is stacked on #452; do not equate these with a complete canonical restore drill. Alternative hypotheses: a correct hash with malformed records; a successful PUT with failed DB transaction; concurrent writer mutation; a valid gzip archive with unsafe expansion; a stale object GET; duplicate restore.

## Disposable integration benchmark (acceptance contract)
1. Use disposable PostgreSQL and disposable S3-compatible bucket/prefix only. Explicit test ACK required. Seed representative fixes including nullable fields and same-MMSI temporal neighbors; snapshot canonical rows in stable order.
2. Execute the *actual* canonical prune/archive path with retention-release guard unchanged in production. Any test-only override must be isolated from production configuration and require a disposable-DB assertion.
3. Confirm object HEAD/GET, full payload SHA-256, schema validation, unique IDs, row counts, timestamps, coordinates and nullable fields; restore to a clean disposable table and compare canonical row equality (not just count/hash).
4. Hard negatives: concurrent update while selected rows are locked; PUT failure; GET failure; checksum mismatch; invalid schema; duplicate IDs; gzip expansion beyond configured test budget; rollback after DELETE; restore replay/idempotency; expired or missing object.
5. Failure invariant: if durable archive verification or row equivalence cannot be proven, original DB rows remain; no evidence deletion. Assert no changes to humanitarian data, public incident attribution, or LIVE geometry.
6. Report runtime, peak memory, object bytes, restored-row count, false-success count (target zero), and observed PostgreSQL/object-store costs. Record exact command, environment, commit SHA and CI job URL. Until measured, all metrics = **not observed**.

## Release decision and rollback
- This documentation-only change is GREEN and reversible by revert.
- Actual retention enablement is AMBER/RED depending on destructive implications and requires separate authorization, backup and restore proof. Do not set `AIS_PRUNE_APPROVED` or bypass `_RETENTION_RELEASE_AUTHORIZED`.
- Auto-release already-written code only when exact-head required checks and applicable E2E pass, stacked PR dependencies are reconciled, and deployment provider reports success. Verify public URL and smoke after deploy; rollback by provider rollback/revert on regression. Test-only changes may not alter public UI.
- Next implementation: disposable PostgreSQL + S3-compatible fault-injection harness invoking the canonical prune and restore code; do not create a second archival implementation.

Capability: evidence recoverability = **experimental / not yet demonstrated end-to-end**; live release = **not verified**.
