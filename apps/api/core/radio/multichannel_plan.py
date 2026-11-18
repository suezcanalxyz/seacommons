"""Explicit, operator-gated channel assignment for an independently authorized SDR.

This is a configuration compiler, NOT an SDR scanner. No new sockets are
opened merely because a channel exists or a public receiver publishes a band.
"""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Iterable

from core.radio.registry import ReceiverDescriptor

MARITIME_CHANNEL_TARGETS = {
    ("dsc", 2_187_500): "usb",
    ("dsc", 4_207_500): "usb",
    ("dsc", 6_312_000): "usb",
    ("dsc", 8_414_500): "usb",
    ("dsc", 12_577_000): "usb",
    ("dsc", 16_804_500): "usb",
    ("navtex", 490_000): "am",
    ("navtex", 518_000): "am",
}

def configure_opt_in_channels(
    descriptors: Iterable[ReceiverDescriptor], raw_json: str,
) -> tuple[ReceiverDescriptor, ...]:
    """Apply a fully explicit operator-approved one-device/one-channel manifest.

    All assignments must identify a receiver already present in the operator's
    configured descriptor list, never an unreviewed directory hit.
    The caller may combine these descriptors with pre-existing receiver config;
    no new physical lineage is created and VHF is deliberately unsupported.
    """
    try:
        data = json.loads(raw_json)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid multichannel assignment JSON") from exc
    if not isinstance(data, list) or len(data) > 16:
        raise ValueError("multichannel assignments must be a list of at most 16 entries")
    available = {row.receiver_id: row for row in descriptors}
    output: list[ReceiverDescriptor] = []
    used_lineage: set[str] = set()
    used_receivers: set[str] = set()
    for item in data:
        if not isinstance(item, dict) or item.get("operator_authorized") is not True:
            raise ValueError("explicit receiver operator authorization required")
        receiver_id = str(item.get("receiver_id") or "")
        original = available.get(receiver_id)
        if original is None or original.terms_status != "allowed" or not original.enabled:
            raise ValueError("unknown, disabled or non-authorized receiver")
        kind = str(item.get("channel_kind") or "")
        try:
            frequency = int(item.get("frequency_hz"))
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid radio channel frequency") from exc
        mode = MARITIME_CHANNEL_TARGETS.get((kind, frequency))
        if mode is None:
            raise ValueError("channel unsupported by the deployed decoder")
        if receiver_id in used_receivers or original.physical_lineage in used_lineage:
            raise ValueError("one physical receiver may monitor only one assigned channel")
        if not any(
            cap.frequency_min_hz <= frequency <= cap.frequency_max_hz and mode in cap.modes
            for cap in original.capabilities
        ):
            raise ValueError("receiver cannot tune the assigned frequency and mode")
        output.append(replace(original, channel_kind=kind, frequency_hz=frequency, mode=mode))
        used_lineage.add(original.physical_lineage)
        used_receivers.add(receiver_id)
    return tuple(output)
