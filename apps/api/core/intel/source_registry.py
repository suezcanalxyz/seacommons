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
        # Optional per-target health for multi-source collectors (for example
        # one X/Twitter monitor polling several NGO handles).  This belongs to
        # the channel status instead of a parallel registry so pipeline health
        # and source availability cannot drift apart.
        self._targets: dict[str, dict[str, Any]] = {}
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

    def register_targets(self, targets: list[str]) -> None:
        with self._lock:
            for target in targets:
                name = str(target or "").strip().lstrip("@")
                if not name:
                    continue
                self._targets.setdefault(
                    name,
                    {
                        "name": name,
                        "last_poll_at": None,
                        "consecutive_errors": 0,
                        "last_error": None,
                        "total_events": 0,
                    },
                )

    def record_target_poll(
        self,
        target: str,
        *,
        events_found: int = 0,
        error: Optional[str] = None,
    ) -> None:
        name = str(target or "").strip().lstrip("@")
        if not name:
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            state = self._targets.setdefault(
                name,
                {
                    "name": name,
                    "last_poll_at": None,
                    "consecutive_errors": 0,
                    "last_error": None,
                    "total_events": 0,
                },
            )
            state["last_poll_at"] = now_iso
            state["total_events"] += events_found
            if error:
                state["consecutive_errors"] += 1
                state["last_error"] = error
            else:
                state["consecutive_errors"] = 0
                state["last_error"] = None

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
        pipeline = self.pipeline_status
        availability = self.source_status
        if pipeline == "offline" or availability == "offline":
            return "offline"
        if pipeline == "degraded" or availability == "degraded":
            return "degraded"
        if pipeline == "pending" or availability == "pending":
            return "pending"
        return pipeline

    @property
    def pipeline_status(self) -> str:
        with self._lock:
            if self.last_poll_at is None:
                return "pending"
            if self.consecutive_errors >= 5:
                return "offline"
            if self.consecutive_errors >= 2:
                return "degraded"
            return "active"

    @property
    def source_status(self) -> str:
        with self._lock:
            if not self._targets:
                return "unknown"
            polled = [target for target in self._targets.values() if target["last_poll_at"]]
            if not polled:
                return "pending"
            reachable = sum(
                1
                for target in self._targets.values()
                if target["last_poll_at"] and not target["consecutive_errors"]
            )
            if reachable == 0:
                return "offline"
            if reachable < len(self._targets):
                return "degraded"
            return "healthy"

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            targets = [
                {
                    **target,
                    "status": (
                        "pending"
                        if target["last_poll_at"] is None
                        else "unavailable"
                        if target["consecutive_errors"]
                        else "healthy"
                    ),
                }
                for target in self._targets.values()
            ]
        reachable = sum(1 for target in targets if target["status"] == "healthy")
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
            "pipeline_status": self.pipeline_status,
            "source_status": self.source_status,
            "configured": len(targets),
            "reachable": reachable,
            "handles": targets,
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

    def register_targets(self, name: str, targets: list[str]) -> None:
        with self._lock:
            src = self._sources.get(name)
        if src:
            src.register_targets(targets)

    def record_target_poll(
        self,
        name: str,
        target: str,
        *,
        events_found: int = 0,
        error: Optional[str] = None,
    ) -> None:
        with self._lock:
            src = self._sources.get(name)
        if src:
            src.record_target_poll(target, events_found=events_found, error=error)

    def get_all(self) -> list[dict[str, Any]]:
        with self._lock:
            sources = list(self._sources.values())
        return [s.to_dict() for s in sources]

    def get(self, name: str) -> Optional[SourceStatus]:
        with self._lock:
            return self._sources.get(name)


# Module-level singleton
source_registry = SourceRegistry()
