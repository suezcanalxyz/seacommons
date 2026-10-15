# SeaCommons storage and ingestion architecture (ADR, 2026-10-15)

**Programme:** #334, Oracle capacity #336, AIS integrity #333, R2 probe #337, log noise #338.  
**Status:** PROPOSED; components require independent review, CI, recovery tests and controlled rollout. This is the target architecture, not a statement that production has migrated.

## Architectural decision

SeaCommons must separate **acquisition reliability**, **hot investigation**, **cold preservation**, and **query delivery**. A single 45 GB Oracle VM cannot be the only durable location for every AIS position, backup and application checkout. No hosting provider supplies unlimited *durable* production storage for free.

```text
AIS and radio adapters + partner feeds
    | observed/received timestamps + upstream/source IDs
    v
validated source-level observation / AIS throttling
    | synchronous durable enqueue (AIS track positions)
    v
SQLite WAL spool on persistent volume (bounded, fsync FULL, disk reserve)
    | frozen batch ID and SHA-256
    v
PostgreSQL: vessel_tracks + vessel_track_ingest_batches receipt
    | one transaction, then acknowledge SQLite
    +--> LIVE / low-latency operational detectors
    +--> PLAY / current and historical investigation metadata
    |
    v  (archive ONLY after approved policy and full restore drill)
Parquet + Zstandard partitions, manifest + SHA-256 + provenance
    |
    v
Cloudflare R2 private object store, independently backed up
    |
    +--> DuckDB / versioned historical queries / verified restore
    +--> PLAY archive reports (no missing window when PG hot data expires)
Futures: reliability, provenance, costs, metrics and availability
```

## P0: accepted-data integrity invariants

1. In the **optional durable-spool mode**, an AIS track fix is considered accepted only after its canonical representation is committed to SQLite with WAL and `synchronous=FULL`. The spool is on a persistent path, never `/tmp`.
2. A batch is frozen under `BEGIN IMMEDIATE`; its ID, member rows and digest survive restarts. A PostgreSQL transaction inserts `vessel_tracks` and a unique batch receipt together. A retry first checks the receipt and hash, preventing duplicate DB rows if a crash happened after the DB commit but before the SQLite acknowledgement.
3. Only after PostgreSQL commit (or matching receipt replay) may the corresponding SQLite batch be acknowledged. SQLite errors preserve pending rows for recovery.
4. A hard configurable backlog limit (initial default 512 MiB **payload**, not full SQLite physical size) and at least 2 GiB free-disk reserve reject new writes loudly instead of silently losing data. Rejection means that exact upstream-message continuity **cannot be guaranteed** without an upstream replay source; configure active alerts and investigate.
5. Prepare/attach durable TrackStore **before starting AIS acquisition**. If that fails, the worker fails startup rather than recording apparently healthy AIS feed activity with no track history.
6. The feature is **disabled by default** until migration, review and fault-injection pass. The existing RAM-only path continues without changed production behavior until explicitly enabled.
7. Batch receipts MUST outlive the recovery window of their corresponding SQLite spool. Never TTL-delete receipts based on age alone. Preserve raw SourceObservation evidence, incident/corroboration records and source attribution independently of the operational track retention.
8. This provides **idempotent PostgreSQL delivery of already accepted track fixes**, not a guarantee that disconnected upstream AIS sources replay all missed radio/network messages.

## Staged rollout: zero unverified deletion

- **Gate A, staging:** GitHub tests, security review and all CI checks green. Use disposable SQLite + PostgreSQL database; inject process death after PostgreSQL commit, after SQLite enqueue, during R2 failure and during capacity exhaustion. Verify row equality, ordering, missing/duplicate counts and alerts.
- **Gate B, migration:** confirmed off-VM backup and restore, PostgreSQL free space and WAL checks. Apply additive Alembic revision `0032_ais_spool_receipts` (or let compatible `create_all` create only the new table). Do not run VACUUM FULL or reindex on a near-full VM.
- **Gate C, worker:** ensure persistent directory is writable and excluded from temp cleanup; configure `SEACOMMONS_AIS_SPOOL_ENABLED=true`, `SEACOMMONS_AIS_SPOOL_PATH=/home/ubuntu/seacommons/shared/ais-track-spool.sqlite3`, `SEACOMMONS_AIS_SPOOL_MAX_BYTES=536870912`, `SEACOMMONS_AIS_SPOOL_DISK_RESERVE_BYTES=2147483648` in the authorized systemd service environment. Restart worker with rollback plan. The API shares an env file in some deployments; opening is lazy so mere API imports do not create another writer.
- **Gate D, monitoring:** record spool pending count/bytes, rejection events, failed/replayed commits, actual SQLite/WAL file size and oldest batch age; alert immediately on rejected ingest or repeated PostgreSQL failures, at 50/75/90% spool capacity, and Oracle volume 70/80/90%.
- **Gate E, recovery:** restart worker in staging with pending data; prove exactly one PostgreSQL commit per accepted fix. Observe production for at least seven days after rollout, with before/after throughput and latency.

