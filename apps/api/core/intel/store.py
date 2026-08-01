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
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_COORDINATE_SOURCE_RANK = {
    "none": 0,
    "place_centroid": 1,
    "relative_place_offset": 2,
    "media_ocr_consensus": 3,
    "media_ocr_text": 3,
    "post_text": 4,
}

MAX_EVENTS = 600
DEDUP_WINDOW = 2000  # max unique hashes kept in memory


@dataclass
class IntelEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp_utc: str = field(default="")

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()
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

    # ── Operational classification ─────────────────────────────────────────────
    # Distress is the product's reason to exist: distress events are surfaced as
    # the top "operational" tier (pinned, blinking, drift-ready). Everything else
    # is context. Tiers (highest priority first):
    #   operational → a live distress / SAR call demanding action
    #   news        → reporting / incidents / situational updates
    #   signal      → low-salience telemetry (AIS loiter spikes, NGO movements)
    _OPERATIONAL_TYPES = frozenset({"distress", "iom_incident"})
    _NEWS_TYPES = frozenset({"news", "twitter", "mastodon", "manual", "gdacs", "bluesky"})
    _SIGNAL_TYPES = frozenset({"ais_spike", "ngo_activity"})

    def tier(self) -> str:
        if self.type == "distress" or self.metadata.get("is_distress"):
            return "operational"
        if self.type == "iom_incident" and self.severity in ("critical", "high"):
            return "operational"
        if self.type in self._SIGNAL_TYPES:
            return "signal"
        if self.type in self._NEWS_TYPES or self.type == "iom_incident":
            return "news"
        return "news"

    def priority(self) -> int:
        """Lower = more urgent. Used for stable operational sorting."""
        tier_rank = {"operational": 0, "news": 1, "signal": 2}.get(self.tier(), 1)
        sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(self.severity, 2)
        return tier_rank * 10 + sev_rank

    def verification_status(self) -> str:
        """
        Evidence-first labelling (nextstep.txt): never present an asserted public
        report as confirmed fact. Manual operator entries are treated as
        operator-asserted; everything ingested from public sources is unverified.
        """
        explicit = self.metadata.get("verification_status")
        if explicit:
            return explicit
        if self.type == "ais_spike":
            return "derived"          # computed from AIS telemetry
        if self.source and self.source.lower() in ("manual", "operator"):
            return "operator_asserted"
        return "unverified_public_source"

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
                "tier": self.tier(),
                "priority": self.priority(),
                "verification_status": self.verification_status(),
                "drift_ready": geo is not None and self.tier() == "operational",
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
        return hashlib.blake2s(raw.encode(), digest_size=8).hexdigest()


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
        content_key = event.content_hash()
        keys = {dedup_key or content_key, content_key}
        with self._lock:
            if any(key in self._seen for key in keys):
                return False
            self._seen.update(keys)
            if len(self._seen) > DEDUP_WINDOW:
                # Keep the newest half
                self._seen = set(list(self._seen)[DEDUP_WINDOW // 2 :])
            self._events.appendleft(event)

        self._fire_broadcast(event)
        self._persist(event)
        return True

    def load_from_db(self, limit: int = MAX_EVENTS, max_age_days: int = 30) -> int:
        """
        Reload recent events from DB into the in-memory store on startup.
        Only loads events from the last `max_age_days` days.
        Returns number of events loaded.  Silent on any DB error.
        """
        try:
            from core.db.session import session_scope
            from core.db.models import IntelEventDB
            events_to_add: list[IntelEvent] = []
            cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
            with session_scope() as db:
                rows = (
                    db.query(IntelEventDB)
                    .filter(IntelEventDB.timestamp_utc >= cutoff)
                    .order_by(IntelEventDB.timestamp_utc.desc())
                    .limit(limit)
                    .all()
                )
                # Build IntelEvent objects inside session so all columns are
                # accessed while the session is open (expire_on_commit=True default)
                for row in reversed(rows):
                    events_to_add.append(IntelEvent(
                        id=row.id,
                        timestamp_utc=row.timestamp_utc,
                        type=row.type or "",
                        severity=row.severity or "",
                        lat=row.lat,
                        lon=row.lon,
                        title=row.title or "",
                        text=row.text or "",
                        url=row.url or "",
                        source=row.source or "",
                        linked_mmsi=row.linked_mmsi or "",
                        metadata=dict(row.meta or {}),
                    ))
            loaded = 0
            for ev in events_to_add:
                keys = {ev.content_hash()}
                tweet_id = str(ev.metadata.get("tweet_id") or "")
                if tweet_id:
                    keys.add(f"x:{tweet_id}")
                with self._lock:
                    if not any(key in self._seen for key in keys):
                        self._seen.update(keys)
                        self._events.appendleft(ev)
                        loaded += 1
            logger.info("intel_store: loaded %d events from DB", loaded)
            return loaded
        except Exception as exc:
            logger.warning("intel_store: DB reload skipped: %s", exc)
            return 0

    def reset_computing_drifts(self) -> int:
        """
        After startup, any in-memory event whose drift_status is 'computing'
        was orphaned by the previous process kill. Reset to 'failed' so the
        UI shows a Retry button instead of a permanent spinner.
        Also persists the change to DB so it survives future restarts.
        Returns number of events fixed.
        """
        to_fix: list[str] = []
        with self._lock:
            for ev in self._events:
                if ev.metadata.get("drift_status") == "computing":
                    ev.metadata["drift_status"] = "failed"
                    to_fix.append(ev.id)
        if to_fix:
            logger.info("intel_store: reset %d orphaned computing drift(s) to failed", len(to_fix))
            import threading
            threading.Thread(target=self._persist_drift_status_reset, args=(to_fix,), daemon=True).start()
        return len(to_fix)

    def _persist_drift_status_reset(self, event_ids: list[str]) -> None:
        """Write drift_status=failed into DB meta for each orphaned event."""
        try:
            from core.db.session import session_scope
            from core.db.models import IntelEventDB
            import json as _json
            with session_scope() as db:
                rows = db.query(IntelEventDB).filter(IntelEventDB.id.in_(event_ids)).all()
                for row in rows:
                    meta = dict(row.meta or {})
                    if meta.get("drift_status") == "computing":
                        meta["drift_status"] = "failed"
                        row.meta = meta
                db.flush()
        except Exception as exc:
            logger.debug("intel_store: DB drift_status reset skipped: %s", exc)

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

    def enrich_location(
        self,
        event_id: str,
        *,
        lat: float,
        lon: float,
        metadata: dict[str, Any],
    ) -> bool:
        """Attach a location, upgrading an existing lower-quality estimate."""
        updated: Optional[IntelEvent] = None
        with self._lock:
            for event in self._events:
                if event.id != event_id:
                    continue
                if event.lat is not None or event.lon is not None:
                    previous_rank = _COORDINATE_SOURCE_RANK.get(
                        str(event.metadata.get("coordinate_source") or "none"), 0
                    )
                    new_rank = _COORDINATE_SOURCE_RANK.get(
                        str(metadata.get("coordinate_source") or "none"), 0
                    )
                    if new_rank <= previous_rank:
                        return False
                event.lat = lat
                event.lon = lon
                event.metadata.update(metadata)
                updated = event
                break
        if updated is None:
            return False
        threading.Thread(
            target=self._persist_location_sync,
            args=(event_id, lat, lon, dict(metadata)),
            daemon=True,
        ).start()
        self._fire_broadcast(updated)
        return True

    def _persist_location_sync(
        self,
        event_id: str,
        lat: float,
        lon: float,
        metadata: dict[str, Any],
    ) -> None:
        try:
            from core.db.models import IntelEventDB
            from core.db.session import session_scope

            with session_scope() as db:
                row = db.query(IntelEventDB).filter(IntelEventDB.id == event_id).first()
                if row is None:
                    return
                merged = dict(row.meta or {})
                if row.lat is not None or row.lon is not None:
                    previous_rank = _COORDINATE_SOURCE_RANK.get(
                        str(merged.get("coordinate_source") or "none"), 0
                    )
                    new_rank = _COORDINATE_SOURCE_RANK.get(
                        str(metadata.get("coordinate_source") or "none"), 0
                    )
                    if new_rank <= previous_rank:
                        return
                row.lat = lat
                row.lon = lon
                merged.update(metadata)
                row.meta = merged
                db.flush()
        except Exception as exc:
            logger.debug("Intel DB location enrichment skipped: %s", exc)

    def update_metadata(
        self,
        event_id: str,
        *,
        metadata: dict[str, Any],
        linked_mmsi: Optional[str] = None,
    ) -> bool:
        """Merge additional metadata onto an existing event in place.

        Used to record cross-source corroboration (see intel/triangulation.py)
        without creating a duplicate event or overwriting fields set by the
        original ingestion path.
        """
        updated: Optional[IntelEvent] = None
        with self._lock:
            for event in self._events:
                if event.id != event_id:
                    continue
                event.metadata.update(metadata)
                if linked_mmsi:
                    event.linked_mmsi = linked_mmsi
                updated = event
                break
        if updated is None:
            return False
        threading.Thread(
            target=self._persist_metadata_sync,
            args=(event_id, dict(updated.metadata), updated.linked_mmsi),
            daemon=True,
        ).start()
        self._fire_broadcast(updated)
        return True

    def _persist_metadata_sync(
        self,
        event_id: str,
        metadata: dict[str, Any],
        linked_mmsi: str,
    ) -> None:
        try:
            from core.db.models import IntelEventDB
            from core.db.session import session_scope
            with session_scope() as db:
                row = db.query(IntelEventDB).filter(IntelEventDB.id == event_id).first()
                if row is None:
                    return
                row.meta = metadata
                if linked_mmsi:
                    row.linked_mmsi = linked_mmsi
                db.flush()
        except Exception as exc:
            logger.debug("Intel DB metadata update skipped: %s", exc)

    def touch_source_observation(self, event_id: str, observed_at: str) -> bool:
        """Record that a source item is still visible without creating a copy."""
        found = False
        with self._lock:
            for event in self._events:
                if event.id != event_id:
                    continue
                event.metadata["last_source_seen_at"] = observed_at
                event.metadata["source_scan_count"] = int(
                    event.metadata.get("source_scan_count") or 1
                ) + 1
                found = True
                break
        threading.Thread(
            target=self._persist_source_observation_sync,
            args=(event_id, observed_at),
            daemon=True,
        ).start()
        return found

    def _persist_source_observation_sync(self, event_id: str, observed_at: str) -> None:
        try:
            from core.db.models import IntelEventDB
            from core.db.session import session_scope
            with session_scope() as db:
                row = db.query(IntelEventDB).filter(IntelEventDB.id == event_id).first()
                if row is None:
                    return
                metadata = dict(row.meta or {})
                metadata["last_source_seen_at"] = observed_at
                metadata["source_scan_count"] = int(metadata.get("source_scan_count") or 1) + 1
                row.meta = metadata
                db.flush()
        except Exception as exc:
            logger.debug("Intel DB source observation skipped: %s", exc)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, event_id: str) -> Optional[IntelEvent]:
        normalized = event_id.removeprefix("intel:")
        with self._lock:
            return next((event for event in self._events if event.id == normalized), None)

    def persisted_events(
        self,
        *,
        source: Optional[str] = None,
        max_age_days: int = 30,
        limit: int = 1000,
    ) -> list[IntelEvent]:
        """Read durable events independently from the bounded in-memory deque."""
        try:
            from core.db.models import IntelEventDB
            from core.db.session import session_scope

            cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
            with session_scope() as db:
                query = db.query(IntelEventDB).filter(IntelEventDB.timestamp_utc >= cutoff)
                if source:
                    query = query.filter(IntelEventDB.source == source)
                rows = query.order_by(IntelEventDB.timestamp_utc.desc()).limit(limit).all()
                return [
                    IntelEvent(
                        id=row.id,
                        timestamp_utc=row.timestamp_utc,
                        type=row.type or "",
                        severity=row.severity or "",
                        lat=row.lat,
                        lon=row.lon,
                        title=row.title or "",
                        text=row.text or "",
                        url=row.url or "",
                        source=row.source or "",
                        linked_mmsi=row.linked_mmsi or "",
                        metadata=dict(row.meta or {}),
                    )
                    for row in rows
                ]
        except Exception as exc:
            logger.warning("intel_store: durable event read skipped: %s", exc)
            return []

    def events(
        self,
        severity: Optional[str] = None,
        type_filter: Optional[str] = None,
        limit: int = 200,
        max_age_days: int = 30,
    ) -> list[IntelEvent]:
        with self._lock:
            evts = list(self._events)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        evts = [e for e in evts if (e.timestamp_utc or "") >= cutoff]
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
        by_tier: dict[str, int] = {}
        for e in evts:
            by_type[e.type] = by_type.get(e.type, 0) + 1
            by_sev[e.severity] = by_sev.get(e.severity, 0) + 1
            t = e.tier()
            by_tier[t] = by_tier.get(t, 0) + 1
        return {
            "total": len(evts),
            "by_type": by_type,
            "by_severity": by_sev,
            "by_tier": by_tier,
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
