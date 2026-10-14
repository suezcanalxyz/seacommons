# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol


def is_excluded_ship_type(value: object) -> bool:
    """Canonical SeaCommons scope: no pleasure craft or passenger vessels.

    ITU/IMO AIS type 37 identifies pleasure craft; type 60-69 passenger.
    A textual alias catches upstream non-numeric labels without inferring a
    vessel type from its name, route, position, length or MMSI prefix.
    Unknown AIS types are not misclassified as passenger/pleasure.
    """
    if value is None or isinstance(value, bool):
        return False
    try:
        numeric = int(str(value).strip())
    except (TypeError, ValueError):
        normalized = normalize_provider_name(str(value))
        return normalized in {
            "pleasure", "pleasure_craft", "pleasure_vessel", "recreational_craft",
            "recreational_vessel", "passenger", "passenger_ship", "passenger_vessel",
        }
    return numeric == 37 or 60 <= numeric <= 69


def is_excluded_live_vessel(properties: object) -> bool:
    """Deny known excluded vessel types from any public LIVE projection.

    Covers historical observations whose original event did not carry a ship
    type, by consulting the existing registry metadata. No new database.
    """
    if not isinstance(properties, dict):
        return False
    for key in ("ship_type", "vessel_type_context", "ais_ship_type", "vessel_type"):
        if is_excluded_ship_type(properties.get(key)):
            return True
    mmsi = str(properties.get("linked_mmsi") or properties.get("mmsi")
               or properties.get("vessel_id") or "").strip()
    if not mmsi:
        return False
    try:
        from core.vessels.registry import registry
        existing = (getattr(registry, "_cache", {}) or {}).get(mmsi, {})
        return is_excluded_ship_type(existing.get("ship_type"))
    except Exception:
        return False


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
