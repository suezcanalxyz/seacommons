# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical, people-centred metadata for public humanitarian incidents."""
from __future__ import annotations

import re
from typing import Any

from core.intel.geoextract import is_ongoing_incident, is_resolved_distress

_PEOPLE = re.compile(
    r"(?:(?P<approx>~|about|around|approximately|approx\.?|ca\.?)\s*)?"
    r"(?P<count>\d{1,4})\s*(?:people|persons|passengers|migrants|survivors)\b",
    re.I,
)


def _case_type(text: str, *, distress: bool, resolved: bool) -> str:
    value = re.sub(r"\s+", " ", text or "").lower()
    if re.search(r"\b(shipwreck|capsiz(?:e|ed|ing)|sank|sunk)\b", value):
        return "shipwreck"
    if re.search(r"\b(missing|where are they|loss of contact|lost contact)\b", value):
        return "missing_persons"
    if re.search(r"\b(intercept(?:ed|ion)|pushback)\b", value):
        return "interception"
    if re.search(r"\b(medical evacuation|medevac|medical emergency)\b", value):
        return "medical_evacuation"
    if re.search(r"\b(disembark(?:ed|ation)|port of safety|safe port)\b", value):
        return "disembarkation"
    if resolved or re.search(r"\b(rescued|rescue completed|arrived safely|all safe)\b", value):
        return "rescue_completed"
    if distress:
        return "distress_report"
    return "humanitarian_update"


def humanitarian_case_metadata(
    text: str,
    *,
    incident_id: str,
    source: str,
    distress: bool,
    resolved: bool | None = None,
) -> dict[str, Any]:
    """Build the stable case projection without inventing unavailable facts."""
    resolved = is_resolved_distress(text) if resolved is None else resolved
    people = _PEOPLE.search(text or "")
    ongoing = distress or is_ongoing_incident(text)
    if resolved:
        status = "resolved"
    elif ongoing:
        status = "ongoing"
    else:
        status = "reported"
    direct_source = str(source).lower().lstrip("@") == "alarm_phone"
    return {
        "humanitarian_case_id": f"HUM-X-{incident_id}",
        "humanitarian_case_type": _case_type(text, distress=distress, resolved=resolved),
        "humanitarian_status": status,
        "people_reported": int(people.group("count")) if people else None,
        "people_precision": "approximate" if people and people.group("approx") else "exact" if people else "unknown",
        "verification_level": "direct_humanitarian_source" if direct_source else "single_public_source",
        "source_count": 1,
    }
