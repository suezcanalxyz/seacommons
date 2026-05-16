# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Source registry for OSINT monitors.

Each monitor registers itself and records the outcome of every poll cycle.
Provides a health snapshot for the /api/v1/intel/sources endpoint.
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional


class SourceStatus:
    def __init__(self, name: str, source_type: str) -> None:
        self.name = name
        self.source_type = source_type          # twitter | rss | scrape | ais | mastodon | manual
        self.registered_at = datetime.now(timezone.utc).isoformat()
        self.last_poll_at: Optional[str] = None
        self.last_error: Optional[str] = None
        self.consecutive_errors: int = 0
        self.total_events: int = 0
        # sliding window: timestamps of events ingested in the last hour
        self._event_times: deque[float] = deque()
        self._lock = threading.Lock()

    def record_poll(self, events_found: int = 0, error: Optional[str] = None) -> None:
        import time
        now_ts = time.monotonic()
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.last_poll_at = now_iso
            if error:
                self.last_error = error
                self.consecutive_errors += 1
            else:
                self.consecutive_errors = 0
                self.last_error = None
            self.total_events += events_found
            now_wall = datetime.now(timezone.utc).timestamp()
            for _ in range(events_found):
                self._event_times.append(now_wall)
            # Evict events older than 1 hour
            cutoff = now_wall - 3600
            while self._event_times and self._event_times[0] < cutoff:
                self._event_times.popleft()

    @property
    def events_last_hour(self) -> int:
        import time
        cutoff = datetime.now(timezone.utc).timestamp() - 3600
        with self._lock:
            while self._event_times and self._event_times[0] < cutoff:
                self._event_times.popleft()
            return len(self._event_times)

    @property
    def status(self) -> str:
        if self.last_poll_at is None:
            return "pending"
        if self.consecutive_errors >= 5:
            return "offline"
        if self.consecutive_errors >= 2:
            return "degraded"
        return "active"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.source_type,
            "status": self.status,
            "last_poll_at": self.last_poll_at,
            "events_last_hour": self.events_last_hour,
            "total_events": self.total_events,
            "consecutive_errors": self.consecutive_errors,
            "last_error": self.last_error,
            "registered_at": self.registered_at,
        }


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, SourceStatus] = {}
        self._lock = threading.Lock()

    def register(self, name: str, source_type: str) -> SourceStatus:
        with self._lock:
            if name not in self._sources:
                self._sources[name] = SourceStatus(name, source_type)
            return self._sources[name]

    def record_poll(self, name: str, events_found: int = 0, error: Optional[str] = None) -> None:
        with self._lock:
            src = self._sources.get(name)
        if src:
            src.record_poll(events_found=events_found, error=error)

    def get_all(self) -> list[dict[str, Any]]:
        with self._lock:
            sources = list(self._sources.values())
        return [s.to_dict() for s in sources]

    def get(self, name: str) -> Optional[SourceStatus]:
        with self._lock:
            return self._sources.get(name)


# Module-level singleton
source_registry = SourceRegistry()
