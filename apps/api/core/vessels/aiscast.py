# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Iterable

from core.vessels.ais_provider import AISPositionObservation, AISProviderHealth

logger = logging.getLogger(__name__)
_DEFAULT_URL = "wss://ais.openwaters.io/v1/stream"
_SOURCE_TERMS = {
    "volunteer": "CC0-1.0",
    "digitraffic": "CC-BY-4.0",
    "kystverket": "NLOD-2.0",
    "barentswatch": "NLOD-2.0",
    "aishub": "AISHub-membership",
}


def _utc(value: object, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return fallback


def _optional_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def parse_aiscast_message(
    payload: dict,
    *,
    received_at: datetime | None = None,
) -> AISPositionObservation | None:
    if str(payload.get("type") or "").lower() != "event":
        return None
    received = received_at or datetime.now(timezone.utc)
    mmsi = str(payload.get("mmsi") or "").strip()
    if len(mmsi) != 9 or not mmsi.isdigit():
        return None
    lat = _optional_float(payload.get("lat"))
    lon = _optional_float(payload.get("lon"))
    if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None
    source = str(payload.get("source") or "").strip() or None
    station = str(payload.get("station") or "").strip() or None
    terms = str(payload.get("terms") or "").strip() or _SOURCE_TERMS.get(source or "")
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    name = str(payload.get("name") or message.get("Name") or message.get("name") or "").strip()
    nav = payload.get("nav_status", message.get("NavigationalStatus", message.get("nav_status")))
    try:
        nav_status = None if nav is None else int(nav)
    except (TypeError, ValueError):
        nav_status = None
    return AISPositionObservation(
        mmsi=mmsi, ship_name=name, lat=lat, lon=lon,
        sog=_optional_float(payload.get("sog", message.get("Sog", message.get("sog")))),
        cog=_optional_float(payload.get("cog", message.get("Cog", message.get("cog")))),
        heading=_optional_float(payload.get("heading", message.get("TrueHeading", message.get("heading")))),
        nav_status=nav_status,
        observed_at=_utc(payload.get("time"), received),
        received_at=received,
        provider="aiscast", upstream_source=source, station_id=station,
        source_terms=terms, raw_message_id=str(payload.get("id") or "").strip() or None,
    )


class AiscastClient:
    def __init__(
        self,
        *,
        on_observation: Callable[[AISPositionObservation], None],
        bbox: tuple[float, float, float, float] | None = None,
        mmsis: Iterable[str] | None = None,
        url: str = _DEFAULT_URL,
    ) -> None:
        self._on_observation = on_observation
        self._bbox = tuple(bbox) if bbox is not None else None
        self._mmsis = tuple(str(m) for m in (mmsis or ()))
        self._url = url
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False
        self._last_message_at: datetime | None = None
        self._messages_received = 0
        self._error: str | None = None
        if self._bbox is None and not self._mmsis:
            raise ValueError("aiscast requires a bounded bbox and/or MMSI subscription")
        if len(self._mmsis) > 10:
            raise ValueError("anonymous aiscast subscriptions support at most 10 MMSIs")
        if self._bbox is not None:
            min_lat, min_lon, max_lat, max_lon = self._bbox
            if max_lat <= min_lat or max_lon <= min_lon:
                raise ValueError("invalid aiscast bbox")
            if (max_lat - min_lat) * (max_lon - min_lon) > 100:
                raise ValueError("anonymous aiscast bbox exceeds 100 square degrees")

    def subscription_frame(self) -> dict:
        frame: dict[str, object] = {"type": "subscribe"}
        if self._bbox is not None:
            frame["bbox"] = [list(self._bbox)]
        if self._mmsis:
            frame["mmsi"] = [int(m) for m in self._mmsis]
        return frame

    def health(self) -> AISProviderHealth:
        return AISProviderHealth(
            provider="aiscast", connected=self._connected,
            last_message_at=self._last_message_at,
            messages_received=self._messages_received, error=self._error,
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="aiscast")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._connected = False

    def _run(self) -> None:
        from core.intel.source_registry import source_registry
        import websockets.sync.client as ws_sync

        source_registry.register("aiscast", "ais")
        backoff = 2
        while not self._stop.is_set():
            try:
                with ws_sync.connect(self._url, open_timeout=15) as ws:
                    ws.send(json.dumps(self.subscription_frame()))
                    self._connected = True
                    self._error = None
                    backoff = 2
                    while not self._stop.is_set():
                        raw = ws.recv(timeout=60)
                        if not raw:
                            continue
                        received = datetime.now(timezone.utc)
                        payload = json.loads(raw)
                        if payload.get("type") == "error":
                            raise RuntimeError(str(payload.get("error") or "aiscast error"))
                        obs = parse_aiscast_message(payload, received_at=received)
                        if obs is None:
                            continue
                        self._last_message_at = received
                        self._messages_received += 1
                        source_registry.record_poll("aiscast", events_found=1)
                        try:
                            self._on_observation(obs)
                        except Exception:
                            logger.debug("aiscast observation callback failed", exc_info=True)
            except Exception as exc:
                self._connected = False
                self._error = str(exc)
                source_registry.record_poll("aiscast", error=self._error)
                if not self._stop.is_set():
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)
