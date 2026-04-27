# SPDX-License-Identifier: AGPL-3.0-or-later
"""
AISStream.io WebSocket client - feeds real AIS position data into VesselRegistry.

Connects to wss://stream.aisstream.io/v0/stream, subscribes to Mediterranean
bounding box, processes PositionReport and ShipStaticData messages.
Auto-reconnects on disconnect.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Mediterranean + Black Sea bounding box [lat_min, lon_min], [lat_max, lon_max]
_BBOX = [[[28.0, -6.0], [47.0, 42.0]]]
_WS_URL = "wss://stream.aisstream.io/v0/stream"

_SHIP_TYPE_MAP = {
    range(20, 30): "WING_IN_GROUND",
    range(30, 32): "FISHING",
    range(31, 33): "TOWING",
    range(33, 35): "DREDGING",
    range(35, 36): "DIVING",
    range(36, 37): "MILITARY",
    range(37, 38): "SAILING",
    range(38, 40): "PLEASURE",
    range(40, 50): "HSC",
    range(50, 56): "PILOT",
    range(56, 58): "SAR",
    range(58, 59): "TUG",
    range(59, 60): "PORT_TENDER",
    range(60, 70): "PASSENGER",
    range(70, 80): "CARGO",
    range(80, 90): "TANKER",
    range(90, 100): "OTHER",
}


def _ship_type_label(type_code: int) -> str:
    for r, label in _SHIP_TYPE_MAP.items():
        if type_code in r:
            return label
    return "UNKNOWN"


class AISStreamClient:
    """Background thread that streams live AIS data from AISStream.io."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._connected = False
        self.messages_received = 0

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="aisstream")
        self._thread.start()
        logger.info("AISStream client started (Mediterranean bbox)")

    def stop(self) -> None:
        self._stop.set()
        self._connected = False

    def _run(self) -> None:
        from core.vessels.registry import registry
        import websockets.sync.client as ws_sync

        backoff = 2
        while not self._stop.is_set():
            try:
                logger.info("AISStream: connecting to %s", _WS_URL)
                with ws_sync.connect(_WS_URL, open_timeout=15) as ws:
                    # Subscribe
                    sub = {
                        "APIKey": self._api_key,
                        "BoundingBoxes": _BBOX,
                        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
                    }
                    ws.send(json.dumps(sub))
                    self._connected = True
                    backoff = 2
                    logger.info("AISStream: subscribed to Mediterranean")

                    while not self._stop.is_set():
                        raw = ws.recv(timeout=60)
                        if not raw:
                            continue
                        try:
                            msg = json.loads(raw)
                            self._handle(msg, registry)
                            self.messages_received += 1
                        except Exception as e:
                            logger.debug("AISStream msg parse error: %s", e)

            except Exception as exc:
                self._connected = False
                if not self._stop.is_set():
                    logger.warning("AISStream disconnected: %s  retry in %ds", exc, backoff)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)

    def _handle(self, msg: dict, registry) -> None:
        mtype = msg.get("MessageType", "")
        meta = msg.get("MetaData", {})
        mmsi = str(meta.get("MMSI", "")).strip()
        if not mmsi:
            return

        if mtype == "PositionReport":
            pr = msg.get("Message", {}).get("PositionReport", {})
            lat = pr.get("Latitude") or meta.get("latitude")
            lon = pr.get("Longitude") or meta.get("longitude")
            cog = pr.get("Cog")
            sog = pr.get("Sog")
            hdg = pr.get("TrueHeading")
            if lat is not None and lon is not None:
                registry.upsert(
                    mmsi,
                    ship_name=meta.get("ShipName", "").strip() or None,
                    lat=float(lat),
                    lon=float(lon),
                    course=float(cog) if cog is not None else None,
                    speed=float(sog) if sog is not None else None,
                    heading=float(hdg) if hdg is not None and hdg != 511 else None,
                )

        elif mtype == "ShipStaticData":
            sd = msg.get("Message", {}).get("ShipStaticData", {})
            name = (sd.get("Name") or meta.get("ShipName") or "").strip()
            registry.upsert(
                mmsi,
                ship_name=name or None,
                imo=sd.get("ImoNumber"),
                ship_type=sd.get("Type"),
                flag=sd.get("Flag"),
                destination=(sd.get("Destination") or "").strip() or None,
            )


# Module-level singleton - started by main.py lifespan
_client: AISStreamClient | None = None


def get_client() -> AISStreamClient | None:
    return _client


def start(api_key: str) -> AISStreamClient:
    global _client
    _client = AISStreamClient(api_key)
    _client.start()
    return _client
