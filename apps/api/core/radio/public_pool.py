from __future__ import annotations

from core.radio.catalog import rank_catalog
from core.radio.registry import ReceiverDescriptor


def public_receiver_pool() -> tuple[ReceiverDescriptor, ...]:
    """Use the scored persistent pool, falling back to curated seeds during bootstrap."""
    try:
        from core.radio.catalog_store import rank_persistent_catalog

        persisted = rank_persistent_catalog(
            target_frequency_hz=2_187_500,
            mode="usb",
            limit=64,
        )
        if persisted:
            return persisted
    except Exception:
        pass
    rows = rank_catalog("central_med", frequency_hz=2_187_500)
    return tuple(
        row.to_descriptor(2_187_500, "usb")
        for row in rows
        if row.activation_status == "eligible"
    )
