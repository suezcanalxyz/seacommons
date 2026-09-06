# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from core.vessels.ais_provider import AISPositionObservation, AISProviderHealth


@dataclass(frozen=True)
class CoverageAssessment:
    status: str
    active_upstreams: frozenset[str]
    degraded_upstreams: frozenset[str]
    confidence: float
    reason_codes: tuple[str, ...]
    gap_eligible: bool


def assess_coverage(
    *,
    active_upstreams: set[str] | frozenset[str],
    degraded_upstreams: set[str] | frozenset[str],
    nearby_traffic_seen: bool,
) -> CoverageAssessment:
    active = frozenset(str(v) for v in active_upstreams if str(v))
    degraded = frozenset(str(v) for v in degraded_upstreams if str(v))
    if degraded:
        return CoverageAssessment(
            "provider_degraded", active, degraded, 0.25,
            ("UPSTREAM_DEGRADED",), False,
        )
    if active and nearby_traffic_seen:
        return CoverageAssessment(
            "coverage_present", active, degraded, 0.9,
            ("COVERAGE_PRESENT",), True,
        )
    if active:
        return CoverageAssessment(
            "no_nearby_traffic", active, degraded, 0.35,
            ("NO_NEARBY_TRAFFIC",), False,
        )
    return CoverageAssessment(
        "coverage_unknown", active, degraded, 0.0,
        ("COVERAGE_UNKNOWN",), False,
    )


class CoverageState:
    def __init__(self, *, freshness_s: int = 180) -> None:
        self.freshness_s = freshness_s
        self._lock = threading.Lock()
        self._last_upstream: dict[str, datetime] = {}
        self._health: dict[str, AISProviderHealth] = {}

    def note_observation(self, obs: AISPositionObservation) -> None:
        upstream = str(obs.upstream_source or obs.provider or "").strip().lower()
        if not upstream:
            return
        with self._lock:
            self._last_upstream[upstream] = obs.received_at

    def update_health(self, health: AISProviderHealth) -> None:
        with self._lock:
            self._health[str(health.provider).strip().lower()] = health

    def assess(self, *, nearby_traffic_seen: bool, now: datetime | None = None) -> CoverageAssessment:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.freshness_s)
        with self._lock:
            active = {
                upstream for upstream, seen in self._last_upstream.items()
                if seen >= cutoff
            }
            degraded = {
                provider for provider, health in self._health.items()
                if not health.connected or bool(health.error)
            }
        return assess_coverage(
            active_upstreams=active,
            degraded_upstreams=degraded,
            nearby_traffic_seen=nearby_traffic_seen,
        )


coverage_state = CoverageState()