## Hot/warm/cold data lifecycle

| Tier | Role | Storage | Policy |
|---|---|---|---|
| Acquisition spool | Accepted, uncommitted AIS fixes | Persistent SQLite on Oracle | Acknowledge ONLY after PG transaction receipt; bounded, alerting |
| Hot data | LIVE/present operational tracks and events | PostgreSQL on Oracle | Window chosen from real LIVE/PLAY query requirements |
| Canonical evidence | Original sourced observations, corroborated records, claims, hashes and provenance | Versioned schema and independently recoverable storage | Preserve under an explicit evidence/legal policy; no automatic TTL |
| Cold analytic archive | Closed immutable historical AIS track partitions | Parquet + Zstandard in private R2 | Append-only manifests, checksums, row counts, time/MMSI ranges |
| Recovery | PG backups, WAL/PITR and R2 object backups | Independent location and access principal | Periodic restore drills; never share a single failure domain |

Do not switch on existing `TrackStore.prune()` solely because the bucket exists: current gzip+JSON output is not a validated immutable Parquet/Zstd archive and its delete/restore semantics are not approved. The default-off guard in #333 should remain until complete; #335 tracks a snapshot/delete concurrency hazard. Successful PUT+GET is necessary but not sufficient for disaster recovery.

## Compression and query acceptance criteria

Benchmark real, authorized, representative AIS tracks by week, sensor source and vessel activity, covering spikes, nullable fields, out-of-order fixes and provenance. Measure bytes per observation including current PG index overhead, Parquet/Zstd bytes, CPU, RAM and DuckDB historical query latency. Do not claim a compression ratio until a reproducible measured sample exists.

An archive segment is eligible for cold commitment only when: canonical schema version + source attribution are present; it has deterministic manifest, content digest and original row count; PUT/GET and decode restore are verified against original rows; duplicate uploads are idempotent; R2 permissions/lifecycle are inspected; and an independent backup has passed a restore test. Deletion from PostgreSQL requires a separately approved retention policy and an explicit fail-closed job, never implicit `older_than_days=60`.

## Oracle capacity and operations

Direct measured baseline Oct 15 before safe cleanup: 45 GiB-class root volume, ~81% used, ~9 GiB free, `/tmp` 4.9 GiB, journald 1.8 GiB, many Git worktrees. Recovery removed 32 **clean checkout directories only** after verifying local branch refs, no modifications and no open file handles: 3,780,169,728 bytes freed. **After:** 73% used, 13.42 GB free. The 30 local-only branch heads were backed up to a single GitHub annotated tag `seacommons-worktree-recovery-20261015`; eight dirty worktrees preserved. Keep the existing forensic log/incident retention until formally approved.

Current 1Hz successful origin /health logging is addressed in draft #338 and cannot be declared fixed before reviewed deployment. The hourly disk metrics cron records capacity and HTTP readiness but sends no verified external alert; verify paging, database freshness, queue backlog and R2 failures. Establish `SystemMaxUse` for journald only after approved incident-log preservation.

## Cost and limitations

Open-source components: PostgreSQL, SQLite, Arrow/Parquet, Zstandard, DuckDB, Prometheus/Grafana (if operational overhead is justified). R2 provides cost-controlled object storage but **not infinite free storage**. Compute forecast at 30/90/365 days using actual ingest and compression benchmarks, R2 operation rates and quota. Supabase Free is suitable for identity and lightweight product metadata, not raw AIS accumulation. IPFS may distribute approved public evidence, but cannot guarantee private long-term persistence without an independently maintained pinning service.

## Definition of done

- Crash and PostgreSQL outage tests demonstrate no duplicate committed rows, no loss of already durably accepted fixes and explicit rejection/alerting when finite buffers fill.
- R2 archive/manifest/restore tests pass on a real isolated canary and then an authorized non-destructive historical sample; immutable provenance remains queryable through PLAY.
- Oracle disk, WAL and backlog growth are tracked and forecast; sustained normal usage <75%, with alerts and >=30 days capacity headroom based on observed growth.
- LIVE, PLAY and Futures are tested with real data; security/review/CI and rollback gates satisfied.
- A seven-day observation period confirms operational stability. Completion is evidence-based, not a PR merge or HTTP 200 alone.
