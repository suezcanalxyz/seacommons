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


PUBLIC_CHANNELS = (
    ("MF DSC", "dsc", 2_187_500, True),
    ("HF DSC 4 MHz", "dsc", 4_207_500, True),
    ("HF DSC 6 MHz", "dsc", 6_312_000, True),
    ("HF DSC 8 MHz", "dsc", 8_414_500, True),
    ("HF DSC 12 MHz", "dsc", 12_577_000, True),
    ("HF DSC 16 MHz", "dsc", 16_804_500, True),
    ("NAVTEX national", "navtex", 490_000, True),
    ("NAVTEX international", "navtex", 518_000, True),
    ("HF NAVTEX", "navtex", 4_209_500, False),
    ("VHF DSC Ch70", "vhf_dsc", 156_525_000, False),
    ("VHF voice Ch16", "vhf_voice", 156_800_000, False),
)


def public_channel_status(runtime_receivers: Iterable[dict]) -> list[dict[str, object]]:
    """Map *current* connected receiver tuning to the public channel matrix.

    No supported receiver band is counted until the runtime explicitly reports
    a connected receiver on the exact nominal frequency.
    """
    active = tuple(
        row for row in runtime_receivers
        if row.get("state") == "connected" and row.get("receiver_id")
    )
    result = []
    for label, family, frequency, decoder_ready in PUBLIC_CHANNELS:
        ids = {str(row["receiver_id"]) for row in active
               if row.get("frequency_hz") == frequency}
        result.append({
            "label": label,
            "family": family,
            "frequency_hz": frequency,
            "decoder_ready": decoder_ready,
            "active_receivers": len(ids),
            "state": "receiving" if ids else "not_monitored",
        })
    return result
