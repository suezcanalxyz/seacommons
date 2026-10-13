# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alarm Phone location-evidence triage for drift modelling.

A reported precise point may seed physical OpenDrift. A text-inferred search
region is an *initial spatial prior*, never an observed location or a 24-hour
OpenDrift probability contour. A future ensemble must advect multiple seeds
using the same ocean forcing before calling it a macro drift forecast.
"""
from __future__ import annotations

from typing import Any

from core.intel.geoextract import find_all_place_matches


def source_is_alarm_phone(event: Any) -> bool:
    meta = getattr(event, "metadata", {}) or {}
    identity = str(getattr(event, "source", "") or meta.get("tracked_account") or "")
    return identity.lower().lstrip("@").replace(" ", "").replace("_", "") == "alarmphone"


def spatial_prior_for_event(event: Any) -> dict[str, Any]:
    """Record transparent evidence for a reported region, not a guessed fix."""
    meta = getattr(event, "metadata", {}) or {}
    source_text = " ".join(filter(None, [str(getattr(event, "title", "") or ""), str(getattr(event, "text", "") or "")]))
    matches = find_all_place_matches(source_text)
    polygon = meta.get("area_geojson")
    valid = isinstance(polygon, dict) and polygon.get("type") in {"Polygon", "MultiPolygon"} and bool(polygon.get("coordinates"))
    return {
        "candidate": source_is_alarm_phone(event) and bool(meta.get("is_distress")),
        "geometry": polygon if valid else None,
        "location_evidence": "named_area_from_source_text" if valid else "no_geographic_area_resolved",
        "mentioned_places": [name for name, _, _ in matches][:20],
        "spatial_model": "sea_only_text_inferred_prior" if valid else "pending_geographic_evidence",
        "physical_drift_computed": False,
        "calibrated_probability": False,
        "uncertainty": str(meta.get("area_confidence") or "unknown"),
    }
