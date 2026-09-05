"""Conservative evidence lineage for OSINT fusion.

Different detectors over one sensor lineage are not independent corroboration.
Unknown lineage never counts as independent by default.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.intel.source_catalog import get_source_profile


@dataclass(frozen=True)
class EvidenceLineage:
    source_name: str
    source_family: str
    independence_group: str
    sensor_family: str


_AIS_INTERNAL_ALIASES = frozenset({
    "mda",
    "ais",
    "ais incidents",
    "aisstream",
})

_AIS_SOURCE_FAMILIES = frozenset({"ais", "ais_derived_event"})

def _sensor_family(profile: dict | None, source_name: str) -> str:
    if source_name.strip().lower() in _AIS_INTERNAL_ALIASES:
        return "ais"
    if profile is None:
        return "unknown"
    if profile.get("source_family") in _AIS_SOURCE_FAMILIES:
        return "ais"
    if profile.get("source_type") == "ais":
        return "ais"
    return "official_report" if profile.get("source_type") in {"api", "rss"} else str(
        profile.get("source_type") or "unknown"
    )


def lineage_for_event(event) -> EvidenceLineage:
    source_name = str(getattr(event, "source", "") or "").strip()
    profile = get_source_profile(source_name)
    sensor_family = _sensor_family(profile, source_name)
    if sensor_family == "ais":
        return EvidenceLineage(
            source_name=source_name,
            source_family=(profile or {}).get("source_family") or "ais",
            independence_group="ais_sensor_lineage",
            sensor_family="ais",
        )
    if profile is None:
        return EvidenceLineage(source_name, "unknown", "unknown", "unknown")
    return EvidenceLineage(
        source_name=source_name,
        source_family=str(profile.get("source_family") or "unknown"),
        independence_group=str(profile.get("independence_group") or "unknown"),
        sensor_family=sensor_family,
    )
