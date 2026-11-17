# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alarm Phone location-evidence triage for drift modelling.

A reported precise point may seed physical OpenDrift. A text-inferred search
region is an *initial spatial prior*, never an observed location or a 24-hour
OpenDrift probability contour. A future ensemble must advect multiple seeds
using the same ocean forcing before calling it a macro drift forecast.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from core.intel.geoextract import find_all_place_matches


def source_is_alarm_phone(event: Any) -> bool:
    meta = getattr(event, "metadata", {}) or {}
    identity = str(getattr(event, "source", "") or meta.get("tracked_account") or "")
    return identity.lower().lstrip("@").replace(" ", "").replace("_", "") == "alarmphone"


def location_clues(text: str) -> list[dict[str, str]]:
    """Extract source-language place roles with local context, never as certainty.

    A place mentioned as a notified authority cannot silently become an
    origin. A departure point constrains a corridor, not the current fix.
    """
    indexed_clues: list[tuple[int, dict[str, str]]] = []
    for name, _coords, _tier in find_all_place_matches(text):
        for match in list(re.finditer(re.escape(name), text, flags=re.IGNORECASE))[:3]:
            context = text[max(0, match.start() - 85):min(len(text), match.end() + 65)].lower()
            before = text[max(0, match.start() - 55):match.start()].lower()
            if re.search(r"(?:heading\s*to|toward|towards|destination|arriv|trying\s*to\s*reach)[^.!?]{0,45}$", before):
                role = "possible_destination"
            elif re.search(r"(?:departed|left|set\s*sail|sailed|departure|from|parti|quitt|salp)[^.!?]{0,35}$", before):
                role = "possible_departure"
            elif re.search(r"(?:near|off|close\s*to|between|vicinity|south\s*of|north\s*of|east\s*of|west\s*of)[^.!?]{0,35}$", before):
                role = "reported_area"
            elif re.search(r"(?:coast\s*guard|authorit|informed|alerted|contacted|notified|police|emergency\s*services)[^.!?]{0,55}$", before):
                role = "authority_notified"
            else:
                role = "mentioned_unclassified"
            indexed_clues.append((match.start(), {"place": name, "role": role, "text_context": context[:150]}))
    indexed_clues.sort(key=lambda item: item[0])
    return [clue for _offset, clue in indexed_clues[:30]]


def _utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None  # Ambiguous local time must not become an elapsed-time estimate.
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


_MONTHS = {
    "january": 1, "janvier": 1, "gennaio": 1,
    "february": 2, "février": 2, "fevrier": 2, "febbraio": 2,
    "march": 3, "mars": 3, "marzo": 3,
    "april": 4, "avril": 4, "aprile": 4,
    "may": 5, "mai": 5, "maggio": 5,
    "june": 6, "juin": 6, "giugno": 6,
    "july": 7, "juillet": 7, "luglio": 7,
    "august": 8, "août": 8, "aout": 8, "agosto": 8,
    "september": 9, "septembre": 9, "settembre": 9,
    "october": 10, "octobre": 10, "ottobre": 10,
    "november": 11, "novembre": 11,
    "december": 12, "décembre": 12, "decembre": 12, "dicembre": 12,
}
_DEPARTURE_DATE_RE = re.compile(
    r"(?:departed|left|parti(?:e|es|s)?|quitt(?:é|e|és|ées)?|salp(?:ato|ata|ati|ate)?)"
    r"[^.!?]{0,120}?\b(?:on|le|il)?\s*(\d{1,2})\s+("
    + "|".join(sorted((re.escape(month) for month in _MONTHS), key=len, reverse=True))
    + r")\b",
    re.I,
)


