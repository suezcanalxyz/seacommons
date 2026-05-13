# SPDX-License-Identifier: AGPL-3.0-or-later
"""
SAR zone classifier and legal framework analyser.

Given an origin point + optional drift trajectory, returns:
  - Which SAR/SRR zones are involved
  - Primary responsible MRCC
  - Applicable legal framework (SOLAS, UNCLOS, national law)
  - Survival time estimate
  - Risk level breakdown
"""
from __future__ import annotations

import math
from typing import Any, Optional

from shapely.geometry import LineString, Point, Polygon

# ── SAR / operational zone definitions ───────────────────────────────────────
# Mirrors the data in api/routes/zones.py but adds legal metadata.
SAR_ZONES: list[dict[str, Any]] = [
    {
        "id": "med_central_hotspot",
        "name": "Central Med SAR Hotspot",
        "zone_type": "hotspot",
        "description": "Primary migration route — highest SAR incident density",
        "polygon": [
            [11.0, 33.0], [16.5, 33.0], [16.5, 35.8],
            [14.5, 36.2], [12.5, 36.2], [11.0, 35.2], [11.0, 33.0],
        ],
        "mrcc": "MRCC Roma",
        "mrcc_tel": "+39 06 59 08 04",
        "mrcc_alt": "JRCC Malta",
        "mrcc_alt_tel": "+356 21 238797",
        "color": "#ef4444",
        "legal_notes": [
            "SOLAS Reg. V/33 — duty to render assistance to persons in distress applies to all vessels.",
            "UNCLOS Art. 98 — every State shall require masters of vessels flying its flag to render assistance.",
            "Jurisdictional overlap: Italy and Malta both claim SAR responsibility; coordination required.",
            "EU Regulation 656/2014 — Frontex operations in external sea borders apply.",
        ],
        "obligation_level": "critical",
    },
    {
        "id": "italy_srr_south",
        "name": "Italian SRR",
        "zone_type": "srr",
        "description": "MRCC Roma — Italian Search and Rescue Region, southern sector",
        "polygon": [
            [6.5, 37.5], [18.5, 37.5], [18.5, 35.0],
            [15.5, 33.0], [11.5, 33.0], [6.5, 35.5], [6.5, 37.5],
        ],
        "mrcc": "MRCC Roma",
        "mrcc_tel": "+39 06 59 08 04",
        "mrcc_alt": None,
        "mrcc_alt_tel": None,
        "color": "#3b82f6",
        "legal_notes": [
            "Italy holds primary SAR coordination responsibility under SOLAS V/7.",
            "UNCLOS Art. 98 + Maritime Code Art. 490 — obligation to assist is absolute.",
            "DL 130/2020 (Lamorgese Decree) — regulates NGO vessel entry to Italian ports.",
            "Rescue vessels must be assigned a Place of Safety (PoS) within reasonable time.",
        ],
        "obligation_level": "high",
    },
    {
        "id": "malta_srr",
        "name": "Maltese SRR",
        "zone_type": "srr",
        "description": "JRCC Malta — Malta Search and Rescue Region",
        "polygon": [
            [12.0, 36.5], [17.5, 36.5], [17.5, 32.5],
            [12.0, 32.5], [12.0, 36.5],
        ],
        "mrcc": "JRCC Malta",
        "mrcc_tel": "+356 21 238797",
        "mrcc_alt": "MRCC Roma",
        "mrcc_alt_tel": "+39 06 59 08 04",
        "color": "#f59e0b",
        "legal_notes": [
            "Malta holds SAR coordination responsibility under SOLAS V/7.",
            "IAMSAR Manual Vol. I — obligation to coordinate SAR operations within its SRR.",
            "Malta has been criticised for delayed SAR response (ECtHR cases pending).",
            "NGO vessels must notify JRCC Malta on distress frequency (156.8 MHz).",
        ],
        "obligation_level": "high",
    },
    {
        "id": "libyan_declared_zone",
        "name": "Libyan declared zone",
        "zone_type": "declared",
        "description": "Libya-declared maritime zone (2018) — disputed, overlaps Maltese and Italian SRR",
        "polygon": [
            [11.0, 33.5], [25.0, 33.5], [25.0, 29.5],
            [11.0, 29.5], [11.0, 33.5],
        ],
        "mrcc": "MRCC Tripoli (unreliable)",
        "mrcc_tel": "+218 91 3199330",
        "mrcc_alt": "MRCC Roma",
        "mrcc_alt_tel": "+39 06 59 08 04",
        "color": "#f97316",
        "legal_notes": [
            "Libya's declared SAR zone is NOT recognised under international law by major EU states.",
            "Libya is NOT a party to the 1951 Refugee Convention — Libyan ports are NOT safe places (PoS).",
            "UNHCR and IOM: disembarkation in Libya violates non-refoulement principle.",
            "SOLAS Reg. V/33 still applies — vessels must render assistance regardless of zone claim.",
            "Italian DL 130/2020 does NOT override SOLAS duty to assist in Libyan-declared zone.",
        ],
        "obligation_level": "critical",
        "warning": "Non-safe zone — return to Libya constitutes refoulement under international law.",
    },
    {
        "id": "tunisia_srr",
        "name": "Tunisian SRR",
        "zone_type": "srr",
        "description": "MRCC Tunis — Tunisia Search and Rescue Region",
        "polygon": [
            [8.0, 38.5], [12.5, 38.5], [12.5, 35.5],
            [8.0, 35.5], [8.0, 38.5],
        ],
        "mrcc": "MRCC Tunis",
        "mrcc_tel": "+216 71 735 004",
        "mrcc_alt": None,
        "mrcc_alt_tel": None,
        "color": "#22c55e",
        "legal_notes": [
            "Tunisia holds SAR coordination responsibility under SOLAS V/7.",
            "Tunisia is a party to the 1951 Refugee Convention.",
            "Bilateral Italy-Tunisia readmission agreement (1998) affects disembarkation decisions.",
        ],
        "obligation_level": "medium",
    },
    {
        "id": "high_seas",
        "name": "High Seas (international waters)",
        "zone_type": "high_seas",
        "description": "Beyond 12nm from any coast — flag state jurisdiction applies",
        "polygon": None,  # fallback — applied when no other zone matches
        "mrcc": "Nearest coastal MRCC",
        "mrcc_tel": "156.8 MHz (Ch.16 VHF)",
        "mrcc_alt": None,
        "mrcc_alt_tel": None,
        "color": "#64748b",
        "legal_notes": [
            "UNCLOS Art. 92 — vessel subject to exclusive flag state jurisdiction on high seas.",
            "UNCLOS Art. 98 — every State shall require masters to render assistance to persons in distress.",
            "SOLAS Reg. V/33 — absolute duty to render assistance; no exception.",
            "IAMSAR Manual — rescue coordination to be assumed by nearest coastal MRCC.",
        ],
        "obligation_level": "medium",
    },
]

