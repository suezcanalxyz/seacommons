# SPDX-License-Identifier: AGPL-3.0-or-later
"""Normalization and persistence for operator-supplied intelligence."""

from __future__ import annotations

import logging

from core.domain.live_contracts import PublicationStatus, SourcePolicy, VerificationStatus
from core.intel.geoextract import (
    classify_severity,
    extract_coords,
    extract_numeric_coords,
    extract_relative_coords,
    is_direct_distress_call,
)
from core.intel.source_registry import source_registry
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)


def _record_source_observation(
    *, source_name: str, source_id: str, source_policy: str, raw_payload: str,
    observed_at: str, source_url: str = "", lat: float | None = None, lon: float | None = None,
) -> None:
    """docs/fixes.md M1.2: a durable SourceObservation for an operator-
    supplied report (console manual entry or an operator's own external
    script feed). Best-effort and strictly additive: never raises into
    the caller, never alters what gets stored/published. The existing
    intel_store.add() write path remains authoritative until a parity
    comparison (a later PR) proves this envelope is equivalent.
    """
    if not source_id:
        # No stable delivery key -- e.g. store_external_event() with no
        # source_id supplied doesn't dedupe its own IntelEvent either in
        # that case; recording an observation would have nothing genuine
        # to be idempotent by.
        return
    try:
        from datetime import datetime, timezone

        from core.db.session import session_scope
        from core.intel.source_observation import record_observation

        with session_scope() as db:
            record_observation(
                db,
                service="humanitarian",
                lane="review",
                observation_type="source_post",
                source_name=source_name,
                source_policy=source_policy,
                source_id=source_id,
                observed_at=observed_at or datetime.now(timezone.utc).isoformat(),
                raw_payload=raw_payload,
                source_url=source_url,
                lat=lat,
                lon=lon,
            )
    except Exception as exc:
        logger.debug("ingestion_service: source_observation record skipped for %s: %s", source_id, exc)


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
    if stored:
        from datetime import datetime, timezone

        _record_source_observation(
            source_name="Manual",
            # A console entry carries no external delivery key -- the
            # generated event id is the closest stable identity, and
            # unlike a replayed feed item a second manual submission with
            # identical text is a genuinely new operator action, not a
            # redelivery, so a fresh id each time is correct here.
            source_id=event.id,
            source_policy="operator_asserted",
            raw_payload=f"{title}\n{text}",
            observed_at=datetime.now(timezone.utc).isoformat(),
            source_url=url,
            lat=lat,
            lon=lon,
        )
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
        "verification_status": VerificationStatus.OPERATOR_ASSERTED.value,
        "coordinate_source": (
            "post_text" if lat is not None or numeric_coords else "place_centroid"
        ),
    }
    if publish:
        metadata["publication_status"] = PublicationStatus.PUBLISHED.value
        metadata["source_policy"] = SourcePolicy.OPERATOR_PUBLISHED.value

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
    _record_source_observation(
        source_name=source_name,
        source_id=source_id,
        source_policy="operator_asserted",
        raw_payload=f"{title}\n{text}",
        observed_at=timestamp_utc or "",
        source_url=url,
        lat=coords[0] if coords else None,
        lon=coords[1] if coords else None,
    )
    if added and distress:
        from core.intel.triangulation import evaluate as evaluate_triangulation

        evaluate_triangulation(event)
    return event, added
