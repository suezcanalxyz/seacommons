# SPDX-License-Identifier: AGPL-3.0-or-later
"""NMEA 0183 parser — serial port, TCP socket, or MOCK synthetic."""
from __future__ import annotations
import io
import logging
import os
import random
import socket
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Optional

from core.config import config as _cfg

logger = logging.getLogger(__name__)


class NMEAParser:
    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 38400,
        tcp_host: Optional[str] = None,
        tcp_port: int = 10110,
        mock: bool = False,
    ):
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true" or _cfg.MOCK
        self.port = port
        self.baudrate = baudrate
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lat: float = 35.5
        self._lon: float = 14.0
        self._alt: float = 0.0
        self._heading: float = 0.0
        self._speed_kts: float = 0.0
        self._ts: str = ""
        self._callbacks: dict[str, list[Callable]] = defaultdict(list)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def get_position(self) -> tuple[float, float, float, str]:
        return (self._lat, self._lon, self._alt, self._ts)

    def get_heading(self) -> float:
        return self._heading

    def get_speed_kts(self) -> float:
        return self._speed_kts

    def subscribe(self, sentence_type: str, callback: Callable) -> None:
        """Register callback for a specific NMEA sentence type (e.g. 'GGA')."""
        self._callbacks[sentence_type].append(callback)

    # ── Internal ──────────────────────────────────────────────────────────
    def _loop(self) -> None:
        if self.mock:
            self._mock_loop()
            return
        if self.tcp_host:
            self._tcp_loop()
        else:
            self._serial_loop()

    def _mock_loop(self) -> None:
        lat, lon = 35.500, 14.000
        course = random.uniform(0, 360)
        while self._running:
            lat += math.cos(math.radians(course)) * 0.0001
            lon += math.sin(math.radians(course)) * 0.0001
            self._lat, self._lon = lat, lon
            self._heading = course
            self._speed_kts = 8.0 + random.gauss(0, 0.5)
            sentences = [
                f"$GPGGA,{_ts()},3530.00,N,01400.00,E,1,8,1.0,{self._alt:.1f},M,,,,*00",
                f"$GPVTG,{course:.1f},T,,M,{self._speed_kts:.1f},N,,K*00",
                f"$GPHDT,{course:.1f},T*00",
            ]
            for s in sentences:
                self._parse(s)
            time.sleep(1)

    def _serial_loop(self) -> None:
        try:
            import serial  # type: ignore[import]
            with serial.Serial(self.port, self.baudrate, timeout=2) as ser:
                while self._running:
                    line = ser.readline().decode("ascii", errors="ignore").strip()
                    if line:
                        self._parse(line)
        except Exception as exc:
            logger.error("Serial NMEA error: %s", exc)

    def _tcp_loop(self) -> None:
        while self._running:
            try:
                with socket.create_connection((self.tcp_host, self.tcp_port), timeout=5) as sock:
                    f = sock.makefile("r")
                    for line in f:
                        if not self._running:
                            break
                        self._parse(line.strip())
            except Exception as exc:
                logger.warning("TCP NMEA error: %s — reconnecting in 5s", exc)
                time.sleep(5)

    def _parse(self, sentence: str) -> None:
        if not sentence.startswith("$"):
            return
        parts = sentence.split(",")
        msg_type = parts[0][3:] if len(parts[0]) > 3 else ""
        try:
            if msg_type == "GGA":
                self._parse_gga(parts)
            elif msg_type == "VTG":
                self._parse_vtg(parts)
            elif msg_type in ("HDT", "HDG"):
                if len(parts) > 1:
                    self._heading = float(parts[1]) if parts[1] else self._heading
            elif msg_type == "VHW":
                if len(parts) > 5:
                    self._speed_kts = float(parts[5]) if parts[5] else self._speed_kts
        except Exception:
            pass
        for cb in self._callbacks.get(msg_type, []):
            try:
                cb(parts)
            except Exception:
                pass

    def _parse_gga(self, parts: list[str]) -> None:
        if len(parts) < 9:
            return
        if parts[2] and parts[4]:
            self._lat = _nmea_to_deg(parts[2], parts[3])
            self._lon = _nmea_to_deg(parts[4], parts[5])
        if parts[9]:
            self._alt = float(parts[9])
        self._ts = parts[1]

    def _parse_vtg(self, parts: list[str]) -> None:
        if len(parts) > 7 and parts[7]:
            speed_kmh = float(parts[7])
            self._speed_kts = speed_kmh / 1.852
        if len(parts) > 1 and parts[1]:
            self._heading = float(parts[1])


def _ts() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%H%M%S")


def _nmea_to_deg(value: str, hemisphere: str) -> float:
    if not value:
        return 0.0
    dot = value.index(".") if "." in value else len(value)
    degrees = int(value[:dot - 2])
    minutes = float(value[dot - 2:])
    result = degrees + minutes / 60.0
    if hemisphere in ("S", "W"):
        result = -result
    return result


import math  # noqa: E402 — used in mock loop


if __name__ == "__main__":
    parser = NMEAParser(mock=True)
    parser.start()
    time.sleep(3)
    parser.stop()
    lat, lon, alt, ts = parser.get_position()
    print(f"NMEAParser self-test OK: lat={lat:.4f} lon={lon:.4f} hdg={parser.get_heading():.1f}")
