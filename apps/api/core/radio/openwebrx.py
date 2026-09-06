# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Mapping, Protocol
from urllib.parse import urlsplit, urlunsplit

from core.radio.provider import ObservationCallback, RadioObservation, RemoteReceiverHealth
from core.radio.registry import ReceiverDescriptor


class OpenWebRXTransport(Protocol):
    def start(
        self,
        *,
        websocket_url: str,
        timeout_s: float,
        on_message: Callable[[object], None],
        on_disconnect: Callable[[str], None],
    ) -> None: ...

    def send_control(self, payload: Mapping[str, object]) -> None: ...

    def stop(self) -> None: ...


class WebSocketOpenWebRXTransport:
    """Small transport wrapper; OpenWebRX-specific normalization stays in the adapter."""

    def __init__(self) -> None:
        self._connection = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._on_disconnect: Callable[[str], None] | None = None

    def start(
        self,
        *,
        websocket_url: str,
        timeout_s: float,
        on_message: Callable[[object], None],
        on_disconnect: Callable[[str], None],
    ) -> None:
        from websockets.sync.client import connect

        self._stop.clear()
        self._on_disconnect = on_disconnect
        self._connection = connect(
            websocket_url,
            open_timeout=timeout_s,
            compression=None,
            max_size=1_048_576,
        )
        self._reader = threading.Thread(
            target=self._read_loop,
            args=(on_message,),
            daemon=True,
            name="openwebrx-reader",
        )
        self._reader.start()

    def _read_loop(self, on_message: Callable[[object], None]) -> None:
        connection = self._connection
        if connection is None:
            return
        try:
            while not self._stop.is_set():
                try:
                    message = connection.recv(timeout=1.0, decode=False)
                except TimeoutError:
                    continue
                if isinstance(message, bytes):
                    # Audio / binary stream is deliberately ignored in v1.
                    continue
                if isinstance(message, str):
                    try:
                        decoded = json.loads(message)
                    except json.JSONDecodeError:
                        continue
                    on_message(decoded)
        except Exception:
            if not self._stop.is_set() and self._on_disconnect is not None:
                self._on_disconnect("transport_disconnected")

    def send_control(self, payload: Mapping[str, object]) -> None:
        if self._connection is None:
            raise RuntimeError("OpenWebRX transport is not connected")
        self._connection.send(json.dumps(dict(payload), separators=(",", ":")))

    def stop(self) -> None:
        self._stop.set()
        connection = self._connection
        self._connection = None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        reader = self._reader
        self._reader = None
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=2.0)


def openwebrx_websocket_url(frontend_url: str) -> str:
    parsed = urlsplit(frontend_url)
    scheme = {"https": "wss", "http": "ws", "wss": "wss", "ws": "ws"}.get(
        parsed.scheme.lower()
    )
    if scheme is None or not parsed.netloc:
        raise ValueError("OpenWebRX frontend URL must be http(s) or ws(s)")
    base_path = parsed.path.rstrip("/")
    path = f"{base_path}/ws/" if base_path else "/ws/"
    return urlunsplit((scheme, parsed.netloc.lower(), path, "", ""))


class OpenWebRXAdapter:
    def __init__(
        self,
        descriptor: ReceiverDescriptor,
        *,
        on_observation: ObservationCallback,
        transport: OpenWebRXTransport | None = None,
        connect_timeout_s: float = 10.0,
    ) -> None:
        if descriptor.provider != "openwebrx":
            raise ValueError("OpenWebRXAdapter requires provider=openwebrx")
        if connect_timeout_s <= 0:
            raise ValueError("connect_timeout_s must be positive")
        self._descriptor = descriptor
        self._on_observation = on_observation
        self._transport = transport or WebSocketOpenWebRXTransport()
        self._connect_timeout_s = connect_timeout_s
        self._connected = False
        self._last_message_at: datetime | None = None
        self._observations_received = 0
        self._error: str | None = None
        self._frequency_hz: int | None = None
        self._mode: str | None = None
        self._session_id = ""
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._connected:
                return
            self._error = None
            self._session_id = uuid.uuid4().hex
        try:
            self._transport.start(
                websocket_url=openwebrx_websocket_url(self._descriptor.frontend_url),
                timeout_s=self._connect_timeout_s,
                on_message=self._on_message,
                on_disconnect=self._on_disconnect,
            )
        except Exception as exc:
            try:
                self._transport.stop()
            except Exception:
                pass
            with self._lock:
                self._connected = False
                self._error = "connect_failed"
            raise RuntimeError("OpenWebRX connection failed") from exc
        with self._lock:
            self._connected = True

    def stop(self) -> None:
        try:
            self._transport.stop()
        finally:
            with self._lock:
                self._connected = False
                self._error = None

    def health(self) -> RemoteReceiverHealth:
        with self._lock:
            return RemoteReceiverHealth(
                receiver_id=self._descriptor.receiver_id,
                provider=self._descriptor.provider,
                connected=self._connected,
                last_message_at=self._last_message_at,
                observations_received=self._observations_received,
                error=self._error,
            )

    def capabilities(self):
        return self._descriptor.capabilities

    def tune(self, frequency_hz: int, mode: str) -> None:
        normalized_mode = str(mode or "").strip().lower()
        if not normalized_mode:
            raise ValueError("mode must not be empty")
        if not any(
            capability.frequency_min_hz <= frequency_hz <= capability.frequency_max_hz
            and normalized_mode in capability.modes
            for capability in self._descriptor.capabilities
        ):
            raise ValueError("frequency or mode is outside configured receiver capability")
        with self._lock:
            if not self._connected:
                raise RuntimeError("OpenWebRX adapter is not connected")
        self._transport.send_control(
            {"type": "tune", "frequency_hz": int(frequency_hz), "mode": normalized_mode}
        )
        with self._lock:
            self._frequency_hz = int(frequency_hz)
            self._mode = normalized_mode

    def _on_disconnect(self, _detail: str) -> None:
        with self._lock:
            self._connected = False
            self._error = "transport_disconnected"

    def _on_message(self, message: object) -> None:
        if not isinstance(message, Mapping):
            return
        if str(message.get("type") or "").strip().lower() != "signal":
            return
        with self._lock:
            frequency_hz = self._frequency_hz
            mode = self._mode
            session_id = self._session_id
            if frequency_hz is None or mode is None:
                return
        signal_dbm = message.get("signal_dbm")
        snr_db = message.get("snr_db")
        observed_at = datetime.now(timezone.utc)
        observation = RadioObservation(
            receiver_id=self._descriptor.receiver_id,
            provider=self._descriptor.provider,
            physical_lineage=self._descriptor.physical_lineage,
            frequency_hz=frequency_hz,
            mode=mode,
            observed_at=observed_at,
            signal_dbm=float(signal_dbm) if signal_dbm is not None else None,
            snr_db=float(snr_db) if snr_db is not None else None,
            source_terms=self._descriptor.source_terms,
            provider_message_id=str(message.get("message_id")) if message.get("message_id") else None,
            session_id=session_id,
        )
        with self._lock:
            self._last_message_at = observed_at
            self._observations_received += 1
        self._on_observation(observation)