# Pre-build Shapely polygons
_ZONE_SHAPES: list[tuple[dict, Polygon]] = []
for _z in SAR_ZONES:
    if _z["polygon"]:
        ring = _z["polygon"]
        if ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        try:
            _ZONE_SHAPES.append((_z, Polygon(ring)))
        except Exception:
            pass


# ── Survival time model ───────────────────────────────────────────────────────

_VESSEL_CAPSIZING_RISK: dict[str, float] = {
    "rubber_boat":    0.90,   # extreme
    "life_raft":      0.55,
    "wooden_boat":    0.40,
    "fishing_vessel": 0.25,
    "sailboat":       0.20,
    "motorboat":      0.30,
    "container_ship": 0.02,
    "unknown":        0.60,
}

_SEA_STATE_NAMES = {
    0: "Calm", 1: "Rippled", 2: "Wavelets", 3: "Slight",
    4: "Moderate", 5: "Rough", 6: "Very rough", 7: "High", 8: "Very high",
}


def _beaufort_from_ms(speed_ms: float) -> int:
    """Convert wind speed m/s → Beaufort scale."""
    thresholds = [0.3, 1.6, 3.4, 5.5, 8.0, 10.8, 13.9, 17.2, 20.8, 24.5, 28.5, 32.7]
    for i, t in enumerate(thresholds):
        if speed_ms < t:
            return i
    return 12


