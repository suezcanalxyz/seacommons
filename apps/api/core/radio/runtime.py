# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Callable, Iterable

from core.radio.provider import RadioObservation, RemoteReceiverAdapter
from core.radio.registry import ReceiverDescriptor, ReceiverRegistry

AdapterFactory = Callable[[ReceiverDescriptor, Callable[[RadioObservation], None]], RemoteReceiverAdapter]


def _default_observation_handler(observation: RadioObservation) -> None:
    from core.db.session import session_scope
    from core.observability import record_remote_radio_event
    from core.radio.source_observation import persist_radio_observation

    try:
        with session_scope() as db:
            persist_radio_observation(db, observation)
        record_remote_radio_event(provider=observation.provider, state="connected", outcome="observation")
    except Exception:
        record_remote_radio_event(provider=observation.provider, state="connected", outcome="persist_failed")


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
        self._adapters: list[RemoteReceiverAdapter] = []
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
            except Exception:
                self._failed_by_provider[provider] += 1
                record_remote_radio_event(provider=provider, state="disconnected", outcome="start_failed")
                continue
            with self._lock:
                self._adapters.append(adapter)
            record_remote_radio_event(provider=provider, state="connected", outcome="started")

    def stop(self) -> None:
        with self._lock:
            adapters = tuple(self._adapters)
            self._adapters.clear()
        for adapter in adapters:
            try:
                adapter.stop()
            except Exception:
                pass

    def status(self) -> dict[str, object]:
        with self._lock:
            adapters = tuple(self._adapters)
        providers: dict[str, dict[str, int]] = defaultdict(
            lambda: {"connected": 0, "disconnected": 0, "failed": 0}
        )
        for provider, failed in self._failed_by_provider.items():
            providers[provider]["failed"] += int(failed)
        for adapter in adapters:
            try:
                health = adapter.health()
                provider = health.provider if health.provider in {"kiwisdr", "openwebrx"} else "other"
                state = "connected" if health.connected else "disconnected"
                providers[provider][state] += 1
            except Exception:
                providers["other"]["failed"] += 1
        return {
            "enabled": self.enabled,
            "configured": len(self._registry.all()),
            "runnable": len(self._registry.runnable()) if self.enabled else 0,
            "started": len(adapters),
            "failed": sum(self._failed_by_provider.values()),
            "providers": {key: dict(value) for key, value in sorted(providers.items())},
        }


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
    return _runtime


def get_remote_radio_status() -> dict[str, object]:
    if _runtime is not None:
        return _runtime.status()
    from core.config import config

    return {
        "enabled": bool(config.REMOTE_RADIO_ENABLED),
        "configured": 0,
        "runnable": 0,
        "started": 0,
        "failed": 0,
        "providers": {},
    }
