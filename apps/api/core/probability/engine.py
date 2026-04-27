# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Probability engine — maintains live ScoredSignal state for all active
distress signals, re-scores on every environmental update.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

from core.ingestion.signal import DistressSignal
from core.probability.survival import SurvivalContext
from core.probability.interception import Asset
from core.probability.scorer import ScoredSignal, score_signal

logger = logging.getLogger(__name__)


class ProbabilityEngine:
    """
    Thread-safe in-memory store of active ScoredSignals.

    Lifecycle:
    - ingest(signal)        → add / update a signal
    - update_environment()  → re-score all active signals with new env data
    - get_active()          → list of current ScoredSignals sorted by priority
    - resolve(signal_id)    → mark a signal as resolved (remove from active)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._signals: dict[str, DistressSignal] = {}    # signal_id → signal
        self._scored: dict[str, ScoredSignal]  = {}      # signal_id → scored
        self._assets: list[Asset] = _default_assets()
        self._env = _default_env()

    # ── Public API ────────────────────────────────────────────────────────────

    def ingest(self, signal: DistressSignal) -> ScoredSignal:
        """Add or replace a distress signal and score it immediately."""
        ctx = self._make_ctx(signal)
        scored = score_signal(signal, ctx, self._assets)
        with self._lock:
            self._signals[signal.signal_id] = signal
            self._scored[signal.signal_id]  = scored
        logger.info(
            "ingested %s | urgency=%s priority=%.2f",
            signal.signal_id[:8], scored.urgency, scored.priority_score
        )
        return scored

    def update_environment(
        self,
        water_temp_c: Optional[float] = None,
        air_temp_c: Optional[float] = None,
        wind_speed_ms: Optional[float] = None,
        wave_height_m: Optional[float] = None,
    ) -> None:
        """Update environmental conditions and re-score all active signals."""
        with self._lock:
            if water_temp_c  is not None: self._env["water_temp_c"]  = water_temp_c
            if air_temp_c    is not None: self._env["air_temp_c"]    = air_temp_c
            if wind_speed_ms is not None: self._env["wind_speed_ms"] = wind_speed_ms
            if wave_height_m is not None: self._env["wave_height_m"] = wave_height_m
            signals = list(self._signals.values())

        for sig in signals:
            ctx = self._make_ctx(sig)
            scored = score_signal(sig, ctx, self._assets)
            with self._lock:
                self._scored[sig.signal_id] = scored

    def get_active(self) -> list[ScoredSignal]:
        """Return all active scored signals, highest priority first."""
        with self._lock:
            return sorted(self._scored.values(),
                          key=lambda s: s.priority_score, reverse=True)

    def resolve(self, signal_id: str) -> bool:
        """Mark signal as resolved. Returns True if it existed."""
        with self._lock:
            removed = signal_id in self._signals
            self._signals.pop(signal_id, None)
            self._scored.pop(signal_id, None)
        return removed

    def set_assets(self, assets: list[Asset]) -> None:
        with self._lock:
            self._assets = assets

    # ── Internal ──────────────────────────────────────────────────────────────

    def _make_ctx(self, signal: DistressSignal) -> SurvivalContext:
        env = self._env
        elapsed = (
            datetime.now(timezone.utc) - signal.timestamp_utc
        ).total_seconds() / 3600.0
        return SurvivalContext(
            water_temp_c=env["water_temp_c"],
            air_temp_c=env["air_temp_c"],
            wind_speed_ms=env["wind_speed_ms"],
            wave_height_m=env["wave_height_m"],
            persons=signal.persons or 1,
            vessel_condition=signal.vessel_condition,
            medical_emergency=signal.medical_emergency,
            children_aboard=signal.children_aboard,
            hours_elapsed=max(0.0, elapsed),
        )


def _default_env() -> dict:
    return {
        "water_temp_c":  float(os.getenv("DEFAULT_WATER_TEMP_C", "18")),
        "air_temp_c":    float(os.getenv("DEFAULT_AIR_TEMP_C",   "20")),
        "wind_speed_ms": float(os.getenv("DEFAULT_WIND_MS",       "5")),
        "wave_height_m": float(os.getenv("DEFAULT_WAVE_M",        "1")),
    }


def _default_assets() -> list[Asset]:
    """Mock SAR assets for development / MOCK=true mode."""
    return [
        Asset("ALAN_KURDI",     35.88,  12.5,  speed_kn=12, endurance_h=48, asset_type="vessel"),
        Asset("OCEAN_VIKING",   37.5,   14.0,  speed_kn=14, endurance_h=72, asset_type="vessel"),
        Asset("FRONTEX_HEL_1", 35.9,   14.51, speed_kn=90, endurance_h=6,  asset_type="helicopter"),
    ]


# ── Self-test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from datetime import timedelta
    from core.ingestion.signal import DistressSignal

    engine = ProbabilityEngine()

    # Override environment to cold-water scenario
    engine.update_environment(
        water_temp_c=10.0, air_temp_c=8.0,
        wind_speed_ms=12.0, wave_height_m=3.0,
    )

    sig = DistressSignal(
        source_channel="whatsapp",
        source_id="+39000000001",
        raw_text="45 persone su gommone, affonda, bambini a bordo",
        lat=35.4, lon=13.2,
        persons=45,
        vessel_type="rubber_boat",
        vessel_condition="sinking",
        medical_emergency=False,
        children_aboard=True,
        extraction_confidence=0.91,
        requires_human_review=False,
        extraction_method="regex",
        # Simulate 2-hour old distress
        timestamp_utc=datetime.now(timezone.utc) - timedelta(hours=2),
    )

    scored = engine.ingest(sig)
    active = engine.get_active()

    assert len(active) == 1
    assert active[0].urgency in ("URGENT", "IMMEDIATE")
    print(f"ProbabilityEngine self-test OK: P1 {active[0].urgency}")
