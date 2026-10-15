# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crash-recoverable local write-ahead queue for AIS track positions.

SQLite is a bounded *spool*, not the long-term evidence archive. A row is
acknowledged only after PostgreSQL has committed it together with a durable
batch receipt; a frozen batch has a stable identity across process restarts.
The application must explicitly enable this mode and supply an absolute path
on a persistent local filesystem (never /tmp or ephemeral container storage).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class TrackSpoolFull(RuntimeError):
    """The local safety limit was reached; caller must surface ingestion loss risk."""


@dataclass(frozen=True)
class FrozenBatch:
    batch_id: str
    row_ids: tuple[int, ...]
    rows: tuple[dict[str, Any], ...]
    sha256: str

    @property
    def count(self) -> int:
        return len(self.row_ids)


def _serialize(row: dict[str, Any]) -> str:
    values = {
        k: v.isoformat() if isinstance(v, datetime) else v
        for k, v in row.items()
    }
    return json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _deserialize(payload: str) -> dict[str, Any]:
    row = json.loads(payload)
    for key in ("ts", "received_at"):
        row[key] = datetime.fromisoformat(row[key])
    return row


class SQLiteTrackSpool:
    def __init__(
        self, path: str | Path, *, max_payload_bytes: int = 512 * 1024 * 1024,
        reserved_disk_bytes: int = 2 * 1024 * 1024 * 1024,
        allow_temporary_test_path: bool = False,
    ) -> None:
        self.path = Path(path)
        if not self.path.is_absolute() or (
            "/tmp/" in str(self.path) + "/" and not allow_temporary_test_path
        ):
            raise ValueError("AIS spool requires an absolute, persistent, non-/tmp path")
        if max_payload_bytes <= 0 or reserved_disk_bytes < 0:
            raise ValueError("AIS spool capacity limits must be non-negative")
        self.max_payload_bytes = max_payload_bytes
        self.reserved_disk_bytes = reserved_disk_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)
        created = not self.path.exists()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            self.path, timeout=10, check_same_thread=False,
        )
        if created:
            os.chmod(self.path, 0o600)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        with self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS pending ("
                "seq INTEGER PRIMARY KEY AUTOINCREMENT,"
                "payload TEXT NOT NULL, payload_bytes INTEGER NOT NULL,"
                "batch_id TEXT, enqueued_at REAL NOT NULL DEFAULT 0)"
            )
            fields = {
                col[1] for col in self._conn.execute("PRAGMA table_info(pending)")
            }
            if "enqueued_at" not in fields:
                # An older test/rollout spool may already exist.
                self._conn.execute(
                    "ALTER TABLE pending ADD COLUMN "
                    "enqueued_at REAL NOT NULL DEFAULT 0"
                )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_ais_spool_batch "
                "ON pending(batch_id, seq)"
            )
        count, size, oldest = self._conn.execute(
            "SELECT COUNT(*),COALESCE(SUM(payload_bytes),0),"
            "MIN(enqueued_at) FROM pending"
        ).fetchone()
        self._pending_count = int(count)
        self._pending_payload_bytes = int(size)
        self._oldest_enqueued_at = oldest

    def enqueue(self, row: dict[str, Any]) -> int:
        """Return only after SQLite has durably committed the new fix."""
        payload = _serialize(row)
        size = len(payload.encode("utf-8"))
        with self._lock:
            if self._pending_payload_bytes + size > self.max_payload_bytes:
                raise TrackSpoolFull("AIS spool capacity exceeded; ingestion must alert")
            fs = os.statvfs(self.path.parent)
            free = fs.f_bavail * fs.f_frsize
            if free - size < self.reserved_disk_bytes:
                raise TrackSpoolFull("AIS disk reserve reached; ingestion must alert")
            with self._conn:
                cur = self._conn.execute(
                    "INSERT INTO pending(payload,payload_bytes,batch_id,enqueued_at) "
                    "VALUES (?, ?, NULL, ?)",
                    (payload, size, time.time()),
                )
            self._pending_payload_bytes += size
            self._pending_count += 1
            if self._oldest_enqueued_at is None:
                self._oldest_enqueued_at = time.time()
            return int(cur.lastrowid)

    def claim(self, limit: int = 1000) -> FrozenBatch | None:
        """Freeze one batch; retries always return the identical row set.

        Existing frozen batches take precedence. BEGIN IMMEDIATE prevents two
        processes using the same spool from inventing different batch IDs.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                current = self._conn.execute(
                    "SELECT batch_id FROM pending WHERE batch_id IS NOT NULL "
                    "ORDER BY seq LIMIT 1"
                ).fetchone()
                if current:
                    batch_id = str(current[0])
                else:
                    ids = [
                        int(row[0]) for row in self._conn.execute(
                            "SELECT seq FROM pending WHERE batch_id IS NULL "
                            "ORDER BY seq LIMIT ?", (limit,),
                        ).fetchall()
                    ]
                    if not ids:
                        self._conn.commit()
                        return None
                    batch_id = uuid.uuid4().hex
                    self._conn.executemany(
                        "UPDATE pending SET batch_id=? WHERE seq=? "
                        "AND batch_id IS NULL",
                        [(batch_id, seq) for seq in ids],
                    )
                source = self._conn.execute(
                    "SELECT seq,payload FROM pending WHERE batch_id=? "
                    "ORDER BY seq", (batch_id,),
                ).fetchall()
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

            digest = hashlib.sha256()
            for seq, payload in source:
                digest.update(str(seq).encode("ascii"))
                digest.update(b"\x00")
                digest.update(payload.encode("utf-8"))
                digest.update(b"\n")
            return FrozenBatch(
                batch_id=batch_id,
                row_ids=tuple(int(seq) for seq, _ in source),
                rows=tuple(_deserialize(payload) for _, payload in source),
                sha256=digest.hexdigest(),
            )

    def acknowledge(self, batch: FrozenBatch) -> None:
        """Delete ONLY an already committed PostgreSQL batch, atomically."""
        with self._lock:
            with self._conn:
                current = self._conn.execute(
                    "SELECT COUNT(*),COALESCE(SUM(payload_bytes),0) "
                    "FROM pending WHERE batch_id=?", (batch.batch_id,),
                ).fetchone()
                if int(current[0]) != batch.count:
                    raise RuntimeError("AIS spool ack mismatch: batch remains unacknowledged")
                removed = self._conn.execute(
                    "DELETE FROM pending WHERE batch_id=?", (batch.batch_id,),
                )
                if removed.rowcount != batch.count:
                    raise RuntimeError("AIS spool partial ack: rolling back")
            self._pending_payload_bytes -= int(current[1])
            self._pending_count -= batch.count
            oldest = self._conn.execute(
                "SELECT enqueued_at FROM pending ORDER BY seq LIMIT 1"
            ).fetchone()
            self._oldest_enqueued_at = oldest[0] if oldest else None

    def stats(self) -> dict[str, int]:
        with self._lock:
            oldest_age = max(
                0, int(time.time() - self._oldest_enqueued_at)
            ) if self._oldest_enqueued_at is not None else 0
            return {
                "pending": self._pending_count,
                "pending_payload_bytes": self._pending_payload_bytes,
                "oldest_pending_age_seconds": oldest_age,
                "capacity_bytes": self.max_payload_bytes,
                "disk_reserve_bytes": self.reserved_disk_bytes,
            }

    def close(self) -> None:
        with self._lock:
            self._conn.close()
