# SPDX-License-Identifier: AGPL-3.0-or-later
"""Low-memory live publisher from SeaCommons intel state to the edge.

The operational mode is deliberately live-first:
- no historical backfill is required;
- recent rows are rescanned so location/status enrichments are published;
- each material state version gets a deterministic event ID;
- a SQLite outbox survives short network failures;
- delivered versions are remembered locally to avoid repeated sends.

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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("seacommons.live_edge_publisher")

# Same block list as core/api/routes/live.py's VM-hosted public feed. Kept as
# a local copy (not an import) so this low-memory publisher process never
# pulls in FastAPI — but the values must stay identical: a record blocked on
# the VM standby path must never leak through the primary edge path instead.
_BLOCKED_SOURCE_POLICIES = frozenset({"nitter", "scrape", "twscrape", "unofficial"})


@dataclass(frozen=True)
class PublisherSettings:
    edge_url: str
    ingest_secret: str
    node_id: str
    outbox_path: Path
    poll_seconds: float = 1.0
    batch_size: int = 25
    scan_limit: int = 200
    # Must comfortably exceed lifecycle.DISTRESS_LIVE_MAX_AGE_DAYS (7 days) so
    # an event stays inside the scan long enough to receive its final
    # "expired" removal at the true 7-day boundary, plus margin for a
    # same-source resolution post to still be seen before that.
    live_window_minutes: int = 8 * 24 * 60
    request_timeout_seconds: float = 8.0
    max_attempts: int = 20

    @classmethod
    def from_env(cls) -> "PublisherSettings":
        return cls(
            edge_url=os.getenv("LIVE_EDGE_INGEST_URL", "").rstrip("/"),
            ingest_secret=os.getenv("LIVE_EDGE_INGEST_SECRET", ""),
            node_id=os.getenv("SEACOMMONS_NODE_ID", os.uname().nodename),
            outbox_path=Path(os.getenv("LIVE_EDGE_OUTBOX_PATH", "./shared/live-edge-outbox.db")),
            poll_seconds=max(0.5, float(os.getenv("LIVE_EDGE_POLL_SECONDS", "1"))),
            batch_size=max(1, int(os.getenv("LIVE_EDGE_BATCH_SIZE", "25"))),
            scan_limit=max(10, int(os.getenv("LIVE_EDGE_SCAN_LIMIT", "200"))),
            live_window_minutes=max(5, int(os.getenv("LIVE_EDGE_WINDOW_MINUTES", str(8 * 24 * 60)))),
            request_timeout_seconds=float(os.getenv("LIVE_EDGE_TIMEOUT_SECONDS", "8")),
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
            CREATE TABLE IF NOT EXISTS pending (
                event_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at REAL NOT NULL DEFAULT 0,
                last_error TEXT
            );
            CREATE TABLE IF NOT EXISTS delivered (
                event_id TEXT PRIMARY KEY,
                delivered_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS pending_ready_idx
                ON pending(next_attempt_at, created_at);
            CREATE INDEX IF NOT EXISTS delivered_at_idx
                ON delivered(delivered_at);
            """
        )
        self.connection.commit()

    def enqueue(self, event_id: str, payload: dict[str, Any]) -> bool:
        if self.connection.execute(
            "SELECT 1 FROM delivered WHERE event_id=?", (event_id,)
        ).fetchone():
            return False
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO pending(event_id,payload,created_at) VALUES(?,?,?)",
            (event_id, json.dumps(payload, separators=(",", ":"), sort_keys=True), now_iso()),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def was_ever_delivered(self, incident_id: str) -> bool:
        """Whether any version of this incident was ever actually sent.

        Used to decide whether a row that no longer qualifies for the
        public feed needs an explicit removal pushed -- most excluded rows
        (AIS spikes, private reports) were never published in the first
        place and don't need one; only a row that flips from published to
        excluded (e.g. a duplicate later marked private) does.
        """
        return self.connection.execute(
            "SELECT 1 FROM delivered WHERE event_id LIKE ? LIMIT 1",
            (f"{incident_id}:%",),
        ).fetchone() is not None

    def ready(self, limit: int) -> list[sqlite3.Row]:
        return list(
            self.connection.execute(
                "SELECT * FROM pending WHERE next_attempt_at <= ? "
                "ORDER BY created_at ASC LIMIT ?",
                (time.time(), limit),
            ).fetchall()
        )

    def acknowledge(self, event_id: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM pending WHERE event_id=?", (event_id,))
            self.connection.execute(
                "INSERT OR REPLACE INTO delivered(event_id,delivered_at) VALUES(?,?)",
                (event_id, now_iso()),
            )

    def fail(self, event_id: str, attempts: int, error: str, max_attempts: int) -> None:
        capped_attempts = min(attempts, max_attempts)
        delay = min(300.0, 2 ** min(capped_attempts, 8))
        self.connection.execute(
            "UPDATE pending SET attempts=?, next_attempt_at=?, last_error=? WHERE event_id=?",
            (attempts, time.time() + delay, error[:500], event_id),
        )
        self.connection.commit()

    def prune(self, retention_hours: int = 48) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=retention_hours)).isoformat()
        self.connection.execute("DELETE FROM delivered WHERE delivered_at < ?", (cutoff,))
        self.connection.commit()

    def counts(self) -> dict[str, int]:
        total = self.connection.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
        failed = self.connection.execute("SELECT COUNT(*) FROM pending WHERE attempts > 0").fetchone()[0]
        return {"pending": int(total), "retrying": int(failed)}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _version_id(incident_id: str, payload: dict[str, Any]) -> str:
    material = json.dumps(
        {
            "type": payload.get("type"),
            "geometry": payload.get("geometry"),
            "confidence": payload.get("confidence"),
            "properties": payload.get("properties"),
            "source_url": payload.get("source_url"),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    version = hashlib.sha256(material.encode()).hexdigest()[:20]
    return f"{incident_id}:{version}"


def _event_from_row(row: Any) -> "IntelEvent":
    from core.intel.store import IntelEvent

    return IntelEvent(
        id=str(getattr(row, "id")),
        timestamp_utc=str(getattr(row, "timestamp_utc", "") or ""),
        type=str(getattr(row, "type", "") or ""),
        severity=str(getattr(row, "severity", "") or ""),
        lat=getattr(row, "lat", None),
        lon=getattr(row, "lon", None),
        title=str(getattr(row, "title", "") or ""),
        text=str(getattr(row, "text", "") or ""),
        url=str(getattr(row, "url", "") or ""),
        source=str(getattr(row, "source", "") or ""),
        linked_mmsi=str(getattr(row, "linked_mmsi", "") or ""),
        metadata=dict(getattr(row, "meta", None) or {}),
    )


def public_event_from_row(
    row: Any,
    node_id: str,
    *,
    now: datetime,
    same_source: list[Any],
) -> dict[str, Any] | None:
    """Build an edge payload with the SAME lifecycle semantics as the VM's
    public /api/v1/live/signals feed (core/api/routes/live.py) — both paths
    import core.intel.lifecycle so a marker can never look "resolved" on one
    and "still active" on the other.
    """
    from core.intel import lifecycle

    event = _event_from_row(row)
    metadata = event.metadata
    event_type = event.type
    # Operator-only marker (same semantics as the VM's public live feed):
    # news/archive channels (e.g. official RSS) mark their rows "private" so an
    # NGO article that merely mentions distress vocabulary can never surface on
    # the public live map.
    publication_status = str(metadata.get("publication_status") or "").lower()
    if publication_status == "private":
        return None
    # Defense in depth, same as the VM path: a blocked source policy (legacy
    # scraper rows, unofficial transport) must never reach the public map even
    # if `publication_status`/`is_distress` were ever set incorrectly upstream.
    source_policy = str(metadata.get("source_policy") or "").lower()
    transport = str(metadata.get("via") or metadata.get("scrape_source") or "").lower()
    if source_policy in _BLOCKED_SOURCE_POLICIES or any(
        blocked in transport for blocked in _BLOCKED_SOURCE_POLICIES
    ):
        return None
    is_distress = bool(metadata.get("is_distress")) or event_type in {"distress", "iom_incident"}
    # NOTE: previously checked a "publication_state" key that no producer in
    # this codebase ever sets (a typo for publication_status) — this branch
    # was therefore dead: it never once evaluated True in production. Only
    # `is_distress` was ever actually gating inclusion.
    explicitly_public = publication_status == "published"
    if not is_distress and not explicitly_public:
        return None

    from core.intel.public_geometry import public_geometry_and_precision

    incident_id = event.id
    geometry, location_precision = public_geometry_and_precision(event)

    confidence = metadata.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    # expired: past the 7-day total Live window — the edge must purge it
    # outright. incident_lifecycle (active/resolved/archived) governs color
    # for anything still inside that window; it never triggers removal.
    expired = is_distress and not lifecycle.is_within_live_window(event, now=now)
    incident_lifecycle = (
        lifecycle.distress_lifecycle(event, now=now, same_source=same_source)
        if is_distress else None
    )
    # Same redaction as the VM's public feed (core/api/routes/live.py,
    # _public_intel_feature): only the tracked account's own reply fields —
    # never the event's private-caller-sourced `text` (already blanked
    # above) or anything else from thread_reposts.
    thread_reposts = metadata.get("thread_reposts")
    repost_count = metadata.get("repost_count")
    properties = {
        "incident_id": incident_id,
        "severity": event.severity,
        "title": event.title,
        "text": event.text,
        "verification_status": metadata.get("verification_status", "unverified_public_source"),
        "coordinate_source": metadata.get("coordinate_source"),
        "radius_m": metadata.get("location_uncertainty_m"),
        "incident_lifecycle": incident_lifecycle,
        "expired": expired,
        "persons": metadata.get("persons"),
        "linked_mmsi": event.linked_mmsi,
        "last_source_seen_at": metadata.get("last_source_seen_at"),
        "repost_count": repost_count,
        "thread_reposts": [
            {"tweet_id": r.get("tweet_id"), "posted_at": r.get("posted_at"),
             "url": r.get("url"), "kind": r.get("kind"), "note": r.get("note")}
            for r in thread_reposts
        ] if thread_reposts else None,
        "location_precision": location_precision,
        "area_weather_narrowed": metadata.get("area_weather_narrowed"),
    }
    properties = {key: value for key, value in properties.items() if value not in (None, "")}

    payload: dict[str, Any] = {
        "schema": "seacommons-event-v1",
        "type": "incident_removed" if expired else (
            "distress_observation" if is_distress else event_type
        ),
        "source": event.source or "unknown",
        "node": node_id,
        "observed_at": event.timestamp_utc or now_iso(),
        "visibility": "public",
        "confidence": confidence,
        "geometry": geometry,
        "properties": properties,
        "source_url": event.url or None,
    }
    payload["id"] = _version_id(incident_id, payload)
    return payload


def removed_payload(incident_id: str, node_id: str, *, source: str = "unknown") -> dict[str, Any]:
    """A synthetic incident_removed payload for a row still inside the scan
    window but no longer eligible for the public feed (e.g. flipped to
    private after being published) -- without this the edge keeps serving
    whatever version it last received forever, since it never re-scans
    anything itself; collect() is the only thing that ever revisits a row.
    """
    payload: dict[str, Any] = {
        "schema": "seacommons-event-v1",
        "type": "incident_removed",
        "source": source,
        "node": node_id,
        "observed_at": now_iso(),
        "visibility": "public",
        "confidence": None,
        "geometry": None,
        "properties": {"incident_id": incident_id},
        "source_url": None,
    }
    payload["id"] = _version_id(incident_id, payload)
    return payload


def signature(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


class LiveEdgePublisher:
    def __init__(self, settings: PublisherSettings) -> None:
        settings.validate()
        self.settings = settings
        self.outbox = Outbox(settings.outbox_path)
        self.running = True
        self.client = httpx.Client(timeout=settings.request_timeout_seconds)
        self.cycles = 0

    def stop(self, *_: Any) -> None:
        self.running = False

    def collect(self) -> int:
        """Rescan only the live window and enqueue unseen material versions.

        Two queries, not one: a high-volume, non-distress source (AIS spike
        detection can post dozens of rows per cycle) would otherwise crowd
        genuine distress reports out of a single "most recent N" scan. The
        second query is exempt from that noise so a real report is never
        starved out of the window by spike volume.
        """
        from core.db.models import IntelEventDB
        from core.db.session import session_scope
        from core.intel import lifecycle

        cutoff = (datetime.now(timezone.utc) - timedelta(
            minutes=self.settings.live_window_minutes
        )).isoformat()
        now = datetime.now(timezone.utc)
        added = 0
        with session_scope() as db:
            general = (
                db.query(IntelEventDB)
                .filter(IntelEventDB.timestamp_utc >= cutoff)
                .order_by(IntelEventDB.timestamp_utc.desc())
                .limit(self.settings.scan_limit)
                .all()
            )
            distress_bearing = (
                db.query(IntelEventDB)
                .filter(IntelEventDB.timestamp_utc >= cutoff)
                .filter(IntelEventDB.type != "ais_spike")
                .order_by(IntelEventDB.timestamp_utc.desc())
                .limit(self.settings.scan_limit)
                .all()
            )
            by_id = {row.id: row for row in general}
            by_id.update({row.id: row for row in distress_bearing})
            rows = list(by_id.values())
            events = [_event_from_row(row) for row in rows]
            by_source: dict[str, list[Any]] = {}
            for event in events:
                by_source.setdefault(event.source, []).append(event)
            for row in reversed(rows):
                same_source = by_source.get(str(getattr(row, "source", "") or ""), [])
                payload = public_event_from_row(row, self.settings.node_id, now=now, same_source=same_source)
                if payload is not None:
                    if self.outbox.enqueue(payload["id"], payload):
                        added += 1
                    continue
                # Row is still within the scan window but no longer public
                # (e.g. a duplicate later marked private) -- if the edge was
                # ever actually sent a version of it, it needs an explicit
                # removal, or it keeps showing the last version forever.
                if self.outbox.was_ever_delivered(row.id):
                    removal = removed_payload(row.id, self.settings.node_id, source=str(row.source or "unknown"))
                    if self.outbox.enqueue(removal["id"], removal):
                        added += 1
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
        logger.info(
            "Live-first edge publisher started node=%s poll=%.2fs window=%dm",
            self.settings.node_id,
            self.settings.poll_seconds,
            self.settings.live_window_minutes,
        )
        while self.running:
            started = time.monotonic()
            try:
                added = self.collect()
                delivered = self.deliver()
                self.cycles += 1
                if self.cycles % 3600 == 0:
                    self.outbox.prune()
                if added or delivered:
                    logger.info(
                        "Live edge cycle: collected=%d delivered=%d outbox=%s",
                        added,
                        delivered,
                        self.outbox.counts(),
                    )
            except Exception:
                logger.exception("Live edge publisher cycle failed")
            remaining = self.settings.poll_seconds - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)


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
