# SPDX-License-Identifier: AGPL-3.0-or-later
"""AISHub contributor API client.

AISHub grants free access to its aggregated AIS feed to contributors that
share a qualifying receiver feed. The public webservice must not be polled
more frequently than once per minute, so this client enforces a 60-second
minimum interval.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://data.aishub.net/ws.php"
_DEFAULT_BBOX = (28.0, 47.0, -6.0, 42.0)
_MIN_POLL_INTERVAL_S = 60


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    for fmt in ("%Y-%m-%d %H:%M:%S GMT", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_response(payload: Any) -> list[dict[str, Any]]:
    """Normalize the AISHub JSON envelope into VesselRegistry arguments."""
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError("invalid AISHub response envelope")
    status, records = payload[0], payload[1]
    if not isinstance(status, dict):
        raise ValueError("invalid AISHub response status")
    if status.get("ERROR") not in (False, "false", 0, "0", None):
        raise RuntimeError(str(status.get("ERROR")))
    if not isinstance(records, list):
        raise ValueError("invalid AISHub vessel list")

    vessels: list[dict[str, Any]] = []
    for raw in records:
        if not isinstance(raw, dict):
            continue
        mmsi = str(raw.get("MMSI") or "").strip()
        lat = _as_float(raw.get("LATITUDE"))
        lon = _as_float(raw.get("LONGITUDE"))
        if not mmsi or lat is None or lon is None:
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        heading = _as_float(raw.get("HEADING"))
        if heading == 511:
            heading = None
        vessels.append({
            "mmsi": mmsi,
            "ship_name": str(raw.get("NAME") or "").strip() or None,
            "imo": str(raw.get("IMO") or "").strip() or None,
            "ship_type": _as_int(raw.get("TYPE")),
            "destination": str(raw.get("DEST") or "").strip() or None,
            "lat": lat,
            "lon": lon,
            "course": _as_float(raw.get("COG")),
            "speed": _as_float(raw.get("SOG")),
            "heading": heading,
            "last_seen": _parse_timestamp(raw.get("TIME") or raw.get("TSTAMP")),
        })
    return vessels


class AISHubClient:
    """Poll AISHub's contributor webservice in a background thread."""

    def __init__(
        self,
        username: str,
        *,
        poll_interval_s: int = _MIN_POLL_INTERVAL_S,
        bbox: tuple[float, float, float, float] = _DEFAULT_BBOX,
        max_age_minutes: int = 10,
        timeout_s: float = 20.0,
    ) -> None:
        self._username = username.strip()
        self._poll_interval_s = max(_MIN_POLL_INTERVAL_S, int(poll_interval_s))
        self._bbox = bbox
        self._max_age_minutes = max(1, int(max_age_minutes))
        self._timeout_s = timeout_s
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._connected = False
        self.messages_received = 0

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        if not self._username:
            raise ValueError("AISHub username is required")
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="aishub-mediterranean")
        self._thread.start()
        logger.info("AISHub client started")

    def stop(self) -> None:
        self._stop.set()
        self._connected = False

    def _params(self) -> dict[str, str | int | float]:
        latmin, latmax, lonmin, lonmax = self._bbox
        return {
            "username": self._username,
            "format": 1,
            "output": "json",
            "compress": 0,
            "latmin": latmin,
            "latmax": latmax,
            "lonmin": lonmin,
            "lonmax": lonmax,
            "interval": self._max_age_minutes,
        }

    def _poll_once(self, registry: Any, client: httpx.Client) -> int:
        response = client.get(_API_URL, params=self._params())
        response.raise_for_status()
        vessels = parse_response(response.json())
        for vessel in vessels:
            registry.upsert(**vessel)
        self.messages_received += len(vessels)
        return len(vessels)

    def _run(self) -> None:
        from core.intel.source_registry import source_registry
        from core.vessels.registry import registry

        source_name = "aishub_mediterranean"
        source_registry.register(source_name, "ais")
        with httpx.Client(timeout=self._timeout_s, follow_redirects=True) as client:
            while not self._stop.is_set():
                started = time.monotonic()
                try:
                    count = self._poll_once(registry, client)
                    self._connected = True
                    source_registry.record_poll(source_name, events_found=count)
                except Exception as exc:
                    self._connected = False
                    source_registry.record_poll(source_name, events_found=0, error=str(exc))
                    logger.warning("AISHub poll failed: %s", exc)
                elapsed = time.monotonic() - started
                self._stop.wait(max(1.0, self._poll_interval_s - elapsed))


_client: AISHubClient | None = None


def get_client() -> AISHubClient | None:
    return _client


def start(username: str, *, poll_interval_s: int = _MIN_POLL_INTERVAL_S) -> AISHubClient:
    global _client
    _client = AISHubClient(username, poll_interval_s=poll_interval_s)
    _client.start()
    return _client
