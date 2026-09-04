# SPDX-License-Identifier: AGPL-3.0-or-later
"""
AISStream.io WebSocket client - feeds real AIS position data into VesselRegistry.

Connects to wss://stream.aisstream.io/v0/stream, subscribes to Mediterranean
bounding box, processes PositionReport and ShipStaticData messages.
Auto-reconnects on disconnect.

A second, independent connection additionally tracks the known NGO/SAR fleet
by MMSI (AISStream's FiltersShipMMSI, capped at 50 values — the fleet is
~20) with a global bounding box, so a tracked vessel is never missed just
because it repositions outside the Mediterranean box (e.g. transiting to a
European drydock). Both run on the free tier — AISStream's public docs
document no data/message quota, just per-connection throughput and
throttling-under-load caveats — so this is additive coverage, not a
different plan.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)

# Extra consumers of each parsed PositionReport, driven off the single
# AISStream connection (the free tier allows only one open socket per key,
# so a second consumer must never open its own). A hook is called with
# (mmsi, ship_name, lat, lon, sog, nav_status, cog, heading, received_at) and
# must return fast and never raise -- it runs on the stream thread. The first
# six args are the original stable contract; `cog`/`heading` (degrees, heading
# None when 511) and `received_at` (our wall-clock at receipt, for AIS-timestamp
# skew checks) were appended so old 6-arg consumers keep working unchanged.
_PositionHook = Callable[..., None]
_position_hooks: list[_PositionHook] = []


def register_position_hook(hook: _PositionHook) -> None:
    if hook not in _position_hooks:
        _position_hooks.append(hook)


def position_hook_count() -> int:
    return len(_position_hooks)

# Mediterranean + Black Sea bounding box [lat_min, lon_min], [lat_max, lon_max]
_BBOX = [[[28.0, -6.0], [47.0, 42.0]]]
# Whole-world box, used only for the MMSI-filtered NGO-fleet subscription.
_GLOBAL_BBOX = [[[-90.0, -180.0], [90.0, 180.0]]]
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

    def __init__(
        self,
        api_key: str,
        *,
        label: str = "Mediterranean",
        bbox: list | None = None,
        mmsi_filter: list[str] | None = None,
    ):
        self._api_key = api_key
        self._label = label
        self._bbox = bbox or _BBOX
        self._mmsi_filter = mmsi_filter
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
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"aisstream-{self._label}"
        )
        self._thread.start()
        logger.info("AISStream client started (%s)", self._label)

    def stop(self) -> None:
        self._stop.set()
        self._connected = False

    def _run(self) -> None:
        from core.vessels.registry import registry
        from core.intel.source_registry import source_registry
        import websockets.sync.client as ws_sync

        # AIS never reported into the same health/alerting system every other
        # source already uses -- verified live: the whole Mediterranean feed
        # went completely silent (connects, subscribes, then times out with
        # zero messages every cycle -- a known, unresolved upstream AISstream
        # bug, github.com/aisstream/aisstream/issues/15) for 7+ hours with
        # nothing surfacing it anywhere except a user noticing "no nearby
        # vessels" on the map. record_poll on every disconnect means the
        # existing 15-minute source_health job (core/scheduler.py) now alerts
        # within a few reconnect cycles instead.
        source_name = "aisstream_" + self._label.lower().replace(" ", "_").replace("(", "").replace(")", "")
        source_registry.register(source_name, "ais")

        backoff = 2
        last_report_ts = time.monotonic()
        messages_since_report = 0
        while not self._stop.is_set():
            try:
                logger.info("AISStream: connecting to %s (%s)", _WS_URL, self._label)
                with ws_sync.connect(_WS_URL, open_timeout=15) as ws:
                    # Subscribe
                    sub = {
                        "APIKey": self._api_key,
                        "BoundingBoxes": self._bbox,
                        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
                    }
                    if self._mmsi_filter:
                        sub["FiltersShipMMSI"] = self._mmsi_filter
                    ws.send(json.dumps(sub))
                    self._connected = True
                    backoff = 2
                    logger.info("AISStream: subscribed (%s)", self._label)

                    silent_windows = 0
                    positions_this_window = 0
                    while not self._stop.is_set():
                        raw = ws.recv(timeout=60)
                        if not raw:
                            continue
                        try:
                            msg = json.loads(raw)
                            self._handle(msg, registry)
                            self.messages_received += 1
                            messages_since_report += 1
                            if msg.get("MessageType") == "PositionReport":
                                positions_this_window += 1
                        except Exception as e:
                            logger.debug("AISStream msg parse error: %s", e)
                        now = time.monotonic()
                        if now - last_report_ts >= 60:
                            source_registry.record_poll(source_name, events_found=messages_since_report)
                            # Known AISStream bug: the socket stays open (and
                            # keepalives may arrive) but no real PositionReports
                            # flow -- aisstream/aisstream#15. Force a fresh
                            # connection after 3 empty minutes rather than sit
                            # on a dead feed.
                            silent_windows = silent_windows + 1 if positions_this_window == 0 else 0
                            messages_since_report = 0
                            positions_this_window = 0
                            last_report_ts = now
                            if silent_windows >= 3:
                                logger.warning(
                                    "AISStream (%s): 3 min with no PositionReports — forcing reconnect",
                                    self._label,
                                )
                                break

            except Exception as exc:
                self._connected = False
                source_registry.record_poll(source_name, events_found=messages_since_report, error=str(exc))
                messages_since_report = 0
                last_report_ts = time.monotonic()
                if not self._stop.is_set():
                    logger.warning(
                        "AISStream (%s) disconnected: %s  retry in %ds",
                        self._label, exc, backoff,
                    )
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
            nav_status = pr.get("NavigationalStatus")
            if lat is not None and lon is not None:
                name = meta.get("ShipName", "").strip()
                registry.upsert(
                    mmsi,
                    ship_name=name or None,
                    lat=float(lat),
                    lon=float(lon),
                    course=float(cog) if cog is not None else None,
                    speed=float(sog) if sog is not None else None,
                    heading=float(hdg) if hdg is not None and hdg != 511 else None,
                    nav_status=int(nav_status) if nav_status is not None else None,
                )
                received_at = datetime.now(timezone.utc)
                for hook in _position_hooks:
                    try:
                        hook(
                            mmsi, name, float(lat), float(lon),
                            float(sog) if sog is not None else None,
                            int(nav_status) if nav_status is not None else None,
                            float(cog) if cog is not None else None,
                            float(hdg) if hdg is not None and hdg != 511 else None,
                            received_at,
                        )
                    except Exception:
                        logger.debug("AIS position hook failed", exc_info=True)

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


# Module-level singletons - started by main.py lifespan
_client: AISStreamClient | None = None
_ngo_client: AISStreamClient | None = None


def get_client() -> AISStreamClient | None:
    """The primary Mediterranean-bbox client (used for ops health reporting)."""
    return _client


def get_ngo_client() -> AISStreamClient | None:
    """The secondary, MMSI-filtered global client tracking the known NGO fleet."""
    return _ngo_client


def start(api_key: str, *, ngo_api_key: str = "") -> AISStreamClient:
    """`ngo_api_key` must be a SEPARATE AISStream key from `api_key` — verified
    live against the real service that it allows only one open connection per
    key, so a second subscription reusing the same key gets dropped
    immediately (connects, subscribes, then closes within ~1s, in a tight
    reconnect loop). With no second key, the NGO-fleet subscription is simply
    not started rather than spinning in that broken state.
    """
    global _client, _ngo_client
    _client = AISStreamClient(api_key, label="Mediterranean")
    _client.start()

    if ngo_api_key and ngo_api_key != api_key:
        try:
            from core.intel.ngo_registry import NGO_VESSELS

            ngo_mmsi = list(NGO_VESSELS.keys())[:50]  # AISStream's FiltersShipMMSI cap
            _ngo_client = AISStreamClient(
                ngo_api_key, label="NGO fleet (global)", bbox=_GLOBAL_BBOX, mmsi_filter=ngo_mmsi,
            )
            _ngo_client.start()
        except Exception:
            logger.warning("AISStream NGO-fleet subscription failed to start", exc_info=True)

    return _client
