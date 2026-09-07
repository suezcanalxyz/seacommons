# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Callable, Iterable

from core.radio.provider import RadioObservation, RemoteReceiverAdapter
from core.radio.registry import ReceiverDescriptor, ReceiverRegistry

AdapterFactory = Callable[[ReceiverDescriptor, Callable[[RadioObservation], None]], RemoteReceiverAdapter]


def _default_observation_handler(observation: RadioObservation) -> None:
    from core.radio.bridge import handle_radio_observation

    handle_radio_observation(observation)


def _default_adapter_factory(
    descriptor: ReceiverDescriptor,
    callback: Callable[[RadioObservation], None],
) -> RemoteReceiverAdapter:
    if descriptor.provider == "kiwisdr":
        from core.radio.kiwisdr import KiwiSDRAdapter

        return KiwiSDRAdapter(descriptor, on_observation=callback)
    if descriptor.provider == "openwebrx":
        from core.radio.openwebrx import OpenWebRXAdapter

        return OpenWebRXAdapter(descriptor, on_observation=callback)
    raise ValueError("unsupported remote radio provider")


class RemoteRadioRuntime:
    def __init__(
        self,
        *,
        enabled: bool,
        descriptors: Iterable[ReceiverDescriptor],
        max_receivers: int,
        adapter_factory: AdapterFactory = _default_adapter_factory,
        observation_handler: Callable[[RadioObservation], None] = _default_observation_handler,
    ) -> None:
        self.enabled = bool(enabled)
        self._registry = ReceiverRegistry(descriptors, max_receivers=max_receivers)
        self._adapter_factory = adapter_factory
        self._observation_handler = observation_handler
        self._adapters: list[tuple[ReceiverDescriptor, RemoteReceiverAdapter]] = []
        self._failed_by_provider: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def start(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._adapters:
                return
        from core.observability import record_remote_radio_event

        for descriptor in self._registry.runnable():
            provider = descriptor.provider if descriptor.provider in {"kiwisdr", "openwebrx"} else "other"
            try:
                adapter = self._adapter_factory(descriptor, self._observation_handler)
                adapter.start()
                if descriptor.frequency_hz is not None and descriptor.mode is not None:
                    adapter.tune(descriptor.frequency_hz, descriptor.mode)
            except Exception:
                try:
                    adapter.stop()
                except Exception:
                    pass
                self._failed_by_provider[provider] += 1
                record_remote_radio_event(provider=provider, state="disconnected", outcome="start_failed")
                continue
            with self._lock:
                self._adapters.append((descriptor, adapter))
            record_remote_radio_event(provider=provider, state="connected", outcome="started")

    def stop(self) -> None:
        with self._lock:
            adapters = tuple(self._adapters)
            self._adapters.clear()
        for _descriptor, adapter in adapters:
            try:
                adapter.stop()
            except Exception:
                pass

    def status(self, *, include_receivers: bool = False) -> dict[str, object]:
        with self._lock:
            adapters = tuple(self._adapters)
        providers: dict[str, dict[str, int]] = defaultdict(
            lambda: {"connected": 0, "disconnected": 0, "failed": 0}
        )
        receiver_rows: list[dict[str, object]] = []
        for provider, failed in self._failed_by_provider.items():
            providers[provider]["failed"] += int(failed)
        health_by_receiver: dict[str, object] = {}
        for descriptor, adapter in adapters:
            try:
                health = adapter.health()
                health_by_receiver[descriptor.receiver_id] = health
                provider = health.provider if health.provider in {"kiwisdr", "openwebrx"} else "other"
                state = "connected" if health.connected else "disconnected"
                providers[provider][state] += 1
            except Exception:
                providers["other"]["failed"] += 1
        if include_receivers:
            for descriptor in self._registry.runnable() if self.enabled else self._registry.all():
                health = health_by_receiver.get(descriptor.receiver_id)
                connected = bool(getattr(health, "connected", False))
                last_message_at = getattr(health, "last_message_at", None)
                receiver_rows.append(
                    {
                        "receiver_id": descriptor.receiver_id,
                        "station_label": descriptor.public_label,
                        "provider": descriptor.provider,
                        "state": "connected" if connected else "disconnected",
                        "channel_kind": descriptor.channel_kind,
                        "frequency_hz": descriptor.frequency_hz,
                        "mode": descriptor.mode,
                        "last_observation_at": (
                            last_message_at.isoformat() if last_message_at is not None else None
                        ),
                        "observations_received": int(
                            getattr(health, "observations_received", 0) or 0
                        ),
                    }
                )
        result: dict[str, object] = {
            "enabled": self.enabled,
            "configured": len(self._registry.all()),
            "runnable": len(self._registry.runnable()) if self.enabled else 0,
            "started": len(adapters),
            "failed": sum(self._failed_by_provider.values()),
            "providers": {key: dict(value) for key, value in sorted(providers.items())},
        }
        if include_receivers:
            result["receivers"] = receiver_rows
        return result


_runtime: RemoteRadioRuntime | None = None


def start_remote_radio_from_config() -> RemoteRadioRuntime:
    global _runtime
    if _runtime is not None:
        return _runtime
    from core.config import config
    from core.radio.registry import load_receiver_descriptors

    registry = load_receiver_descriptors(
        raw_json=config.REMOTE_RADIO_RECEIVERS_JSON,
        file_path=config.REMOTE_RADIO_RECEIVERS_FILE,
        max_receivers=config.REMOTE_RADIO_MAX_RECEIVERS,
    )
    _runtime = RemoteRadioRuntime(
        enabled=config.REMOTE_RADIO_ENABLED,
        descriptors=registry.all(),
        max_receivers=config.REMOTE_RADIO_MAX_RECEIVERS,
    )
    _runtime.start()
    from core.radio.bridge import register_radio_acquisition_status

    register_radio_acquisition_status()
    return _runtime


def get_remote_radio_status(*, include_receivers: bool = False) -> dict[str, object]:
    if _runtime is not None:
        return _runtime.status(include_receivers=include_receivers)
    from core.config import config

    return {
        "enabled": bool(config.REMOTE_RADIO_ENABLED),
        "configured": 0,
        "runnable": 0,
        "started": 0,
        "failed": 0,
        "providers": {},
        **({"receivers": []} if include_receivers else {}),
    }
