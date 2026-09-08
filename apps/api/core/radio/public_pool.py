from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from core.radio.catalog import rank_catalog
from core.radio.failover import ChannelTarget
from core.radio.registry import ReceiverDescriptor

_DEFAULT_TARGET = ChannelTarget("monitor", 2_187_500, "usb")


def public_receiver_pool(
    targets: Iterable[ChannelTarget] | None = None,
    *,
    limit: int = 16,
) -> tuple[ReceiverDescriptor, ...]:
    """Return ranked, terms-allowed candidates for explicit channel targets."""
    resolved_targets = tuple(targets or (_DEFAULT_TARGET,))
    cap = max(0, int(limit))
    if not resolved_targets or cap == 0:
        return ()
    per_target = max(1, (cap + len(resolved_targets) - 1) // len(resolved_targets))
    result: list[ReceiverDescriptor] = []
    seen_lineages: set[str] = set()

    try:
        from core.radio.catalog_store import rank_persistent_catalog

        for target in resolved_targets:
            added = 0
            rows = rank_persistent_catalog(
                target_frequency_hz=target.frequency_hz,
                mode=target.mode,
                channel_kind=target.channel_kind,
                limit=max(cap, per_target * 3),
            )
            for row in rows:
                if row.physical_lineage in seen_lineages:
                    continue
                result.append(row)
                seen_lineages.add(row.physical_lineage)
                added += 1
                if added >= per_target or len(result) >= cap:
                    break
            if len(result) >= cap:
                break
        if result:
            return tuple(result[:cap])
    except Exception:
        result.clear()
        seen_lineages.clear()

    for target in resolved_targets:
        added = 0
        rows = rank_catalog("central_med", frequency_hz=target.frequency_hz, limit=max(cap, per_target * 3))
        for row in rows:
            if row.activation_status != "eligible" or row.physical_lineage in seen_lineages:
                continue
            descriptor = replace(
                row.to_descriptor(target.frequency_hz, target.mode),
                channel_kind=target.channel_kind,
            )
            result.append(descriptor)
            seen_lineages.add(row.physical_lineage)
            added += 1
            if added >= per_target or len(result) >= cap:
                break
        if len(result) >= cap:
            break
    return tuple(result[:cap])
