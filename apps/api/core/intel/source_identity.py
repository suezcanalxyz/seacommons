from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SourceIdentityPolicy:
    identity_id: str
    service: str | None
    source_role: str
    may_open_incident: bool
    independence_group: str


def _key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "", text)


_POLICIES = {
    "alarm_phone": SourceIdentityPolicy("alarm_phone", "humanitarian", "operational_origin", True, "alarm_phone"),
    "sos_mediterranee": SourceIdentityPolicy("sos_mediterranee", "humanitarian", "verification", False, "sos_mediterranee"),
    "msf": SourceIdentityPolicy("msf", "humanitarian", "verification", False, "msf"),
    "sea_watch": SourceIdentityPolicy("sea_watch", "humanitarian", "verification", False, "sea_watch"),
    "open_arms": SourceIdentityPolicy("open_arms", "humanitarian", "verification", False, "open_arms"),
    "sos_humanity": SourceIdentityPolicy("sos_humanity", "humanitarian", "verification", False, "sos_humanity"),
    "sea_eye": SourceIdentityPolicy("sea_eye", "humanitarian", "verification", False, "sea_eye"),
    "resqship": SourceIdentityPolicy("resqship", "humanitarian", "verification", False, "resqship"),
    "emergency": SourceIdentityPolicy("emergency", "humanitarian", "verification", False, "emergency"),
    "iom_missing_migrants": SourceIdentityPolicy("iom_missing_migrants", "humanitarian", "archive_reference", False, "iom_missing_migrants"),
}

_ALIASES = {
    "alarmphone": "alarm_phone",
    "sosmediterranee": "sos_mediterranee",
    "sosmedintl": "sos_mediterranee",
    "msf": "msf",
    "msfsea": "msf",
    "seawatch": "sea_watch",
    "seawatchcrew": "sea_watch",
    "openarms": "open_arms",
    "openarmsfund": "open_arms",
    "proactivaopenarms": "open_arms",
    "soshumanity": "sos_humanity",
    "seaeye": "sea_eye",
    "seaeyeorg": "sea_eye",
    "resqship": "resqship",
    "emergency": "emergency",
    "emergencyong": "emergency",
    "iommissingmigrants": "iom_missing_migrants",
}


def resolve_source_identity(
    source_name: str,
    metadata: Mapping[str, Any] | None = None,
) -> SourceIdentityPolicy:
    identity_id = _ALIASES.get(_key(source_name))
    if identity_id is not None:
        return _POLICIES[identity_id]
    normalized = _key(source_name) or "unknown"
    return SourceIdentityPolicy(
        identity_id=normalized,
        service=None,
        source_role="unknown",
        may_open_incident=False,
        independence_group=normalized,
    )


def may_open_humanitarian_incident(event: Any) -> bool:
    from core.intel.service_taxonomy import classify_service

    classification = classify_service(event)
    if classification.service != "humanitarian":
        return False
    source_name = str(getattr(event, "source", "") or "")
    metadata = getattr(event, "metadata", None) or {}
    return resolve_source_identity(source_name, metadata).may_open_incident
