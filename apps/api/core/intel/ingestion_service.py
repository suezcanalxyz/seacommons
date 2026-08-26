# SPDX-License-Identifier: AGPL-3.0-or-later
"""Normalization and persistence for operator-supplied intelligence."""

from __future__ import annotations

from core.intel.geoextract import (
    classify_severity,
    extract_coords,
    extract_numeric_coords,
    extract_relative_coords,
    is_direct_distress_call,
)
from core.intel.source_registry import source_registry
from core.intel.store import IntelEvent, intel_store


def store_manual_event(
    *,
    title: str,
    text: str,
    source: str,
    severity: str,
    event_type: str,
    lat: float | None,
    lon: float | None,
    url: str,
    linked_mmsi: str,
) -> IntelEvent | None:
    source_registry.register("Manual", "manual")
    event = IntelEvent(
        type=event_type,
        severity=severity,
        lat=lat,
        lon=lon,
        title=title[:255],
        text=text[:1000],
        url=url[:511],
        source=source or "manual",
        linked_mmsi=linked_mmsi,
        metadata={"injected_manually": True},
    )
    stored = intel_store.add(event)
    source_registry.record_poll("Manual", events_found=1 if stored else 0)
    return event if stored else None


def store_external_event(
    *,
    source: str,
    source_id: str,
    text: str,
    title: str,
    url: str,
    lat: float | None,
    lon: float | None,
    timestamp_utc: str | None,
    publish: bool,
) -> tuple[IntelEvent, bool]:
    source_name = f"External / {source}"[:64]
    source_registry.register(source_name, "twitter")

    distress = is_direct_distress_call(text)
    numeric_coords = extract_numeric_coords(text)
    coords = (
        (lat, lon)
        if lat is not None and lon is not None
        else numeric_coords or extract_relative_coords(text) or extract_coords(text)
    )
    metadata = {
        "is_distress": distress,
        "verification_status": "operator_asserted",
        "coordinate_source": (
            "post_text" if lat is not None or numeric_coords else "place_centroid"
        ),
    }
    if publish:
        metadata["publication_status"] = "published"
        metadata["source_policy"] = "operator_published"

    event = IntelEvent(
        type="twitter",
        severity=classify_severity(text) if distress else "low",
        lat=coords[0] if coords else None,
        lon=coords[1] if coords else None,
        title=(title or text[:120])[:255],
        text=text[:600],
        url=url[:511],
        source=source_name,
        timestamp_utc=timestamp_utc or "",
        metadata=metadata,
    )
    dedup_key = f"external:{source}:{source_id}" if source_id else ""
    added = intel_store.add(event, dedup_key=dedup_key)
    source_registry.record_poll(source_name, events_found=1 if added else 0)
    if added and distress:
        from core.intel.triangulation import evaluate as evaluate_triangulation

        evaluate_triangulation(event)
    return event, added
