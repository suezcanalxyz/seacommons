# SPDX-License-Identifier: AGPL-3.0-or-later
"""Durable background drift orchestration for intelligence events."""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any

from core.api.ratelimit import acquire_drift_slot, release_drift_slot
from core.intel.public_policy import HUMANITARIAN_DRIFT_DOMAINS
from core.intel.store import intel_store

logger = logging.getLogger(__name__)


# ── Auto-drift evidence eligibility ───────────────────────────────────────────
# docs/fixes.md F-01 (P0/critical): a drift model must never originate from
# disputed / unverified / non-maritime location evidence. `force=True` (an
# OCR-upgrade recompute or a refresher re-run) may bypass the once-only dedup
# guard but NEVER this policy. One gate, called from every auto/backfill drift
# path (this module's schedule_intel_drift chokepoint, plus the public
# auto-drift route for an explainable 400, plus twikit's pre-flight check so a
# disputed OCR produces exactly zero drift requests).
AUTO_DRIFT_POLICY_VERSION = "auto-drift-eligibility/1"

# Coordinate review states trusted enough to seed an operational leeway model.
_TRUSTED_REVIEW_STATES = frozenset(
    {
        "not_required",  # coordinate parsed from post text, no OCR involved
        "machine_ocr_consensus_verified",  # EasyOCR + an independent Tesseract pass agree
        "human_verified",
        "reported_exact",
    }
)
# Coordinate provenances trustworthy even without an explicit review status.
_TRUSTED_COORD_SOURCES = frozenset({"post_text", "navtext", "ais_position"})
# Provenances explicitly too coarse / unverified to originate a drift.
_BLOCKED_COORD_SOURCES = frozenset(
    {
        "",
        "none",
        "region_area",
        "place_centroid",
        "relative_place_offset",
        "post_text_or_maritime_place",
        "maritime_place",
        "media_pin_landmark",
        "media_ocr_text",
        "media_ocr_text_backfill",
        "media_pin_landmark_backfill",
    }
)
_NON_MARITIME_LOCATION_STATES = frozenset(
    {
        "withheld_from_maritime_map",
        "region_only",
        "unpositioned",
        "processing",
        "disputed",
        "needs_review",
    }
)
_DRIFT_BLOCKING_LIFECYCLES = frozenset({"resolved", "archived"})

MAX_AUTO_DRIFT_UNCERTAINTY_M = float(os.getenv("AUTO_DRIFT_MAX_UNCERTAINTY_M", "10000"))


def _lifecycle_state(event: Any) -> str:
    try:
        from core.intel import lifecycle

        return lifecycle.distress_lifecycle(event, now=datetime.now(UTC), same_source=[])
    except Exception:  # pragma: no cover - lifecycle must never block the gate
        meta = getattr(event, "metadata", {}) or {}
        return str(meta.get("incident_lifecycle") or "active")


def is_auto_drift_eligible(event: Any) -> tuple[bool, str]:
    """Whether an intel event's location evidence may originate a SAR drift.

    Returns ``(eligible, reason)``. ``reason`` is a short machine-readable
    string persisted on the event and surfaced by the auto-drift route on
    rejection.
    """
    domain = event.maritime_domain()
    if domain not in HUMANITARIAN_DRIFT_DOMAINS:
        return False, f"maritime_domain={domain} (drift is humanitarian SAR only)"

    if getattr(event, "type", "") == "iom_incident":
        # IOM Missing Migrants is a retrospective dataset -- never a live,
        # minute-by-minute distress model (docs/fixes.md sec 3.3 / Phase 3).
        return False, "iom_incident is retrospective, not a live drift origin"

    if event.tier() != "operational":
        return False, f"tier={event.tier()} (not an operational distress case)"

    meta = getattr(event, "metadata", {}) or {}

    lifecycle_state = _lifecycle_state(event)
    if lifecycle_state in _DRIFT_BLOCKING_LIFECYCLES:
        return False, f"incident_lifecycle={lifecycle_state}"

    sea_land = str(meta.get("sea_land_class") or "").upper()
    if sea_land and sea_land != "SEA":
        return False, f"sea_land_class={sea_land} (not SEA)"

    location_status = str(meta.get("location_status") or "").lower()
    if location_status in _NON_MARITIME_LOCATION_STATES:
        return False, f"location_status={location_status}"

    review = str(meta.get("coordinate_review_status") or "").lower()
    if "disputed" in review or "needs_review" in review:
        return False, f"coordinate_review_status={review}"

    coord_source = str(meta.get("coordinate_source") or "").lower()
    trusted = review in _TRUSTED_REVIEW_STATES or coord_source in _TRUSTED_COORD_SOURCES
    if not trusted or coord_source in _BLOCKED_COORD_SOURCES:
        return False, (
            "location evidence not verified for operational modelling "
            f"(review={review or 'none'}, source={coord_source or 'none'})"
        )

    uncertainty = meta.get("location_uncertainty_m")
    try:
        if uncertainty is not None and float(uncertainty) > MAX_AUTO_DRIFT_UNCERTAINTY_M:
            return False, (
                f"location_uncertainty_m={uncertainty} exceeds "
                f"{MAX_AUTO_DRIFT_UNCERTAINTY_M:.0f}"
            )
    except (TypeError, ValueError):
        pass

    return True, "eligible"


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
        cfg: dict = {}
        if vessel_type:
            cfg["vessel_type"] = vessel_type
        if persons is not None:
            cfg["persons"] = persons
        # Seed the drift ensemble over the report's actual position
        # uncertainty, not a fixed 150 m -- a boat located only to a named
        # SAR zone must not produce a falsely confident start.
        event = intel_store.get(event_id)
        if event is not None:
            uncertainty = event.metadata.get("location_uncertainty_m")
            case_type = event.metadata.get("case_type")
            if case_type:
                cfg["case_type"] = case_type
            try:
                if uncertainty is not None:
                    cfg["seed_radius_m"] = max(150.0, min(float(uncertainty), 50_000.0))
            except (TypeError, ValueError):
                pass
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
    background: bool = True,
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
    # F-01 evidence gate -- authoritative chokepoint. Runs after the idempotency
    # check (which schedules nothing) but before `force` can take effect, so an
    # OCR-upgrade recompute or a refresher re-run cannot bypass it either.
    if event is not None:
        eligible, reason = is_auto_drift_eligible(event)
        if not eligible:
            logger.info("auto-drift blocked for intel event %s: %s", normalized_id, reason)
            intel_store.update_metadata(
                normalized_id,
                metadata={
                    "drift_status": "ineligible",
                    "drift_ineligible_reason": reason,
                    "drift_policy_version": AUTO_DRIFT_POLICY_VERSION,
                },
            )
            return False
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
        args = (normalized_id, lat, lon, persons, vessel_type, observed_at)
        if background:
            threading.Thread(target=_run_intel_drift, args=args, daemon=True).start()
        else:
            # CLI/backfill callers must keep the process alive until the model
            # has persisted its result; a daemon thread would be discarded as
            # soon as the command exits.
            _run_intel_drift(*args)
    except Exception:
        release_drift_slot()
        intel_store.update_metadata(normalized_id, metadata={"drift_status": "failed"})
        raise
    return True