def _departure_date_window(text: str, report_at: datetime | None) -> dict[str, Any] | None:
    """Extract a source-stated calendar date as a UTC day window, never an exact departure time."""
    if report_at is None:
        return None
    match = _DEPARTURE_DATE_RE.search(text or "")
    if match is None:
        return None
    day = int(match.group(1))
    month_name = match.group(2).casefold()
    month = _MONTHS.get(month_name)
    if month is None:
        return None
    year = report_at.year
    try:
        start = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None
    # A December departure mentioned in an early-January report belongs to the previous year.
    if start > report_at + timedelta(days=2):
        try:
            start = datetime(year - 1, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None
    end = start + timedelta(days=1)
    if start > report_at:
        return None
    return {
        "start_utc": start.isoformat(),
        "end_utc": end.isoformat(),
        "precision": "date_only",
        "source_phrase": match.group(0)[-160:],
    }


def _event_source_text(event: Any) -> str:
    meta = getattr(event, "metadata", {}) or {}
    parts = [str(getattr(event, "title", "") or ""), str(getattr(event, "text", "") or "")]
    for repost in list(meta.get("thread_reposts") or [])[-20:]:
        if isinstance(repost, dict) and repost.get("note"):
            parts.append(str(repost.get("note") or ""))
    return " ".join(part for part in parts if part).strip()


def temporal_route_evidence(event: Any) -> dict[str, Any]:
    """Extract route claims without turning a departure into a current fix.

    This is evidence triage, not a vessel-speed or ocean-current forecast.
    """
    meta = getattr(event, "metadata", {}) or {}
    text = _event_source_text(event)
    clues = location_clues(text)
    departure = [c for c in clues if c["role"] == "possible_departure"]
    destination = [c for c in clues if c["role"] == "possible_destination"]
    reported = [c for c in clues if c["role"] == "reported_area"]
    departure_at = _utc(meta.get("departure_at") or meta.get("departure_time"))
    last_contact_at = _utc(meta.get("last_contact_at") or meta.get("last_contact_time"))
    report_at = _utc(getattr(event, "timestamp_utc", None))
    departure_window = None if departure_at is not None else _departure_date_window(text, report_at)
    elapsed_to_report_min = elapsed_to_report_max = None
    if departure_window is not None and report_at is not None:
        window_start = _utc(departure_window.get("start_utc"))
        window_end = _utc(departure_window.get("end_utc"))
        if window_start is not None and window_end is not None and report_at >= window_start:
            elapsed_to_report_min = round(max(0.0, (report_at - window_end).total_seconds() / 3600), 2)
            elapsed_to_report_max = round((report_at - window_start).total_seconds() / 3600, 2)
    chronological = (departure_at is not None and last_contact_at is not None
                     and departure_at <= last_contact_at
                     and (report_at is None or last_contact_at <= report_at))
    elapsed = round((last_contact_at - departure_at).total_seconds() / 3600, 2) if chronological else None
    followups = [
        repost for repost in list(meta.get("thread_reposts") or [])[-20:]
        if isinstance(repost, dict) and repost.get("note")
    ]
    followup_times = [
        parsed for parsed in (_utc(repost.get("posted_at")) for repost in followups)
        if parsed is not None
    ]
    return {
        "departure_claims": departure,
        "destination_claims": destination,
        "reported_area_claims": reported,
        "reported_event_time": str(getattr(event, "timestamp_utc", "") or ""),
        "follow_up_count": len(followups),
        "latest_follow_up_at": max(followup_times).isoformat() if followup_times else None,
        "last_contact_time": str(meta.get("last_contact_at") or meta.get("last_contact_time") or ""),
        "departure_time": str(meta.get("departure_at") or meta.get("departure_time") or ""),
        "departure_time_window": departure_window,
        "elapsed_departure_to_report_hours_min": elapsed_to_report_min,
        "elapsed_departure_to_report_hours_max": elapsed_to_report_max,
        "elapsed_departure_to_contact_hours": elapsed,
        "chronology_status": "consistent" if chronological else "insufficient_or_inconsistent",
        "location_status": "unverified_route_claims",
        "estimated_current_position": None,
        "physical_drift_computed": False,
    }


def spatial_prior_for_event(event: Any) -> dict[str, Any]:
    """Build a source-derived search prior, never a guessed current position."""
    meta = getattr(event, "metadata", {}) or {}
    source_text = _event_source_text(event)
    clues = location_clues(source_text)
    mentioned_places = list(dict.fromkeys(
        str(clue.get("place") or "")
        for clue in clues
        if clue.get("role") != "authority_notified" and clue.get("place")
    ))[:20]
    polygon = meta.get("area_geojson")
    valid = isinstance(polygon, dict) and polygon.get("type") in {"Polygon", "MultiPolygon"} and bool(polygon.get("coordinates"))
    geometry = polygon if valid else None
    evidence = "named_area_from_source_text" if valid else "no_geographic_area_resolved"
    uncertainty = str(meta.get("area_confidence") or "unknown")
    spatial_model = "sea_only_text_inferred_prior" if valid else "pending_geographic_evidence"

    if geometry is None and str(meta.get("coordinate_source") or "").lower() == "region_area":
        try:
            from core.intel.area_extract import area_from_center

            region_area = area_from_center(
                getattr(event, "lat", None), getattr(event, "lon", None),
                meta.get("location_uncertainty_m"),
            )
            if region_area is not None:
                geometry = region_area.polygon
                evidence = "reported_region_radius_spatial_prior"
                uncertainty = region_area.confidence
                spatial_model = "sea_only_reported_region_prior"
        except Exception:
            pass

    has_followups = any(
        isinstance(repost, dict) and repost.get("note")
        for repost in list(meta.get("thread_reposts") or [])[-20:]
    )
    route_has_constraint = any(
        clue.get("role") in {"possible_destination", "reported_area"} for clue in clues
    )
    # Do not overwrite a source-provided polygon or a reported region with
    # a weaker text-derived corridor, even when a follow-up mentions a place.
    if (source_is_alarm_phone(event) and meta.get("is_distress")
            and route_has_constraint and geometry is None):
        try:
            from core.intel.area_extract import extract_area

            report_time = _utc(getattr(event, "timestamp_utc", None))
            route_area = extract_area(source_text, report_time=report_time)
            if route_area is not None:
                geometry = route_area.polygon
                evidence = (
                    "route_followup_text_spatial_prior"
                    if has_followups else "route_text_spatial_prior"
                )
                uncertainty = route_area.confidence
                spatial_model = "sea_only_route_followup_prior" if has_followups else "sea_only_route_prior"
        except Exception:
            pass

    return {
        "candidate": source_is_alarm_phone(event) and bool(meta.get("is_distress")),
        "geometry": geometry,
        "location_evidence": evidence,
        "mentioned_places": mentioned_places,
        "location_clues": clues,
        "temporal_route_evidence": temporal_route_evidence(event),
        "spatial_model": spatial_model,
        "physical_drift_computed": False,
        "calibrated_probability": False,
        "uncertainty": uncertainty,
    }
