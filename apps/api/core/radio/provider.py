# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol, runtime_checkable


def _normalize_identifier(value: str, *, field: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    if not normalized:
        raise ValueError(f"{field} must contain an identifier")
    return normalized


def normalize_provider_name(value: str) -> str:
    return _normalize_identifier(value, field="provider")


@dataclass(frozen=True)
class ReceiverCapability:
    frequency_min_hz: int
    frequency_max_hz: int
    modes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.frequency_min_hz <= 0 or self.frequency_max_hz <= 0:
            raise ValueError("frequency bounds must be positive")
        if self.frequency_min_hz > self.frequency_max_hz:
            raise ValueError("frequency_min_hz must not exceed frequency_max_hz")
        modes = tuple(sorted({str(mode).strip().lower() for mode in self.modes if str(mode).strip()}))
        if not modes:
            raise ValueError("modes must contain at least one mode")
        object.__setattr__(self, "modes", modes)


@dataclass(frozen=True)
class RemoteReceiverHealth:
    receiver_id: str
    provider: str
    connected: bool
    last_message_at: datetime | None
    observations_received: int
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "receiver_id", _normalize_identifier(self.receiver_id, field="receiver_id"))
        object.__setattr__(self, "provider", normalize_provider_name(self.provider))
        if self.observations_received < 0:
            raise ValueError("observations_received must be non-negative")


@dataclass(frozen=True)
class RadioObservation:
    receiver_id: str
    provider: str
    physical_lineage: str
    frequency_hz: int
    mode: str
    observed_at: datetime
    signal_dbm: float | None = None
    snr_db: float | None = None
    source_terms: str | None = None
    provider_message_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "receiver_id", _normalize_identifier(self.receiver_id, field="receiver_id"))
        object.__setattr__(self, "provider", normalize_provider_name(self.provider))
        object.__setattr__(
            self,
            "physical_lineage",
            _normalize_identifier(self.physical_lineage, field="physical_lineage"),
        )
        if self.frequency_hz <= 0:
            raise ValueError("frequency_hz must be positive")
        mode = str(self.mode or "").strip().lower()
        if not mode:
            raise ValueError("mode must not be empty")
        object.__setattr__(self, "mode", mode)


ObservationCallback = Callable[[RadioObservation], None]


@runtime_checkable
class RemoteReceiverAdapter(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def health(self) -> RemoteReceiverHealth: ...

    def capabilities(self) -> tuple[ReceiverCapability, ...]: ...

    def tune(self, frequency_hz: int, mode: str) -> None: ...
