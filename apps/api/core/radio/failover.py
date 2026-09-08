# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.radio.registry import ReceiverDescriptor

_CHANNEL_KINDS = frozenset({"dsc", "navtex", "monitor"})


@dataclass(frozen=True)
class ChannelTarget:
    channel_kind: str
    frequency_hz: int
    mode: str

    def __post_init__(self) -> None:
        kind = str(self.channel_kind or "").strip().lower()
        mode = str(self.mode or "").strip().lower()
        frequency = int(self.frequency_hz)
        if kind not in _CHANNEL_KINDS:
            raise ValueError("channel_kind must be dsc, navtex, or monitor")
        if frequency <= 0:
            raise ValueError("frequency_hz must be positive")
        if not mode:
            raise ValueError("mode is required")
        object.__setattr__(self, "channel_kind", kind)
        object.__setattr__(self, "frequency_hz", frequency)
        object.__setattr__(self, "mode", mode)


@dataclass(frozen=True)
class ChannelPlan:
    target: ChannelTarget
    desired_replicas: int
    active: tuple[ReceiverDescriptor, ...]
    standby: tuple[ReceiverDescriptor, ...]


def channel_target_for(descriptor: ReceiverDescriptor) -> ChannelTarget | None:
    if descriptor.frequency_hz is None or descriptor.mode is None:
        return None
    return ChannelTarget(
        descriptor.channel_kind,
        descriptor.frequency_hz,
        descriptor.mode,
    )


def build_channel_plans(
    descriptors: Iterable[ReceiverDescriptor],
    *,
    desired_replicas: int,
) -> tuple[ChannelPlan, ...]:
    replicas = int(desired_replicas)
    if replicas < 1 or replicas > 8:
        raise ValueError("desired_replicas must be between 1 and 8")

    grouped: dict[ChannelTarget, list[ReceiverDescriptor]] = {}
    seen_lineages: set[str] = set()
    for descriptor in descriptors:
        if descriptor.physical_lineage in seen_lineages:
            continue
        target = channel_target_for(descriptor)
        if target is None:
            continue
        seen_lineages.add(descriptor.physical_lineage)
        grouped.setdefault(target, []).append(descriptor)

    plans: list[ChannelPlan] = []
    for target, candidates in grouped.items():
        active = tuple(candidates[:replicas])
        standby = tuple(candidates[replicas:])
        plans.append(
            ChannelPlan(
                target=target,
                desired_replicas=replicas,
                active=active,
                standby=standby,
            )
        )
    return tuple(plans)