def estimate_survival_hours(
    vessel_type: str,
    persons: int,
    wave_height_m: float = 1.0,
    wind_speed_ms: float = 5.0,
    drift_hours: float = 24.0,
) -> dict[str, Any]:
    """
    Heuristic survival time estimate based on vessel type, sea state, occupancy.
    Not a certified medical or naval calculation — for situational awareness only.
    """
    beaufort = _beaufort_from_ms(wind_speed_ms)
    sea_state = _SEA_STATE_NAMES.get(beaufort, "Unknown")

    # Base survival window by vessel type (hours in open sea)
    base_hours = {
        "rubber_boat":    4.0,
        "life_raft":      12.0,
        "wooden_boat":    18.0,
        "fishing_vessel": 36.0,
        "sailboat":       48.0,
        "motorboat":      24.0,
        "container_ship": 200.0,
        "unknown":        6.0,
    }.get(vessel_type, 6.0)

    # Sea state penalty
    sea_factor = max(0.15, 1.0 - (beaufort * 0.08))

    # Overcrowding: >20 persons on rubber boat is critical
    overcrowd_factor = 1.0
    if vessel_type in ("rubber_boat", "life_raft") and persons > 30:
        overcrowd_factor = 0.5
    elif vessel_type in ("rubber_boat", "life_raft") and persons > 15:
        overcrowd_factor = 0.75

    survival_h = base_hours * sea_factor * overcrowd_factor
    capsizing_risk = _VESSEL_CAPSIZING_RISK.get(vessel_type, 0.5)

    # Risk level
    if survival_h < drift_hours * 0.5:
        risk_level = "critical"
        risk_label = "Survival window shorter than drift period — immediate rescue required"
    elif survival_h < drift_hours:
        risk_level = "high"
        risk_label = "Survival window within drift period — urgent response"
    elif beaufort >= 5:
        risk_level = "high"
        risk_label = "Rough conditions — deterioration expected"
    else:
        risk_level = "medium"
        risk_label = "Conditions survivable within projection window"

    return {
        "estimated_survival_hours": round(survival_h, 1),
        "beaufort": beaufort,
        "sea_state": sea_state,
        "wave_height_m": round(wave_height_m, 1),
        "capsizing_risk_pct": round(capsizing_risk * 100),
        "risk_level": risk_level,
        "risk_label": risk_label,
        "note": "Heuristic estimate — not a certified survival model.",
    }


# ── Zone classification ───────────────────────────────────────────────────────

def classify_point(lat: float, lon: float) -> list[dict[str, Any]]:
    """Return all SAR zones that contain the given point."""
    pt = Point(lon, lat)
    hits = []
    for zone, shape in _ZONE_SHAPES:
        if shape.contains(pt):
            hits.append(zone)
    if not hits:
        hits = [next(z for z in SAR_ZONES if z["id"] == "high_seas")]
    return hits


