# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.vessels.ais_provider import AISPositionObservation
from core.vessels.ais_reconcile import AISReconciler, ReconciledAISFix

_VALID_MODES = frozenset({"legacy", "shadow", "fused"})


class AISFusionRuntime:
    """Mode gate between provider observations and canonical AIS consumers."""

    def __init__(
        self,
        *,
        mode: str = "legacy",
        canonical_sink: Callable[[ReconciledAISFix], None] | None = None,
    ) -> None:
        normalized = str(mode or "legacy").strip().lower()
        if normalized not in _VALID_MODES:
            raise ValueError(f"unsupported AIS fusion mode: {mode}")
        self.mode = normalized
        self._reconciler = AISReconciler()
        self._canonical_sink = canonical_sink or _canonical_sink
        self._shadow_comparisons = 0
        self._canonical_writes = 0
        self._aiscast_started = False
        self._aiscast_client = None
        self._last_health_ok: dict[str, bool] = {}

    def ingest(self, observation: AISPositionObservation) -> ReconciledAISFix | None:
        from core.observability import record_ais_fusion_observation
        from core.vessels.ais_coverage import coverage_state

        upstream = str(observation.upstream_source or observation.provider or "unknown").lower()
        record_ais_fusion_observation(
            provider=observation.provider, upstream=upstream, mode=self.mode, outcome="received"
        )
        coverage_state.note_observation(observation)
        if self.mode == "legacy":
            return None
        fix = self._reconciler.ingest(observation)
        if fix is None:
            record_ais_fusion_observation(
                provider=observation.provider, upstream=upstream, mode=self.mode, outcome="duplicate"
            )
            return None
        if self.mode == "shadow":
            self._shadow_comparisons += 1
            record_ais_fusion_observation(
                provider=observation.provider, upstream=upstream, mode=self.mode, outcome="shadow"
            )
            return fix
        self._canonical_sink(fix)
        self._canonical_writes += 1
        record_ais_fusion_observation(
            provider=observation.provider, upstream=upstream, mode=self.mode, outcome="canonical"
        )
        return fix


    def update_health(self, health) -> None:
        from core.vessels.ais_coverage import coverage_state

        coverage_state.update_health(health)
        provider = str(getattr(health, "provider", "") or "unknown").lower()
        healthy = bool(getattr(health, "connected", False)) and not bool(getattr(health, "error", None))
        previous = self._last_health_ok.get(provider)
        self._last_health_ok[provider] = healthy
        if previous is True and not healthy:
            try:
                from core.intel.coverage_change_log import record_coverage_change
                record_coverage_change(
                    provider, "coverage_break",
                    rationale="AIS provider became unavailable during active runtime",
                )
            except Exception:
                pass

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "shadow_comparisons": self._shadow_comparisons,
            "canonical_writes": self._canonical_writes,
            "aiscast_started": self._aiscast_started,
        }


def _canonical_sink(fix: ReconciledAISFix) -> None:
    from core.vessels.ais_bus import publish
    from core.vessels.registry import registry
    from core.vessels.track_store import track_store

    registry.upsert_reconciled(fix)
    track_store.on_reconciled_fix(fix)
    publish(fix)


_runtime: AISFusionRuntime | None = None


def runtime() -> AISFusionRuntime | None:
    return _runtime


def configure_runtime(mode: str) -> AISFusionRuntime:
    global _runtime
    _runtime = AISFusionRuntime(mode=mode)
    return _runtime


def _parse_bbox(value: str):
    text = str(value or "").strip()
    if not text:
        return None
    parts = [float(part.strip()) for part in text.split(",")]
    if len(parts) != 4:
        raise ValueError("AISCAST_BBOX must be min_lat,min_lon,max_lat,max_lon")
    return tuple(parts)


def start_sources(
    *,
    mode: str,
    aisstream_key: str,
    ngo_api_key: str = "",
    aiscast_enabled: bool = False,
    aiscast_bbox: str = "",
    aiscast_mmsi_limit: int = 10,
    aiscast_url: str = "wss://ais.openwaters.io/v1/stream",
    aisstream_start=None,
    aiscast_factory=None,
) -> AISFusionRuntime:
    global _runtime
    rt = configure_runtime(mode)

    if aisstream_start is None:
        from core.vessels.aisstream import start as aisstream_start
    if aiscast_factory is None:
        from core.vessels.aiscast import AiscastClient as aiscast_factory

    if aisstream_key:
        if rt.mode == "legacy":
            aisstream_start(aisstream_key, ngo_api_key=ngo_api_key)
        else:
            aisstream_start(
                aisstream_key, ngo_api_key=ngo_api_key,
                on_observation=rt.ingest,
                on_health=rt.update_health,
                publish_legacy=rt.mode == "shadow",
            )

    if aiscast_enabled and rt.mode != "legacy":
        bbox = _parse_bbox(aiscast_bbox)
        mmsis = None
        if bbox is None:
            from core.intel.ngo_registry import ngo_mmsi_set
            limit = max(1, min(10, int(aiscast_mmsi_limit or 10)))
            mmsis = sorted(ngo_mmsi_set())[:limit]
        client = aiscast_factory(
            on_observation=rt.ingest,
            on_health=rt.update_health,
            bbox=bbox,
            mmsis=mmsis,
            url=aiscast_url,
        )
        client.start()
        rt._aiscast_client = client
        rt._aiscast_started = True
    else:
        rt._aiscast_client = None
        rt._aiscast_started = False
    return rt
