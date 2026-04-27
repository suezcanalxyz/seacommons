"""
AISStream.io WebSocket client — live AIS vessel positions.

Connects to wss://stream.aisstream.io/v0/stream, subscribes to a bounding box,
normalises incoming position reports into NormalizedEvent and appends them to
the shared IntegrationEventStore so the /api/v1/integrations/vessels endpoint
picks them up automatically.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Global coverage
DEFAULT_BBOX = [[[-90.0, -180.0], [90.0, 180.0]]]

_running = False

# Throttle: skip updates for a vessel seen within this many seconds
_THROTTLE_S = 60
_last_update: dict[str, float] = {}


def _throttled(mmsi: str) -> bool:
    """Return True if this vessel was updated recently and should be skipped."""
    now = time.monotonic()
    if now - _last_update.get(mmsi, 0) < _THROTTLE_S:
        return True
    _last_update[mmsi] = now
    return False


async def run_aisstream(store, api_key: str, bbox: list = DEFAULT_BBOX, registry=None) -> None:
    """Background task: connect → subscribe → receive → store. Reconnects on failure."""
    global _running
    if _running:
        return
    _running = True

    try:
        import websockets  # optional dep
    except ImportError:
        logger.warning("AISStream: 'websockets' not installed. Run: pip install websockets")
        _running = False
        return

    url = "wss://stream.aisstream.io/v0/stream"
    subscribe_msg = json.dumps({
        "APIKey": api_key,
        "BoundingBoxes": bbox,
        "MessageTypes": [
            "PositionReport",
            "StandardClassBPositionReport",
            "ExtendedClassBPositionReport",
            "ShipStaticData",
        ],
    })

    while _running:
        try:
            logger.info("AISStream: connecting to %s", url)
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(subscribe_msg)
                logger.info("AISStream: subscribed — Mediterranean bbox active")

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        _handle_message(msg, store, registry=registry)
                    except Exception as exc:
                        logger.debug("AISStream: parse error %s", exc)

        except Exception as exc:
            logger.warning("AISStream: connection lost (%s) — reconnecting in 15s", exc)
            await asyncio.sleep(15)

    _running = False


def _handle_message(msg: dict, store, registry=None) -> None:
    from core.domain.events import NormalizedEvent, SourceRef

    msg_type = msg.get("MessageType", "")
    meta = msg.get("MetaData", {})
    message = msg.get("Message", {})

    mmsi = str(meta.get("MMSI", "unknown"))
    ship_name = meta.get("ShipName", "").strip() or mmsi
    lat = meta.get("latitude")
    lon = meta.get("longitude")
    time_str = meta.get("time_utc", "")

    try:
        ts = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S %z")
    except Exception:
        ts = datetime.now(timezone.utc)

    source_ref = SourceRef(
        protocol="ais",
        adapter="aisstream",
        vessel_id=mmsi,
        device_id=ship_name,
        transport="websocket",
        raw_sentence="",
    )

    if msg_type == "PositionReport":
        if _throttled(mmsi):
            return
        pr = message.get("PositionReport", {})
        cog = pr.get("Cog"); sog = pr.get("Sog"); heading = pr.get("TrueHeading")
        cog_v = cog if cog is not None and cog < 360 else None
        sog_v = sog if sog is not None and sog < 102.3 else None
        hdg_v = heading if heading is not None and heading < 360 else None
        if registry and lat is not None and lon is not None:
            registry.upsert(mmsi, ship_name=ship_name, ais_class="A",
                            lat=lat, lon=lon, course=cog_v, speed=sog_v,
                            heading=hdg_v, last_seen=ts)

    elif msg_type in ("StandardClassBPositionReport", "ExtendedClassBPositionReport"):
        if _throttled(mmsi):
            return
        pr = message.get(msg_type, {})
        cog = pr.get("Cog"); sog = pr.get("Sog"); heading = pr.get("TrueHeading")
        cog_v = cog if cog is not None and cog < 360 else None
        sog_v = sog if sog is not None and sog < 102.3 else None
        hdg_v = heading if heading is not None and heading < 360 else None
        if registry and lat is not None and lon is not None:
            registry.upsert(mmsi, ship_name=ship_name, ais_class="B",
                            lat=lat, lon=lon, course=cog_v, speed=sog_v,
                            heading=hdg_v, last_seen=ts)

    elif msg_type == "ShipStaticData":
        # Static data: always update (infrequent, no throttle needed)
        sd = message.get("ShipStaticData", {})
        if registry:
            registry.upsert(mmsi, ship_name=ship_name,
                            imo=sd.get("ImoNumber"),
                            ship_type=sd.get("Type"),
                            destination=sd.get("Destination", "").strip(),
                            lat=lat, lon=lon, last_seen=ts)


def stop_aisstream() -> None:
    global _running
    _running = False
