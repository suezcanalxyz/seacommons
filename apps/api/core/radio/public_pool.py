from __future__ import annotations

from core.radio.catalog import rank_catalog
from core.radio.registry import ReceiverDescriptor


def public_receiver_pool() -> tuple[ReceiverDescriptor, ...]:
    """Ranked free/public receiver pool for Central Mediterranean MF DSC monitoring."""
    rows = rank_catalog("central_med", frequency_hz=2_187_500)
    return tuple(row.to_descriptor(2_187_500, "usb") for row in rows if row.activation_status == "eligible")
