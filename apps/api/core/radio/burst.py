# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean
from typing import Iterable

from core.radio.provider import RadioObservation


@dataclass(frozen=True)
class RadioBurst:
    burst_id: str
    physical_lineage: str
    frequency_hz: int
    started_at: datetime
    ended_at: datetime
    sample_count: int
    peak_signal_db: float
    mean_signal_db: float


@dataclass(frozen=True)
class CorrelatedRadioEvent:
    event_id: str
    frequency_hz: int
    started_at: datetime
    ended_at: datetime
    independent_receivers: int
    physical_lineages: tuple[str, ...]
    burst_ids: tuple[str, ...]
    confidence: float


def _signal_db(observation: RadioObservation) -> float | None:
    if observation.signal_dbm is not None:
        return float(observation.signal_dbm)
    if observation.signal_dbfs is not None:
        return float(observation.signal_dbfs)
    return None


@dataclass
class _ChannelState:
    baseline_db: float | None = None
    active_samples: list[tuple[datetime, float]] | None = None


class RadioBurstDetector:
    def __init__(
        self,
        *,
        trigger_delta_db: float = 8.0,
        release_delta_db: float = 3.0,
        min_samples: int = 2,
        baseline_alpha: float = 0.15,
    ) -> None:
        self.trigger_delta_db = float(trigger_delta_db)
        self.release_delta_db = float(release_delta_db)
        self.min_samples = max(1, int(min_samples))
        self.baseline_alpha = min(max(float(baseline_alpha), 0.01), 1.0)
        self._states: dict[tuple[str, int], _ChannelState] = {}

    def ingest(self, observation: RadioObservation) -> tuple[RadioBurst, ...]:
        signal = _signal_db(observation)
        if signal is None:
            return ()
        key = (observation.physical_lineage, observation.frequency_hz)
        state = self._states.setdefault(key, _ChannelState())
        if state.baseline_db is None:
            state.baseline_db = signal
            return ()
        if state.active_samples is None:
            if signal >= state.baseline_db + self.trigger_delta_db:
                state.active_samples = [(observation.observed_at, signal)]
                return ()
            state.baseline_db = (
                (1.0 - self.baseline_alpha) * state.baseline_db
                + self.baseline_alpha * signal
            )
            return ()
        if signal > state.baseline_db + self.release_delta_db:
            state.active_samples.append((observation.observed_at, signal))
            return ()
        samples = state.active_samples
        state.active_samples = None
        state.baseline_db = (
            (1.0 - self.baseline_alpha) * state.baseline_db
            + self.baseline_alpha * signal
        )
        if len(samples) < self.min_samples:
            return ()
        return (self._build_burst(observation, samples),)

    @staticmethod
    def _build_burst(
        observation: RadioObservation,
        samples: list[tuple[datetime, float]],
    ) -> RadioBurst:
        started_at = samples[0][0]
        ended_at = samples[-1][0]
        values = [value for _timestamp, value in samples]
        material = "|".join(
            (
                observation.physical_lineage,
                str(observation.frequency_hz),
                started_at.isoformat(),
                ended_at.isoformat(),
                str(len(samples)),
            )
        )
        burst_id = "rfb:" + hashlib.blake2s(
            material.encode("utf-8"), digest_size=12
        ).hexdigest()
        return RadioBurst(
            burst_id=burst_id,
            physical_lineage=observation.physical_lineage,
            frequency_hz=observation.frequency_hz,
            started_at=started_at,
            ended_at=ended_at,
            sample_count=len(samples),
            peak_signal_db=max(values),
            mean_signal_db=round(fmean(values), 2),
        )


def correlate_bursts(
    bursts: Iterable[RadioBurst], *, window_seconds: float = 5.0
) -> CorrelatedRadioEvent:
    rows = sorted(tuple(bursts), key=lambda row: row.started_at)
    if not rows:
        raise ValueError("bursts must not be empty")
    frequency_hz = rows[0].frequency_hz
    matching = [
        row for row in rows
        if row.frequency_hz == frequency_hz
        and (row.started_at - rows[0].started_at).total_seconds() <= window_seconds
    ]
    by_lineage: dict[str, RadioBurst] = {}
    for row in matching:
        current = by_lineage.get(row.physical_lineage)
        if current is None or row.peak_signal_db > current.peak_signal_db:
            by_lineage[row.physical_lineage] = row
    selected = tuple(sorted(by_lineage.values(), key=lambda row: row.physical_lineage))
    material = "|".join(row.burst_id for row in selected)
    event_id = "rfe:" + hashlib.blake2s(material.encode("utf-8"), digest_size=12).hexdigest()
    independent = len(selected)
    confidence = round(min(1.0, 0.35 + 0.2 * independent), 3)
    return CorrelatedRadioEvent(
        event_id=event_id,
        frequency_hz=frequency_hz,
        started_at=min(row.started_at for row in selected),
        ended_at=max(row.ended_at for row in selected),
        independent_receivers=independent,
        physical_lineages=tuple(row.physical_lineage for row in selected),
        burst_ids=tuple(row.burst_id for row in selected),
        confidence=confidence,
    )
