# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistent best-effort publisher from the SeaCommons intel DB to Live edge.

Designed for 1 GB Oracle micro instances:
- no additional broker is required;
- a small SQLite outbox survives restarts and network failures;
- delivery is idempotent because the edge deduplicates event IDs;
- private/non-operational material is never exported by default.

Run with:
    python -m core.live_edge_publisher
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import signal
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("seacommons.live_edge_publisher")


@dataclass(frozen=True)
class PublisherSettings:
    edge_url: str
    ingest_secret: str
    node_id: str
    outbox_path: Path
    poll_seconds: float = 15.0
    batch_size: int = 25
    request_timeout_seconds: float = 12.0
    max_attempts: int = 20

    @classmethod
    def from_env(cls) -> "PublisherSettings":
        return cls(
            edge_url=os.getenv("LIVE_EDGE_INGEST_URL", "").rstrip("/"),
            ingest_secret=os.getenv("LIVE_EDGE_INGEST_SECRET", ""),
            node_id=os.getenv("SEACOMMONS_NODE_ID", os.uname().nodename),
            outbox_path=Path(os.getenv("LIVE_EDGE_OUTBOX_PATH", "./shared/live-edge-outbox.db")),
            poll_seconds=float(os.getenv("LIVE_EDGE_POLL_SECONDS", "15")),
            batch_size=max(1, int(os.getenv("LIVE_EDGE_BATCH_SIZE", "25"))),
            request_timeout_seconds=float(os.getenv("LIVE_EDGE_TIMEOUT_SECONDS", "12")),
            max_attempts=max(1, int(os.getenv("LIVE_EDGE_MAX_ATTEMPTS", "20"))),
        )

    def validate(self) -> None:
        if not self.edge_url:
            raise RuntimeError("LIVE_EDGE_INGEST_URL is required")
        if not self.ingest_secret:
            raise RuntimeError("LIVE_EDGE_INGEST_SECRET is required")


