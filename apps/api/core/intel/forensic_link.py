# SPDX-License-Identifier: AGPL-3.0-or-later
"""Attach a signed forensic evidentiary packet to a distress intel event.

The forensic packet system (core.forensic.*: blake3 hash + ed25519
signature, verifiable via /api/v1/forensic/{event_id}/verify) already
existed but was only ever wired to a separate manual-alerts flow -- the
actual OSINT-sourced distress events shown on Live never got one. This
connects it, using the intel event's own id as the forensic event_id, so
the same id shown on the map is directly queryable for its evidentiary
record. Signing happens wherever ingestion runs (the monitors host);
verification happens wherever the API runs (a different host) -- both
share SUEZCANAL_SIGNING_KEY, so a packet signed on one is verifiable on
the other.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Same discipline as the public feed (core.intel.public_geometry /
# core.api.routes.live): never let a private caller-sourced value leak
# into an exported/verifiable record -- an explicit allowlist, not "the
# whole metadata dict minus a blocklist".
_SENSOR_DATA_KEYS = (
    "source", "url", "verification_status", "coordinate_source",
    "coordinate_review_status", "media_count", "tracked_account",
    "platform", "report_kind", "location_uncertainty_m", "area_confidence",
)

_CONFIDENCE_BY_SOURCE = {
    "post_text": 0.95,
    "media_ocr_text": 0.85,
    "media_pin_landmark": 0.7,
    "relative_place_offset": 0.55,
    "place_centroid": 0.35,
    "region_area": 0.3,
}


def attach_forensic_packet(event: Any) -> None:
    """Best-effort, fire-and-forget; never raises to the caller and never
    blocks the ingestion loop (signing + DB write run on a background
    thread, same pattern as intel_store's own location persistence)."""
    if event.lat is None or event.lon is None:
        return
    if os.getenv("SEACOMMONS_FORENSIC_SYNC", "").lower() in {"1", "true", "yes"}:
        _build_and_sign(event)
        return
    threading.Thread(
        target=_build_and_sign,
        args=(event,),
        daemon=True,
        name=f"forensic-{event.id}",
    ).start()


def _build_and_sign(event: Any) -> None:
    try:
        from core.forensic.logger import sign_and_store
        from core.forensic.packet import ForensicPacket

        metadata = event.metadata or {}
        sensors = ["twitter"]
        tracked = metadata.get("tracked_account")
        if tracked:
            sensors.append(f"twitter:{tracked}")
        coordinate_source = str(metadata.get("coordinate_source") or "")
        if coordinate_source.startswith("media_"):
            sensors.append("image_ocr")

        packet = ForensicPacket(
            event_id=str(event.id),
            timestamp_utc=event.timestamp_utc,
            classification=str(metadata.get("report_kind") or "distress_report"),
            confidence=_CONFIDENCE_BY_SOURCE.get(coordinate_source, 0.4),
            position={
                "lat": event.lat,
                "lon": event.lon,
                "alt": 0,
                "source": coordinate_source or "unknown",
            },
            vessel_id=event.linked_mmsi or "",
            contributing_sensors=sensors,
            sensor_data={key: metadata[key] for key in _SENSOR_DATA_KEYS if key in metadata},
        )
        sign_and_store(packet)
        logger.info("forensic packet attached: %s", event.id)
    except Exception as exc:
        logger.debug("forensic packet attach failed for %s: %s", event.id, exc)
