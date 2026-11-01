# PostgreSQL backup / R2 release gate

This procedure does **not** authorize a production deployment. Do not delete PostgreSQL data, WAL, evidence, or pre-existing R2 objects.

The opt-in script `scripts/backup_pg_to_r2_quarantined.py` performs a read-only, low-priority `pg_dump` streamed to R2. Without `--execute`, it performs a preflight only. It refuses to run under high CPU load/PSI or low RAM/disk headroom, and aborts an in-progress dump on sustained pressure. The default stream cap is 2 MiB/s with 8 MiB multipart chunks, backpressuring PostgreSQL rather than running the dump at maximum throughput. The cap can be adjusted with `--max-stream-mib-per-sec` (0 < rate <= 16), but no throughput or successful backup is guaranteed. Never bypass resource guards to force a release.

A streamed dump first lands under `seacommons/backups/pending/`. This location is **untrusted**, including when a multipart upload has completed. Only after `pg_dump` exits successfully, enough bytes are produced, and a separate remote read matches the producer's SHA-256 and length does the script write a JSON attestation under `seacommons/backups/byte-verified/`.

The attestation explicitly says `checksum_verified_restore_pending` and `restore_drill_done=false`. Neither a pending dump nor a byte-verified attestation is deploy-ready. A failed upload, terminated producer, checksum mismatch or failed attestation write remains untrusted. The script never deletes such artifacts automatically.

## Required independent restore drill

1. Confirm the exact object key, expected SHA-256, byte length and creation time from the attestation. Do not accept a key solely because it appears under a historical `full/` prefix.
2. On a **separate isolated host** with adequate free disk and no connection to production, download the object, compute SHA-256 and byte count independently, and compare with the attestation. Reject mismatches.
3. Validate the custom archive with `pg_restore --list`. Restore into a **new, isolated PostgreSQL database** with a compatible PostgreSQL version; never target production or a database containing evidence.
4. Check the restored schema, critical tables, representative rows, constraints, and counts against the backup snapshot. Record a timestamped result, checksum, restore commands, PostgreSQL version and exit statuses. Do not log secrets.
5. Rehearse application rollback and verify API, humanitarian cases, maritime episodes, geometry and provenance after rollback. Only then can the release gate be considered for opening.

Existing historical dumps and the earlier resource-aborted dump are not automatically trusted by this procedure. A checksum match alone cannot demonstrate that PostgreSQL can be restored.
