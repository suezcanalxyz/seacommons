# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alarm Phone location-evidence triage for drift modelling.

A reported precise point may seed physical OpenDrift. A text-inferred search
region is an *initial spatial prior*, never an observed location or a 24-hour
OpenDrift probability contour. A future ensemble must advect multiple seeds
using the same ocean forcing before calling it a macro drift forecast.
"""
from __future__ import annotations

import re
from typing import Any

from core.intel.geoextract import find_all_place_matches


def source_is_alarm_phone(event: Any) -> bool:
    meta = getattr(event, "metadata", {}) or {}
    identity = str(getattr(event, "source", "") or meta.get("tracked_account") or "")
    return identity.lower().lstrip("@").replace(" ", "").replace("_", "") == "alarmphone"


def explicit_distress_flag(value: Any) -> bool:
    """Accept only explicit positive distress metadata, never bool("false").

    RSS and social adapters may serialize booleans as strings. Ambiguous
    values must not create an operational Alarm Phone drift candidate.
    """
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return isinstance(value, int) and value == 1


def location_clues(text: str) -> list[dict[str, str]]:
    """Extract source-language place roles with local context, never as certainty.

    A place mentioned as a notified authority cannot silently become an
    origin. A departure point constrains a corridor, not the current fix.
    """
    clues = []
    for name, _coords, _tier in find_all_place_matches(text):
        for match in list(re.finditer(re.escape(name), text, flags=re.IGNORECASE))[:3]:
            context = text[max(0, match.start() - 85):min(len(text), match.end() + 65)].lower()
            before = text[max(0, match.start() - 55):match.start()].lower()
            if re.search(r"(?:coast\s*guard|authorit|informed|alerted|contacted|notified|police|emergency\s*services)[^.!?]{0,55}$", before):
                role = "authority_notified"
            elif re.search(r"(?:departed|left|set\s*sail|sailed|departure|from|parti|quitt|salp)[^.!?]{0,35}$", before):
                role = "possible_departure"
            elif re.search(r"(?:heading\s*to|toward|towards|destination|arriv|trying\s*to\s*reach)[^.!?]{0,45}$", before):
                role = "possible_destination"
            elif re.search(r"(?:near|off|close\s*to|between|vicinity|south\s*of|north\s*of|east\s*of|west\s*of)[^.!?]{0,35}$", before):
                role = "reported_area"
            else:
                role = "mentioned_unclassified"
            clues.append({"place": name, "role": role, "text_context": context[:150]})
    return clues[:30]


def spatial_prior_for_event(event: Any) -> dict[str, Any]:
    """Record transparent evidence for a reported region, not a guessed fix."""
    meta = getattr(event, "metadata", {}) or {}
    source_text = " ".join(filter(None, [str(getattr(event, "title", "") or ""), str(getattr(event, "text", "") or "")]))
    matches = find_all_place_matches(source_text)
    polygon = meta.get("area_geojson")
    valid = isinstance(polygon, dict) and polygon.get("type") in {"Polygon", "MultiPolygon"} and bool(polygon.get("coordinates"))
    return {
        "candidate": source_is_alarm_phone(event) and explicit_distress_flag(meta.get("is_distress")),
        "geometry": polygon if valid else None,
        "location_evidence": "named_area_from_source_text" if valid else "no_geographic_area_resolved",
        "mentioned_places": [name for name, _, _ in matches][:20],
        "location_clues": location_clues(source_text),
        "spatial_model": "sea_only_text_inferred_prior" if valid else "pending_geographic_evidence",
        "physical_drift_computed": False,
        "calibrated_probability": False,
        "uncertainty": str(meta.get("area_confidence") or "unknown"),
    }
