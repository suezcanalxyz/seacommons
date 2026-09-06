# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol


def normalize_provider_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return normalized.strip("_")


@dataclass(frozen=True)
class AISPositionObservation:
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
    provider: str
    upstream_source: str | None = None
    station_id: str | None = None
    source_terms: str | None = None
    raw_message_id: str | None = None


@dataclass(frozen=True)
class AISProviderHealth:
    provider: str
    connected: bool
    last_message_at: datetime | None
    messages_received: int
    error: str | None = None


ObservationCallback = Callable[[AISPositionObservation], None]


class AISProviderAdapter(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def health(self) -> AISProviderHealth: ...