class Outbox:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending (
                event_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL DEFAULT 0,
                last_error TEXT
            );
            CREATE INDEX IF NOT EXISTS pending_ready_idx
                ON pending(next_attempt_at, created_at);
            """
        )
        self.connection.commit()

    def get_cursor(self) -> str:
        row = self.connection.execute("SELECT value FROM state WHERE key='cursor'").fetchone()
        return str(row["value"]) if row else ""

    def set_cursor(self, value: str) -> None:
        self.connection.execute(
            "INSERT INTO state(key,value) VALUES('cursor',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (value,),
        )
        self.connection.commit()

    def enqueue(self, event_id: str, payload: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO pending(event_id,payload,created_at) VALUES(?,?,?)",
            (event_id, json.dumps(payload, separators=(",", ":"), sort_keys=True), now_iso()),
        )
        self.connection.commit()

    def ready(self, limit: int) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                "SELECT * FROM pending WHERE next_attempt_at <= ? "
                "ORDER BY created_at ASC LIMIT ?",
                (time.time(), limit),
            ).fetchall()
        )

    def acknowledge(self, event_id: str) -> None:
        self.connection.execute("DELETE FROM pending WHERE event_id=?", (event_id,))
        self.connection.commit()

    def fail(self, event_id: str, attempts: int, error: str, max_attempts: int) -> None:
        capped_attempts = min(attempts, max_attempts)
        delay = min(3600.0, 2 ** min(capped_attempts, 11))
        self.connection.execute(
            "UPDATE pending SET attempts=?, next_attempt_at=?, last_error=? WHERE event_id=?",
            (attempts, time.time() + delay, error[:500], event_id),
        )
        self.connection.commit()

    def counts(self) -> dict[str, int]:
        total = self.connection.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
        failed = self.connection.execute("SELECT COUNT(*) FROM pending WHERE attempts > 0").fetchone()[0]
        return {"pending": int(total), "retrying": int(failed)}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def public_event_from_row(row: Any, node_id: str) -> dict[str, Any] | None:
    metadata = dict(getattr(row, "meta", None) or {})
    event_type = str(getattr(row, "type", "") or "")
    severity = str(getattr(row, "severity", "") or "")
    is_distress = bool(metadata.get("is_distress")) or event_type in {"distress", "iom_incident"}
    explicitly_public = metadata.get("publication_state") in {"public", "published"}
    if not is_distress and not explicitly_public:
        return None

    lat = getattr(row, "lat", None)
    lon = getattr(row, "lon", None)
    geometry = None
    if lat is not None and lon is not None:
        geometry = {"type": "Point", "coordinates": [float(lon), float(lat)]}

    confidence = metadata.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    properties = {
        "severity": severity,
        "title": str(getattr(row, "title", "") or ""),
        "text": str(getattr(row, "text", "") or ""),
        "verification_status": metadata.get("verification_status", "unverified_public_source"),
        "coordinate_source": metadata.get("coordinate_source"),
        "radius_m": metadata.get("radius_m"),
        "resolved": bool(metadata.get("resolved")),
        "archived": bool(metadata.get("archived")),
        "persons": metadata.get("persons"),
        "linked_mmsi": str(getattr(row, "linked_mmsi", "") or ""),
    }
    properties = {key: value for key, value in properties.items() if value not in (None, "")}

    return {
        "schema": "seacommons-event-v1",
        "id": str(getattr(row, "id")),
        "type": "distress_observation" if is_distress else event_type,
        "source": str(getattr(row, "source", "") or "unknown"),
        "node": node_id,
        "observed_at": str(getattr(row, "timestamp_utc", "") or now_iso()),
        "visibility": "public",
        "confidence": confidence,
        "geometry": geometry,
        "properties": properties,
        "source_url": str(getattr(row, "url", "") or "") or None,
    }


def signature(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


class LiveEdgePublisher:
    def __init__(self, settings: PublisherSettings) -> None:
        settings.validate()
        self.settings = settings
        self.outbox = Outbox(settings.outbox_path)
        self.running = True
        self.client = httpx.Client(timeout=settings.request_timeout_seconds)

    def stop(self, *_: Any) -> None:
        self.running = False

    def collect(self) -> int:
        """Copy new eligible DB rows into the durable local outbox."""
        from core.db.models import IntelEventDB
        from core.db.session import session_scope

        cursor = self.outbox.get_cursor()
        added = 0
        newest_cursor = cursor
        with session_scope() as db:
            query = db.query(IntelEventDB).order_by(IntelEventDB.timestamp_utc.asc())
            if cursor:
                query = query.filter(IntelEventDB.timestamp_utc > cursor)
            rows = query.limit(self.settings.batch_size * 4).all()
            for row in rows:
                newest_cursor = max(newest_cursor, str(row.timestamp_utc or ""))
                payload = public_event_from_row(row, self.settings.node_id)
                if payload is None:
                    continue
                self.outbox.enqueue(payload["id"], payload)
                added += 1
        if newest_cursor and newest_cursor != cursor:
            self.outbox.set_cursor(newest_cursor)
        return added

    def deliver(self) -> int:
        delivered = 0
        for row in self.outbox.ready(self.settings.batch_size):
            body = str(row["payload"])
            try:
                response = self.client.post(
                    self.settings.edge_url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-SeaCommons-Signature": signature(self.settings.ingest_secret, body),
                        "User-Agent": f"SeaCommons-Node/{self.settings.node_id}",
                    },
                )
                if response.status_code in {200, 202}:
                    self.outbox.acknowledge(str(row["event_id"]))
                    delivered += 1
                    continue
                raise RuntimeError(f"edge HTTP {response.status_code}: {response.text[:200]}")
            except Exception as exc:
                attempts = int(row["attempts"]) + 1
                self.outbox.fail(
                    str(row["event_id"]), attempts, str(exc), self.settings.max_attempts
                )
                logger.warning("Live edge delivery failed for %s: %s", row["event_id"], exc)
        return delivered

    def run(self) -> None:
        logger.info("Live edge publisher started for node %s", self.settings.node_id)
        while self.running:
            try:
                added = self.collect()
                delivered = self.deliver()
                if added or delivered:
                    logger.info(
                        "Live edge cycle: collected=%d delivered=%d outbox=%s",
                        added,
                        delivered,
                        self.outbox.counts(),
                    )
            except Exception:
                logger.exception("Live edge publisher cycle failed")
            time.sleep(self.settings.poll_seconds)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    publisher = LiveEdgePublisher(PublisherSettings.from_env())
    signal.signal(signal.SIGTERM, publisher.stop)
    signal.signal(signal.SIGINT, publisher.stop)
    publisher.run()


if __name__ == "__main__":
    main()