def classify_trajectory(coords: list[list[float]]) -> list[dict[str, Any]]:
    """Return all SAR zones intersected by the drift trajectory (list of [lon, lat])."""
    if len(coords) < 2:
        return classify_point(coords[0][1], coords[0][0]) if coords else []
    line = LineString(coords)
    hits = []
    seen = set()
    for zone, shape in _ZONE_SHAPES:
        if zone["id"] not in seen and shape.intersects(line):
            hits.append(zone)
            seen.add(zone["id"])
    if not hits:
        hits = [next(z for z in SAR_ZONES if z["id"] == "high_seas")]
    return hits


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3440.065  # Earth radius in nm
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def drift_analysis(
    lat: float,
    lon: float,
    trajectory_coords: Optional[list[list[float]]] = None,
    vessel_type: str = "rubber_boat",
    persons: int = 30,
    duration_h: float = 24.0,
    weather: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Full legal + operational analysis for a SAR drift result.
    Returns structured data ready for frontend display.
    """
    origin_zones = classify_point(lat, lon)
    traj_zones = classify_trajectory(trajectory_coords) if trajectory_coords else origin_zones

    # All unique zones touched
    all_zone_ids = {z["id"] for z in origin_zones} | {z["id"] for z in traj_zones}
    all_zones = {z["id"]: z for z in origin_zones + traj_zones}

    # Primary responsible MRCC = zone with highest obligation at origin
    priority_order = ["critical", "high", "medium", "low"]
    primary_zone = sorted(
        origin_zones,
        key=lambda z: priority_order.index(z.get("obligation_level", "medium"))
    )[0] if origin_zones else None

    # Collect all legal notes (deduplicated)
    seen_notes: set[str] = set()
    legal_notes: list[str] = []
    for zid in sorted(all_zone_ids):
        z = all_zones[zid]
        for note in z.get("legal_notes", []):
            if note not in seen_notes:
                legal_notes.append(note)
                seen_notes.add(note)

    # Collect MRCC contacts
    contacts: list[dict[str, str]] = []
    seen_mrcc: set[str] = set()
    for zid in sorted(all_zone_ids):
        z = all_zones[zid]
        if z["mrcc"] and z["mrcc"] not in seen_mrcc:
            contacts.append({"name": z["mrcc"], "tel": z["mrcc_tel"] or ""})
            seen_mrcc.add(z["mrcc"])
        if z.get("mrcc_alt") and z["mrcc_alt"] not in seen_mrcc:
            contacts.append({"name": z["mrcc_alt"], "tel": z.get("mrcc_alt_tel") or ""})
            seen_mrcc.add(z["mrcc_alt"])

    # Drift distance
    drift_nm: Optional[float] = None
    if trajectory_coords and len(trajectory_coords) >= 2:
        total = 0.0
        for i in range(len(trajectory_coords) - 1):
            a, b = trajectory_coords[i], trajectory_coords[i + 1]
            total += _haversine_nm(a[1], a[0], b[1], b[0])
        drift_nm = round(total, 1)

    # Survival estimate
    wave_h = weather.get("waves", {}).get("significant_height_m", 1.0) if weather else 1.0
    wind_ms = weather.get("wind", {}).get("speed_ms", 5.0) if weather else 5.0
    survival = estimate_survival_hours(
        vessel_type=vessel_type,
        persons=persons,
        wave_height_m=float(wave_h or 1.0),
        wind_speed_ms=float(wind_ms or 5.0),
        drift_hours=duration_h,
    )

    # Zone warning flags
    warnings: list[str] = []
    for z in all_zones.values():
        if z.get("warning"):
            warnings.append(z["warning"])
    if survival["risk_level"] == "critical":
        warnings.insert(0, survival["risk_label"])

    return {
        "origin": {"lat": lat, "lon": lon},
        "origin_zones": [_zone_summary(z) for z in origin_zones],
        "trajectory_zones": [_zone_summary(z) for z in traj_zones],
        "primary_mrcc": {
            "name": primary_zone["mrcc"] if primary_zone else "Unknown",
            "tel": primary_zone["mrcc_tel"] if primary_zone else "",
            "zone": primary_zone["name"] if primary_zone else "",
        },
        "all_contacts": contacts,
        "legal_notes": legal_notes,
        "survival": survival,
        "drift_nm": drift_nm,
        "duration_h": duration_h,
        "warnings": warnings,
    }


def _zone_summary(z: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": z["id"],
        "name": z["name"],
        "zone_type": z["zone_type"],
        "mrcc": z["mrcc"],
        "mrcc_tel": z.get("mrcc_tel", ""),
        "obligation_level": z.get("obligation_level", "medium"),
        "color": z.get("color", "#64748b"),
        "warning": z.get("warning"),
    }
