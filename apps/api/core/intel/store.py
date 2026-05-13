# SPDX-License-Identifier: AGPL-3.0-or-later
"""
In-memory event store for intel events.

Holds up to MAX_EVENTS events in a deque (newest first).
Deduplication via a content-hash set.
WebSocket clients are stored as (websocket, asyncio.loop) tuples so
broadcast() can be called from background threads.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_EVENTS = 600
DEDUP_WINDOW = 2000  # max unique hashes kept in memory


@dataclass
class IntelEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Event classification
    type: str = ""        # twitter | news | iom_incident | ais_spike | ngo_activity
    severity: str = ""   # critical | high | medium | low

    # Geography
    lat: Optional[float] = None
    lon: Optional[float] = None

    # Content
    title: str = ""
    text: str = ""
    url: str = ""
    source: str = ""      # e.g. "alarm__phone", "IOM", "MarineTraffic"
    author: str = ""

    # Cross-references
    linked_mmsi: str = ""   # if this event correlates to a known vessel

    # Free-form extras (incident counts, vessel names, etc.)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_geojson_feature(self) -> dict[str, Any]:
        geo = (
            {"type": "Point", "coordinates": [self.lon, self.lat]}
            if self.lat is not None and self.lon is not None
            else None
        )
        return {
            "type": "Feature",
            "geometry": geo,
            "properties": {
                "id": self.id,
                "type": self.type,
                "severity": self.severity,
                "title": self.title,
                "text": self.text,
                "url": self.url,
                "source": self.source,
                "author": self.author,
                "linked_mmsi": self.linked_mmsi,
                "timestamp_utc": self.timestamp_utc,
                **self.metadata,
            },
        }

    def content_hash(self) -> str:
        """Stable dedup key based on source + core content."""
        raw = f"{self.source}:{self.title}:{self.text[:120]}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]


class IntelStore:
    def __init__(self, maxlen: int = MAX_EVENTS) -> None:
        self._events: deque[IntelEvent] = deque(maxlen=maxlen)
        self._seen: set[str] = set()
        self._lock = threading.Lock()
        # (websocket_obj, asyncio_loop) — loop needed for thread-safe sends
        self._ws_clients: set[tuple[Any, asyncio.AbstractEventLoop]] = set()

    # ── Write ─────────────────────────────────────────────────────────────────

    def add(self, event: IntelEvent, dedup_key: str = "") -> bool:
        """
        Add an event.  Returns True if stored, False if duplicate.
        Thread-safe.
        """
        key = dedup_key or event.content_hash()
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            if len(self._seen) > DEDUP_WINDOW:
                # Keep the newest half
                self._seen = set(list(self._seen)[DEDUP_WINDOW // 2 :])
            self._events.appendleft(event)

        self._fire_broadcast(event)
        self._persist(event)
        # Auto-queue drift for high/critical events with known coordinates
        if event.severity in ("critical", "high") and event.lat is not None and event.lon is not None:
            self._queue_auto_drift(event)
        return True

    def _queue_auto_drift(self, event: IntelEvent) -> None:
        """Enqueue drift computation for a geolocated high-priority event."""
        import threading
        threading.Thread(target=self._run_auto_drift, args=(event,), daemon=True).start()

    def _run_auto_drift(self, event: IntelEvent) -> None:
        try:
            from core.scheduler import _compute_drift_for_event
            _compute_drift_for_event(event)
        except Exception as exc:
            logger.warning("Auto-drift failed for event %s: %s", event.id, exc)

    def _persist(self, event: IntelEvent) -> None:
        """Write event to DB in a background thread — never blocks the caller."""
        import threading
        threading.Thread(target=self._persist_sync, args=(event,), daemon=True).start()

    def _persist_sync(self, event: IntelEvent) -> None:
        try:
            from core.db.session import session_scope
            from core.db.models import IntelEventDB
            with session_scope() as db:
                db.add(IntelEventDB(
                    id=event.id,
                    timestamp_utc=event.timestamp_utc,
                    type=event.type,
                    severity=event.severity,
                    lat=event.lat,
                    lon=event.lon,
                    title=event.title[:255],
                    text=event.text,
                    url=event.url[:511],
                    source=event.source,
                    linked_mmsi=event.linked_mmsi,
                    meta=event.metadata,
                ))
        except Exception as exc:
            logger.debug("Intel DB persist skipped: %s", exc)

    # ── Read ──────────────────────────────────────────────────────────────────

    def events(
        self,
        severity: Optional[str] = None,
        type_filter: Optional[str] = None,
        limit: int = 200,
    ) -> list[IntelEvent]:
        with self._lock:
            evts = list(self._events)
        if severity:
            evts = [e for e in evts if e.severity == severity]
        if type_filter:
            evts = [e for e in evts if e.type == type_filter]
        return evts[:limit]

    def geojson(
        self,
        severity: Optional[str] = None,
        type_filter: Optional[str] = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        features = [
            e.to_geojson_feature()
            for e in self.events(severity, type_filter, limit)
            if e.lat is not None and e.lon is not None
        ]
        return {
            "type": "FeatureCollection",
            "features": features,
            "meta": {
                "total": len(features),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            evts = list(self._events)
        by_type: dict[str, int] = {}
        by_sev: dict[str, int] = {}
        for e in evts:
            by_type[e.type] = by_type.get(e.type, 0) + 1
            by_sev[e.severity] = by_sev.get(e.severity, 0) + 1
        return {
            "total": len(evts),
            "by_type": by_type,
            "by_severity": by_sev,
        }

    # ── WebSocket broadcast ───────────────────────────────────────────────────

    def register_ws(self, ws: Any, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._ws_clients.add((ws, loop))

    def unregister_ws(self, ws: Any) -> None:
        with self._lock:
            self._ws_clients = {(w, l) for w, l in self._ws_clients if w is not ws}

    def broadcast_event_update(self, event_id: str, update: dict) -> None:
        """Push a lightweight update packet to all WS clients (e.g. drift completed)."""
        payload = json.dumps({"type": "event_update", "id": event_id, **update})
        with self._lock:
            clients = list(self._ws_clients)
        for ws, loop in clients:
            try:
                asyncio.run_coroutine_threadsafe(_ws_send(ws, payload), loop)
            except Exception:
                pass

    def _fire_broadcast(self, event: IntelEvent) -> None:
        """
        Non-blocking: schedule coroutine in each registered loop.
        Called from background threads after a successful add().
        """
        payload = json.dumps(event.to_geojson_feature())
        dead: list[Any] = []
        with self._lock:
            clients = list(self._ws_clients)
        for ws, loop in clients:
            try:
                asyncio.run_coroutine_threadsafe(
                    _ws_send(ws, payload), loop
                )
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister_ws(ws)


async def _ws_send(ws: Any, payload: str) -> None:
    try:
        await ws.send_text(payload)
    except Exception:
        pass


# ── Module-level singleton ────────────────────────────────────────────────────
intel_store = IntelStore()
