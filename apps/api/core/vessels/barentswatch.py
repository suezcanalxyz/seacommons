# SPDX-License-Identifier: AGPL-3.0-or-later
"""
BarentsWatch Live AIS client — second AIS feed for redundancy and wider coverage.

Polls https://live.ais.barentswatch.no/v1/latest/combined every 60 s.
Requires OAuth2 client credentials (BARENTSWATCH_CLIENT_ID / BARENTSWATCH_CLIENT_SECRET).
Data is merged into the shared VesselRegistry alongside AISStream.io.

Coverage: global (filtered to Mediterranean + Red Sea + Gulf of Aden).
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://id.barentswatch.no/connect/token"
_AIS_URL = "https://live.ais.barentswatch.no/v1/latest/combined"
_POLL_INTERVAL_S = 60

# Bounding boxes to keep (lat_min, lon_min, lat_max, lon_max)
# Mediterranean + Black Sea
_BOX_MED = (28.0, -6.0, 47.0, 42.0)
# Red Sea + Gulf of Aden
_BOX_REDSEA = (11.0, 32.0, 32.0, 60.0)


def _in_bbox(lat: float, lon: float) -> bool:
    for lat_min, lon_min, lat_max, lon_max in (_BOX_MED, _BOX_REDSEA):
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True
    return False


class BarentsWatchClient:
    """Background polling thread that pulls BarentsWatch AIS data into VesselRegistry."""

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.vessels_ingested = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="barentswatch")
        self._thread.start()
        logger.info("BarentsWatch client started (Med + Red Sea bbox)")

    def stop(self) -> None:
        self._stop.set()

    def _fetch_token(self) -> Optional[str]:
        if self._token and time.monotonic() < self._token_expiry - 60:
            return self._token
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": "ais",
        }).encode()
        try:
            req = urllib.request.Request(_TOKEN_URL, data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
            self._token = body["access_token"]
            self._token_expiry = time.monotonic() + float(body.get("expires_in", 3600))
            logger.info("BarentsWatch: token acquired (expires in %ds)", body.get("expires_in", 3600))
            return self._token
        except Exception as exc:
            logger.error("BarentsWatch: token fetch failed: %s", exc)
            return None

    def _poll(self) -> int:
        from core.vessels.registry import registry

        token = self._fetch_token()
        if not token:
            return 0

        req = urllib.request.Request(_AIS_URL)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            vessels = json.loads(resp.read())

        count = 0
        for v in vessels:
            lat = v.get("latitude")
            lon = v.get("longitude")
            if lat is None or lon is None:
                continue
            if not _in_bbox(float(lat), float(lon)):
                continue
            mmsi = str(v.get("mmsi", "")).strip()
            if not mmsi:
                continue
            registry.upsert(
                mmsi,
                ship_name=(v.get("name") or "").strip() or None,
                imo=v.get("imoNumber"),
                ship_type=v.get("shipType"),
                destination=(v.get("destination") or "").strip() or None,
                lat=float(lat),
                lon=float(lon),
                course=v.get("courseOverGround"),
                speed=v.get("speedOverGround"),
                heading=v.get("trueHeading") if v.get("trueHeading") != 511 else None,
            )
            count += 1
        return count

    def _run(self) -> None:
        backoff = 5
        while not self._stop.is_set():
            try:
                n = self._poll()
                self.vessels_ingested += n
                logger.debug("BarentsWatch: ingested %d vessels in bbox", n)
                backoff = 5
            except Exception as exc:
                logger.warning("BarentsWatch poll error: %s  retry in %ds", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)
                continue
            self._stop.wait(timeout=_POLL_INTERVAL_S)


_client: Optional[BarentsWatchClient] = None


def get_client() -> Optional[BarentsWatchClient]:
    return _client


def start(client_id: str, client_secret: str) -> BarentsWatchClient:
    global _client
    _client = BarentsWatchClient(client_id, client_secret)
    _client.start()
    return _client
