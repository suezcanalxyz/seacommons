# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable

from core.radio.failover import ChannelTarget, build_channel_plans, channel_target_for
from core.radio.provider import RadioObservation, RemoteReceiverAdapter
from core.radio.registry import ReceiverDescriptor, ReceiverRegistry

AdapterFactory = Callable[[ReceiverDescriptor, Callable[[RadioObservation], None]], RemoteReceiverAdapter]


@dataclass
class _ManagedEntry:
    descriptor: ReceiverDescriptor
    adapter: RemoteReceiverAdapter
    state: str = "standby"
    activated_at: datetime | None = None
    retry_at: float = 0.0
    previously_active: bool = False


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
        fallback_descriptors: Iterable[ReceiverDescriptor] = (),
        adapter_factory: AdapterFactory = _default_adapter_factory,
        observation_handler: Callable[[RadioObservation], None] = _default_observation_handler,
        reconnect_interval_s: float = 15.0,
        failover_enabled: bool = False,
        channel_replicas: int = 3,
        stale_after_s: float = 30.0,
        retry_after_s: float = 120.0,
        monotonic_clock: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.enabled = bool(enabled)
        primary = tuple(descriptors)
        fallback = tuple(fallback_descriptors)
        self._registry = ReceiverRegistry(primary + fallback, max_receivers=max_receivers)
        self._adapter_factory = adapter_factory
        self._observation_handler = observation_handler
        self._adapters: list[tuple[ReceiverDescriptor, RemoteReceiverAdapter]] = []
        self._failed_by_provider: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._reconnect_interval_s = max(float(reconnect_interval_s), 1.0)
        self._stop_event = threading.Event()
        self._supervisor: threading.Thread | None = None
        self._failover_enabled = bool(failover_enabled)
        self._channel_replicas = max(1, min(int(channel_replicas), 8))
        self._stale_after_s = max(float(stale_after_s), 5.0)
        self._retry_after_s = max(float(retry_after_s), 30.0)
        self._monotonic = monotonic_clock
        self._utcnow = utcnow
        self._managed_entries: dict[str, _ManagedEntry] = {}
        self._managed_channels: dict[ChannelTarget, tuple[str, ...]] = {}
        self._failovers_by_target: dict[ChannelTarget, int] = defaultdict(int)

    def start(self) -> None:
        if not self.enabled:
            return
        self._stop_event.clear()
        with self._lock:
            if self._adapters or self._managed_entries:
                return
        from core.observability import record_remote_radio_event

        runnable = self._registry.runnable()
        if self._failover_enabled:
            self._start_managed(runnable)
            with self._lock:
                should_supervise = bool(self._managed_entries)
                if should_supervise and (self._supervisor is None or not self._supervisor.is_alive()):
                    self._supervisor = threading.Thread(
                        target=self._supervise, daemon=True, name="remote-radio-supervisor"
                    )
                    self._supervisor.start()
            return

        prepared = [
            (descriptor, self._adapter_factory(descriptor, self._observation_handler))
            for descriptor in runnable
        ]

        def _start_descriptor(descriptor: ReceiverDescriptor, adapter: RemoteReceiverAdapter) -> None:
            provider = descriptor.provider if descriptor.provider in {"kiwisdr", "openwebrx"} else "other"
            try:
                adapter.start()
                if descriptor.frequency_hz is not None and descriptor.mode is not None:
                    adapter.tune(descriptor.frequency_hz, descriptor.mode)
            except Exception:
                try:
                    adapter.stop()
                except Exception:
                    pass
                with self._lock:
                    self._failed_by_provider[provider] += 1
                    self._adapters.append((descriptor, adapter))
                record_remote_radio_event(provider=provider, state="disconnected", outcome="start_failed")
                return
            with self._lock:
                self._adapters.append((descriptor, adapter))
            record_remote_radio_event(provider=provider, state="connected", outcome="started")

        if prepared:
            with ThreadPoolExecutor(max_workers=len(prepared), thread_name_prefix="remote-radio-start") as pool:
                futures = [pool.submit(_start_descriptor, descriptor, adapter) for descriptor, adapter in prepared]
                for future in futures:
                    future.result()
        with self._lock:
            if self._adapters and (self._supervisor is None or not self._supervisor.is_alive()):
                self._supervisor = threading.Thread(
                    target=self._supervise, daemon=True, name="remote-radio-supervisor"
                )
                self._supervisor.start()

    def _start_managed(self, runnable: tuple[ReceiverDescriptor, ...]) -> None:
        from core.observability import record_remote_radio_event

        plans = build_channel_plans(runnable, desired_replicas=self._channel_replicas)
        active_ids = {row.receiver_id for plan in plans for row in plan.active}
        entries: dict[str, _ManagedEntry] = {}
        channels: dict[ChannelTarget, tuple[str, ...]] = {}
        for plan in plans:
            candidates = (*plan.active, *plan.standby)
            channels[plan.target] = tuple(row.receiver_id for row in candidates)
            for descriptor in candidates:
                entries[descriptor.receiver_id] = _ManagedEntry(
                    descriptor=descriptor,
                    adapter=self._adapter_factory(descriptor, self._observation_handler),
                )
        with self._lock:
            self._managed_entries = entries
            self._managed_channels = channels

        def _activate(entry: _ManagedEntry) -> None:
            descriptor = entry.descriptor
            provider = descriptor.provider if descriptor.provider in {"kiwisdr", "openwebrx"} else "other"
            try:
                entry.adapter.start()
                entry.adapter.tune(int(descriptor.frequency_hz), str(descriptor.mode))
            except Exception:
                try:
                    entry.adapter.stop()
                except Exception:
                    pass
                entry.state = "cooldown"
                entry.retry_at = self._monotonic() + self._retry_after_s
                with self._lock:
                    self._failed_by_provider[provider] += 1
                record_remote_radio_event(provider=provider, state="disconnected", outcome="start_failed")
                return
            entry.state = "active"
            entry.activated_at = self._utcnow()
            with self._lock:
                self._adapters.append((descriptor, entry.adapter))
            record_remote_radio_event(provider=provider, state="connected", outcome="started")

        prepared = [entries[receiver_id] for receiver_id in active_ids]
        if prepared:
            with ThreadPoolExecutor(max_workers=len(prepared), thread_name_prefix="remote-radio-start") as pool:
                for future in [pool.submit(_activate, entry) for entry in prepared]:
                    future.result()

    def _supervise(self) -> None:
        while not self._stop_event.wait(self._reconnect_interval_s):
            if self._failover_enabled:
                self._failover_once()
            else:
                self._reconnect_disconnected_once()

    def _failover_once(self) -> None:
        from core.observability import record_remote_radio_event

        now_mono = self._monotonic()
        with self._lock:
            for entry in self._managed_entries.values():
                if entry.state == "cooldown" and entry.retry_at <= now_mono:
                    entry.state = "standby"
                    provider = (
                        entry.descriptor.provider
                        if entry.descriptor.provider in {"kiwisdr", "openwebrx"}
                        else "other"
                    )
                    record_remote_radio_event(
                        provider=provider, state="disconnected", outcome="cooldown_retry"
                    )
            active_entries = tuple(
                entry for entry in self._managed_entries.values() if entry.state == "active"
            )

        for entry in active_entries:
            try:
                health = entry.adapter.health()
            except Exception:
                continue
            if health.connected:
                last_message_at = health.last_message_at
                activated_at = entry.activated_at
                if last_message_at is not None and last_message_at.tzinfo is None:
                    last_message_at = last_message_at.replace(tzinfo=timezone.utc)
                if activated_at is not None and activated_at.tzinfo is None:
                    activated_at = activated_at.replace(tzinfo=timezone.utc)
                references = [value for value in (last_message_at, activated_at) if value is not None]
                if not references:
                    continue
                reference = max(references)
                now = self._utcnow()
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)
                if (now - reference).total_seconds() <= self._stale_after_s:
                    continue
            descriptor = entry.descriptor
            provider = (
                descriptor.provider if descriptor.provider in {"kiwisdr", "openwebrx"} else "other"
            )
            try:
                entry.adapter.stop()
            except Exception:
                pass
            entry.state = "cooldown"
            entry.retry_at = self._monotonic() + self._retry_after_s
            entry.previously_active = True
            with self._lock:
                self._adapters = [
                    pair for pair in self._adapters if pair[0].receiver_id != descriptor.receiver_id
                ]
            target = channel_target_for(descriptor)
            if target is not None:
                with self._lock:
                    self._failovers_by_target[target] += 1
            record_remote_radio_event(provider=provider, state="disconnected", outcome="failover")

        for target, receiver_ids in tuple(self._managed_channels.items()):
            while True:
                active_count = sum(
                    1
                    for receiver_id in receiver_ids
                    if self._managed_entries[receiver_id].state == "active"
                )
                if active_count >= self._channel_replicas:
                    break
                candidate = next(
                    (
                        self._managed_entries[receiver_id]
                        for receiver_id in receiver_ids
                        if self._managed_entries[receiver_id].state == "standby"
                        and not self._managed_entries[receiver_id].previously_active
                    ),
                    None,
                )
                if candidate is None:
                    candidate = next(
                        (
                            self._managed_entries[receiver_id]
                            for receiver_id in receiver_ids
                            if self._managed_entries[receiver_id].state == "standby"
                        ),
                        None,
                    )
                if candidate is None:
                    break
                provider = (
                    candidate.descriptor.provider
                    if candidate.descriptor.provider in {"kiwisdr", "openwebrx"}
                    else "other"
                )
                try:
                    candidate.adapter.start()
                    candidate.adapter.tune(
                        int(candidate.descriptor.frequency_hz), str(candidate.descriptor.mode)
                    )
                except Exception:
                    try:
                        candidate.adapter.stop()
                    except Exception:
                        pass
                    candidate.state = "cooldown"
                    candidate.retry_at = self._monotonic() + self._retry_after_s
                    record_remote_radio_event(
                        provider=provider, state="disconnected", outcome="start_failed"
                    )
                    continue
                candidate.state = "active"
                candidate.activated_at = self._utcnow()
                with self._lock:
                    self._adapters.append((candidate.descriptor, candidate.adapter))
                record_remote_radio_event(
                    provider=provider, state="connected", outcome="standby_promoted"
                )

    def _reconnect_disconnected_once(self) -> None:
        from core.observability import record_remote_radio_event

        with self._lock:
            adapters = tuple(self._adapters)
        for descriptor, adapter in adapters:
            try:
                health = adapter.health()
            except Exception:
                continue
            if health.connected:
                continue
            provider = descriptor.provider if descriptor.provider in {"kiwisdr", "openwebrx"} else "other"
            try:
                adapter.stop()
                adapter.start()
                if descriptor.frequency_hz is not None and descriptor.mode:
                    adapter.tune(descriptor.frequency_hz, descriptor.mode)
            except Exception:
                record_remote_radio_event(
                    provider=provider, state="disconnected", outcome="reconnect_failed"
                )
                continue
            if self._failed_by_provider.get(provider, 0) > 0:
                self._failed_by_provider[provider] -= 1
                if self._failed_by_provider[provider] <= 0:
                    self._failed_by_provider.pop(provider, None)
            record_remote_radio_event(
                provider=provider, state="connected", outcome="reconnected"
            )

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            supervisor = self._supervisor
            self._supervisor = None
            if self._failover_enabled and self._managed_entries:
                adapters = tuple(
                    (entry.descriptor, entry.adapter) for entry in self._managed_entries.values()
                )
            else:
                adapters = tuple(self._adapters)
            self._adapters.clear()
            self._managed_entries.clear()
            self._managed_channels.clear()
        if supervisor is not None and supervisor is not threading.current_thread():
            supervisor.join(timeout=2.0)
        for _descriptor, adapter in adapters:
            try:
                adapter.stop()
            except Exception:
                pass

    def status(self, *, include_receivers: bool = False) -> dict[str, object]:
        with self._lock:
            adapters = tuple(self._adapters)
            managed_entries = dict(self._managed_entries)
            managed_channels = dict(self._managed_channels)
            failovers_by_target = dict(self._failovers_by_target)
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
            descriptors = list(self._registry.runnable() if self.enabled else self._registry.all())
            seen_ids: set[str] = set()
            for descriptor in descriptors:
                if descriptor.receiver_id in seen_ids:
                    continue
                seen_ids.add(descriptor.receiver_id)
                health = health_by_receiver.get(descriptor.receiver_id)
                connected = bool(getattr(health, "connected", False))
                last_message_at = getattr(health, "last_message_at", None)
                entry = managed_entries.get(descriptor.receiver_id)
                if entry is not None and entry.state in {"standby", "cooldown"}:
                    state = entry.state
                else:
                    state = "connected" if connected else "disconnected"
                receiver_rows.append(
                    {
                        "receiver_id": descriptor.receiver_id,
                        "station_label": descriptor.public_label,
                        "provider": descriptor.provider,
                        "state": state,
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
        connected_count = sum(
            1 for health in health_by_receiver.values()
            if bool(getattr(health, "connected", False))
        )
        configured_count = len({descriptor.physical_lineage for descriptor in self._registry.all()})
        result: dict[str, object] = {
            "enabled": self.enabled,
            "configured": configured_count,
            "runnable": len(self._registry.runnable()) if self.enabled else 0,
            "started": connected_count,
            "failed": sum(self._failed_by_provider.values()),
            "providers": {key: dict(value) for key, value in sorted(providers.items())},
        }
        if self._failover_enabled:
            result["channels"] = [
                {
                    "channel_kind": target.channel_kind,
                    "frequency_hz": target.frequency_hz,
                    "mode": target.mode,
                    "desired": self._channel_replicas,
                    "active": sum(
                        1 for receiver_id in receiver_ids
                        if managed_entries[receiver_id].state == "active"
                    ),
                    "standby": sum(
                        1 for receiver_id in receiver_ids
                        if managed_entries[receiver_id].state == "standby"
                    ),
                    "cooldown": sum(
                        1 for receiver_id in receiver_ids
                        if managed_entries[receiver_id].state == "cooldown"
                    ),
                    "failovers": int(failovers_by_target.get(target, 0)),
                }
                for target, receiver_ids in managed_channels.items()
            ][:8]
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
    configured_targets: list[ChannelTarget] = []
    for descriptor in registry.runnable():
        target = channel_target_for(descriptor)
        if target is not None and target not in configured_targets:
            configured_targets.append(target)
    fallback_descriptors = ()
    if config.REMOTE_RADIO_PUBLIC_POOL_ENABLED:
        from core.radio.public_pool import public_receiver_pool
        fallback_descriptors = public_receiver_pool(
            targets=tuple(configured_targets) or None,
            limit=max(0, int(config.REMOTE_RADIO_PUBLIC_POOL_MAX)),
        )
    effective_max = max(
        int(config.REMOTE_RADIO_MAX_RECEIVERS),
        len(registry.all()) + len(fallback_descriptors),
    )
    _runtime = RemoteRadioRuntime(
        enabled=config.REMOTE_RADIO_ENABLED,
        descriptors=registry.all(),
        fallback_descriptors=fallback_descriptors,
        max_receivers=effective_max,
        failover_enabled=bool(config.REMOTE_RADIO_FAILOVER_ENABLED),
        channel_replicas=int(config.REMOTE_RADIO_CHANNEL_REPLICAS),
        stale_after_s=float(config.REMOTE_RADIO_FAILOVER_STALE_S),
        retry_after_s=float(config.REMOTE_RADIO_FAILOVER_RETRY_S),
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
