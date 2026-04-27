# SPDX-License-Identifier: AGPL-3.0-or-later
"""NMEA bridge — serial device → TCP server on port 10110."""
from __future__ import annotations
import logging
import os
import socket
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

SERIAL_PORT = os.environ.get("NMEA_PORT", "/dev/ttyUSB0")
BAUD = int(os.environ.get("NMEA_BAUD", "38400"))
TCP_HOST = os.environ.get("NMEA_TCP_HOST", "0.0.0.0")
TCP_PORT = int(os.environ.get("NMEA_TCP_PORT", "10110"))


class NMEABridge:
    """Reads NMEA from serial, broadcasts to all TCP clients."""

    def __init__(self, serial_port: str = SERIAL_PORT, baud: int = BAUD,
                 tcp_host: str = TCP_HOST, tcp_port: int = TCP_PORT, mock: bool = False):
        self.serial_port = serial_port
        self.baud = baud
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self.mock = mock or os.environ.get("MOCK", "").lower() == "true"
        self._clients: list[socket.socket] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        # Start TCP server
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.tcp_host, self.tcp_port))
        server.listen(8)
        logger.info("NMEA TCP server on %s:%d", self.tcp_host, self.tcp_port)
        threading.Thread(target=self._accept_loop, args=(server,), daemon=True).start()

        # Start serial reader
        if self.mock:
            threading.Thread(target=self._mock_serial_loop, daemon=True).start()
        else:
            threading.Thread(target=self._serial_loop, daemon=True).start()

        # Also feed core/sensors/nmea.py
        threading.Thread(target=self._nmea_core_loop, daemon=True).start()

    def _accept_loop(self, server: socket.socket) -> None:
        while True:
            try:
                conn, addr = server.accept()
                logger.info("NMEA client connected: %s", addr)
                with self._lock:
                    self._clients.append(conn)
            except Exception as exc:
                logger.error("Accept error: %s", exc)

    def _broadcast(self, sentence: str) -> None:
        dead = []
        with self._lock:
            for c in self._clients:
                try:
                    c.sendall((sentence + "\r\n").encode())
                except Exception:
                    dead.append(c)
            for c in dead:
                self._clients.remove(c)

    def _serial_loop(self) -> None:
        while True:
            try:
                import serial  # type: ignore[import]
                with serial.Serial(self.serial_port, self.baud, timeout=2) as ser:
                    logger.info("Serial %s @ %d opened", self.serial_port, self.baud)
                    for line in ser:
                        s = line.decode("ascii", errors="ignore").strip()
                        if s.startswith("$"):
                            self._broadcast(s)
            except Exception as exc:
                logger.warning("Serial error: %s — retrying in 5s", exc)
                time.sleep(5)

    def _mock_serial_loop(self) -> None:
        import random, math
        lat, lon = 35.500, 14.000
        hdg = random.uniform(0, 360)
        while True:
            lat += math.cos(math.radians(hdg)) * 0.0001
            lon += math.sin(math.radians(hdg)) * 0.0001
            lat_str = f"{abs(lat) * 100:.4f}"
            lon_str = f"{abs(lon) * 100:.4f}"
            ns = "N" if lat >= 0 else "S"
            ew = "E" if lon >= 0 else "W"
            ts = _nmea_time()
            sentences = [
                f"$GPGGA,{ts},{lat_str},{ns},{lon_str},{ew},1,8,1.0,0.0,M,,,,*00",
                f"$GPVTG,{hdg:.1f},T,,M,8.0,N,,K*00",
                f"$GPHDT,{hdg:.1f},T*00",
            ]
            for s in sentences:
                self._broadcast(s)
            time.sleep(1)

    def _nmea_core_loop(self) -> None:
        try:
            from core.sensors.nmea import NMEAParser
            parser = NMEAParser(tcp_host="127.0.0.1", tcp_port=self.tcp_port, mock=False)
            parser.start()
        except Exception as exc:
            logger.warning("core NMEAParser integration failed: %s", exc)


def _nmea_time() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%H%M%S.00")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = NMEABridge(mock=True)
    bridge.start()
    logger.info("NMEA bridge running (mock mode). Connect to port %d", TCP_PORT)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
