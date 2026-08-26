# SPDX-License-Identifier: AGPL-3.0-or-later
"""Durable background drift orchestration for intelligence events."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from core.api.ratelimit import acquire_drift_slot, release_drift_slot
from core.intel.store import intel_store

logger = logging.getLogger(__name__)


def _run_intel_drift(
    event_id: str,
    lat: float,
    lon: float,
    persons: int | None,
    vessel_type: str | None,
    observed_at: str,
) -> None:
    """Background: compute drift from an intel event's position."""
    try:
        _run_intel_drift_inner(event_id, lat, lon, persons, vessel_type, observed_at)
    finally:
        release_drift_slot()


def _run_intel_drift_inner(
    event_id: str,
    lat: float,
    lon: float,
    persons: int | None,
    vessel_type: str | None,
    observed_at: str,
) -> None:
    import math
    import uuid
    from datetime import datetime

    from core.db.store import complete_drift_job, create_drift_job, fail_drift_job
    from core.drift.engine import DriftEngine

    job_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    try:
        time_utc = datetime.fromisoformat(observed_at)
        if time_utc.tzinfo is None:
            time_utc = time_utc.replace(tzinfo=UTC)
        time_utc = min(time_utc.astimezone(UTC), now)
    except (AttributeError, TypeError, ValueError):
        time_utc = now
    elapsed_h = max(0.0, (now - time_utc).total_seconds() / 3600)
    duration_h = min(72, max(24, math.ceil(elapsed_h) + 12))
    create_drift_job(
        job_id,
        event_id=f"intel:{event_id}",
        lat=lat,
        lon=lon,
        domain="ocean_sar",
        duration_h=duration_h,
        started_at=time_utc,
    )
    try:
        engine = DriftEngine()
        cfg = {}
        if vessel_type:
            cfg["vessel_type"] = vessel_type
        if persons is not None:
            cfg["persons"] = persons
        result = engine.compute(
            lat=lat,
            lon=lon,
            time_utc=time_utc,
            duration_h=duration_h,
            domain="ocean_sar",
            config=cfg,
        )
        complete_drift_job(
            job_id,
            event_id=f"intel:{event_id}",
            lat=lat,
            lon=lon,
            domain="ocean_sar",
            result=result,
        )
        intel_store.update_metadata(
            event_id,
            metadata={
                "drift_job_id": job_id,
                "drift_status": "completed",
                "drift_origin_timestamp_utc": time_utc.isoformat(),
                "drift_duration_h": duration_h,
                "drift_completed_at": datetime.now(UTC).isoformat(),
            },
        )
        intel_store.broadcast_event_update(
            event_id, {"drift_job_id": job_id, "drift_status": "completed"}
        )
        logger.info("Auto-drift completed for intel event %s → job %s", event_id, job_id)
    except Exception as exc:  # noqa: BLE001 - job failures must be persisted uniformly
        fail_drift_job(
            job_id,
            event_id=f"intel:{event_id}",
            lat=lat,
            lon=lon,
            domain="ocean_sar",
            error_message=str(exc),
        )
        intel_store.update_metadata(
            event_id,
            metadata={
                "drift_job_id": job_id,
                "drift_status": "failed",
                "drift_error": str(exc)[:240],
            },
        )
        logger.warning("Auto-drift failed for intel event %s: %s", event_id, exc)


def schedule_intel_drift(
    event_id: str,
    lat: float,
    lon: float,
    persons: int | None,
    vessel_type: str | None,
    observed_at: str,
    *,
    force: bool = False,
) -> bool:
    """Start one durable-linked drift if the shared model slot is available.

    `force` bypasses the once-only guard so a refresher can re-run an
    already-completed drift against freshly observed wind/current forcing —
    the whole point of keeping the drift live as conditions change. It still
    respects the global model slot; a busy engine returns False.
    """
    normalized_id = event_id.removeprefix("intel:")
    event = intel_store.get(normalized_id)
    if event and event.metadata.get("drift_status") in {"computing", "completed"} and not force:
        return True
    if not acquire_drift_slot():
        return False
    intel_store.update_metadata(
        normalized_id,
        metadata={
            "drift_status": "computing",
            "drift_requested_at": datetime.now(UTC).isoformat(),
            "drift_origin_timestamp_utc": observed_at,
        },
    )
    try:
        threading.Thread(
            target=_run_intel_drift,
            args=(normalized_id, lat, lon, persons, vessel_type, observed_at),
            daemon=True,
        ).start()
    except Exception:
        release_drift_slot()
        intel_store.update_metadata(normalized_id, metadata={"drift_status": "failed"})
        raise
    return True
