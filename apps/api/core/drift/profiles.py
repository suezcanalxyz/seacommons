# SPDX-License-Identifier: AGPL-3.0-or-later
"""Drift profiles: which OpenDrift model and parameters to use per object class.

Phase 15a. Replaces the flat vessel_type -> Leeway object_type map: a
drifting cargo ship does not move like a person in the water, so it must not
be simulated with person-in-water leeway coefficients.

A profile is resolved from, in order of preference:
  1. an explicit vessel_type string (operator or connector supplied)
  2. the case_type, when a case drives the drift
  3. a conservative SAR default (rubber boat)

Only "leeway" and "oceandrift" are dispatched in 15a. Oil (OpenOil) is
Phase 15b.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DriftProfile:
    object_class: str
    model: str  # "leeway" | "oceandrift"
    description: str
    # Leeway: OpenDrift object_type integer (see core/drift/models.py notes)
    leeway_object_type: int | None = None
    # OceanDrift: element wind_drift_factor and the config drift:wind_drift_depth
    wind_drift_factor: float | None = None
    wind_drift_depth: float | None = None
    # Debris field: a mix of Leeway object types, each with a particle
    # fraction. Used for shipwrecks -- survivors, rafts and debris drift
    # differently, so a single object type understates the search area.
    debris_mix: tuple[tuple[int, float], ...] | None = None


# Leeway categories keep the existing OpenDrift object_type integers.
_LEEWAY = "leeway"
_OCEAN = "oceandrift"

PROFILES: dict[str, DriftProfile] = {
    "person_in_water": DriftProfile(
        "person_in_water", _LEEWAY, "Person in water", leeway_object_type=26,
    ),
    "life_raft": DriftProfile(
        "life_raft", _LEEWAY, "Canopied life raft, 1-4 persons", leeway_object_type=27,
    ),
    "life_raft_large": DriftProfile(
        "life_raft_large", _LEEWAY, "Canopied life raft, 5+ persons", leeway_object_type=29,
    ),
    "rubber_boat": DriftProfile(
        "rubber_boat", _LEEWAY, "Inflatable boat without canopy", leeway_object_type=38,
    ),
    "small_wooden_boat": DriftProfile(
        "small_wooden_boat", _LEEWAY, "Small wooden or fibreglass boat", leeway_object_type=46,
    ),
    "fishing_vessel": DriftProfile(
        "fishing_vessel", _LEEWAY, "Small fishing vessel", leeway_object_type=52,
    ),
    # Powered / large hulls: current-dominated, low windage, deeper draft.
    "sailboat": DriftProfile(
        "sailboat", _OCEAN, "Sailboat adrift (rig increases windage)",
        wind_drift_factor=0.04, wind_drift_depth=0.5,
    ),
    "motorboat": DriftProfile(
        "motorboat", _OCEAN, "Powered pleasure/work boat adrift",
        wind_drift_factor=0.03, wind_drift_depth=0.6,
    ),
    "general_cargo": DriftProfile(
        "general_cargo", _OCEAN, "General cargo vessel adrift",
        wind_drift_factor=0.02, wind_drift_depth=1.5,
    ),
    "cargo_container_ship": DriftProfile(
        "cargo_container_ship", _OCEAN, "Container ship adrift",
        wind_drift_factor=0.015, wind_drift_depth=2.0,
    ),
    "tanker": DriftProfile(
        "tanker", _OCEAN, "Tanker adrift (deep draft, minimal windage)",
        wind_drift_factor=0.01, wind_drift_depth=3.0,
    ),
    "lost_container": DriftProfile(
        "lost_container", _OCEAN, "Shipping container lost at sea (floats low)",
        wind_drift_factor=0.03, wind_drift_depth=0.3,
    ),
    "shipwreck_debris_field": DriftProfile(
        "shipwreck_debris_field", _LEEWAY,
        "Shipwreck: persons in water, life rafts and wooden debris",
        leeway_object_type=26,  # fallback if the mix is dropped downstream
        debris_mix=(
            (26, 0.45),  # person in water
            (27, 0.30),  # life raft
            (46, 0.25),  # wooden / fibreglass fragments
        ),
    ),
}

DEFAULT_PROFILE = PROFILES["rubber_boat"]

# vessel_type strings (frontend + connectors) -> object_class
_VESSEL_TYPE_TO_CLASS: dict[str, str] = {
    "person_in_water": "person_in_water",
    "piw": "person_in_water",
    "rubber_boat": "rubber_boat",
    "life_raft": "life_raft",
    "fishing_vessel": "fishing_vessel",
    "wooden_boat": "small_wooden_boat",
    "small_wooden_boat": "small_wooden_boat",
    "sailboat": "sailboat",
    "motorboat": "motorboat",
    "container_ship": "cargo_container_ship",
    "cargo_container": "cargo_container_ship",
    "cargo": "general_cargo",
    "general_cargo": "general_cargo",
    "tanker": "tanker",
    "lost_container": "lost_container",
    "container": "lost_container",
}

# case_type (see core/api/routes/cases.py CASE_TYPES) -> default object_class
_CASE_TYPE_TO_CLASS: dict[str, str] = {
    "distress_sar": "rubber_boat",
    "pushback": "rubber_boat",
    "interception": "rubber_boat",
    "missing_persons": "person_in_water",
    "shipwreck": "shipwreck_debris_field",
    "vessel_incident": "general_cargo",
    "monitoring": "rubber_boat",
    "unspecified": "rubber_boat",
    # Broader maritime-domain compartments. Most are monitoring-only (no auto
    # drift); a dark ship-to-ship rendezvous is treated as a tanker for spill
    # contingency drift.
    "sanctions_watch": "rubber_boat",
    "dark_rendezvous": "tanker",
    "subsea_infrastructure": "rubber_boat",
    "piracy_incident": "rubber_boat",
}


def resolve_profile(
    *,
    vessel_type: str | None = None,
    case_type: str | None = None,
    persons: int = 1,
) -> DriftProfile:
    """Pick the drift profile for an object. vessel_type wins over case_type."""
    key = (vessel_type or "").strip().lower()
    object_class = _VESSEL_TYPE_TO_CLASS.get(key)

    if object_class is None and case_type:
        object_class = _CASE_TYPE_TO_CLASS.get(case_type.strip().lower())

    if object_class is None:
        return DEFAULT_PROFILE

    # life raft capacity split, mirroring core/drift/models.resolve_object_type
    if object_class == "life_raft" and persons > 4:
        object_class = "life_raft_large"

    return PROFILES.get(object_class, DEFAULT_PROFILE)
