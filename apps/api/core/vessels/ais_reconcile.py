# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from datetime import datetime

from core.vessels.ais_provider import AISPositionObservation


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_m = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return r_m * 2 * math.asin(math.sqrt(max(0.0, a)))


@dataclass(frozen=True)
class ReconciledAISFix:
    mmsi: str
    ship_name: str
    lat: float
    lon: float
    sog: float | None
    cog: float | None
    heading: float | None
    nav_status: int | None
    observed_at: datetime
    received_at: datetime
    selected_provider: str
    selected_upstream: str
    transport_providers: frozenset[str]
    upstream_sources: frozenset[str]
    station_ids: frozenset[str]
    source_terms: frozenset[str]


class AISReconciler:
    def __init__(self, *, max_time_delta_s: float = 8.0, max_distance_m: float = 120.0) -> None:
        self.max_time_delta_s = max_time_delta_s
        self.max_distance_m = max_distance_m
        self._last_by_mmsi: dict[str, AISPositionObservation] = {}
        self._context: dict[str, ReconciledAISFix] = {}
        self._raw_keys: set[tuple[str, str, str]] = set()
        self._lock = threading.RLock()

    @staticmethod
    def _upstream(obs: AISPositionObservation) -> str:
        return str(obs.upstream_source or obs.provider or "unknown").lower()

    @staticmethod
    def _raw_key(obs: AISPositionObservation) -> tuple[str, str, str] | None:
        if not obs.raw_message_id:
            return None
        return (
            AISReconciler._upstream(obs),
            str(obs.raw_message_id),
            obs.observed_at.isoformat(),
        )

    def _to_fix(self, obs: AISPositionObservation) -> ReconciledAISFix:
        upstream = self._upstream(obs)
        return ReconciledAISFix(
            mmsi=obs.mmsi, ship_name=obs.ship_name, lat=obs.lat, lon=obs.lon,
            sog=obs.sog, cog=obs.cog, heading=obs.heading, nav_status=obs.nav_status,
            observed_at=obs.observed_at, received_at=obs.received_at,
            selected_provider=obs.provider, selected_upstream=upstream,
            transport_providers=frozenset({obs.provider}),
            upstream_sources=frozenset({upstream}),
            station_ids=frozenset({obs.station_id} if obs.station_id else ()),
            source_terms=frozenset({obs.source_terms} if obs.source_terms else ()),
        )

    def _merge_context(self, base: ReconciledAISFix, obs: AISPositionObservation) -> ReconciledAISFix:
        upstream = self._upstream(obs)
        return ReconciledAISFix(
            **{k: getattr(base, k) for k in (
                "mmsi", "ship_name", "lat", "lon", "sog", "cog", "heading", "nav_status",
                "observed_at", "received_at", "selected_provider", "selected_upstream",
            )},
            transport_providers=base.transport_providers | {obs.provider},
            upstream_sources=base.upstream_sources | {upstream},
            station_ids=base.station_ids | ({obs.station_id} if obs.station_id else set()),
            source_terms=base.source_terms | ({obs.source_terms} if obs.source_terms else set()),
        )

    def ingest(self, obs: AISPositionObservation) -> ReconciledAISFix | None:
        with self._lock:
            raw_key = self._raw_key(obs)
            if raw_key is not None and raw_key in self._raw_keys:
                base = self._context.get(obs.mmsi) or self._to_fix(obs)
                self._context[obs.mmsi] = self._merge_context(base, obs)
                return None

            previous = self._last_by_mmsi.get(obs.mmsi)
            same_lineage_duplicate = False
            if previous is not None and self._upstream(previous) == self._upstream(obs):
                dt = abs((obs.observed_at - previous.observed_at).total_seconds())
                dist = _haversine_m(previous.lat, previous.lon, obs.lat, obs.lon)
                same_lineage_duplicate = dt <= self.max_time_delta_s and dist <= self.max_distance_m

            if raw_key is not None:
                self._raw_keys.add(raw_key)
                if len(self._raw_keys) > 100_000:
                    self._raw_keys = set(list(self._raw_keys)[-50_000:])

            if same_lineage_duplicate:
                base = self._context.get(obs.mmsi) or self._to_fix(previous)
                self._context[obs.mmsi] = self._merge_context(base, obs)
                return None

            fix = self._to_fix(obs)
            self._last_by_mmsi[obs.mmsi] = obs
            self._context[obs.mmsi] = fix
            return fix

    def context_for(self, mmsi: str) -> ReconciledAISFix | None:
        return self._context.get(str(mmsi))
