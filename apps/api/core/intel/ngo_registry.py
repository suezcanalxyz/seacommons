# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Known SAR NGO and coastguard vessel database.

MMSIs verified against MarineTraffic / VesselFinder / vesseltracker /
Wikipedia public data (2024-2026). Mark any vessel with MMSI in this dict
as a priority track.

Field semantics:
  name   — vessel name
  org    — operating organisation
  flag   — current flag state (ISO 3166-1 alpha-3)
  role   — SAR / SAR-support / coastguard / surveillance
  imo    — IMO number (where known)
  callsign — AIS callsign (where known)
  status — active | retired | unverified
"""
from __future__ import annotations

from typing import Any

# ── NGO SAR Fleet (verified 2026) ─────────────────────────────────────────────
NGO_VESSELS: dict[str, dict[str, Any]] = {
    # SOS Méditerranée
    "258479000": {"name": "Ocean Viking",  "org": "SOS Méditerranée",     "flag": "NOR", "role": "SAR",
                  "imo": "8506854", "callsign": "JXIW3", "status": "active"},
    # MSF — Geo Barents chartered 2021–2024, SAR ops halted Dec 2024 (Piantedosi decree)
    "258826000": {"name": "Geo Barents",   "org": "MSF",                  "flag": "NOR", "role": "SAR",
                  "imo": "9252503", "callsign": "LAKK6", "status": "retired"},
    # MSF — new vessel since Nov 2025 (replaces Geo Barents); ex-Norwegian ambulance boat.
    # VesselFinder still lists the ex-Norwegian MMSI 257326900 — monitor both.
    "211180740": {"name": "Oyvon",         "org": "MSF",                  "flag": "DEU", "role": "SAR",
                  "status": "active", "note": "ex-NOR MMSI 257326900"},
    "257326900": {"name": "Oyvon (ex-NOR)", "org": "MSF",                 "flag": "NOR", "role": "SAR",
                  "status": "unverified"},
    # Open Arms
    "224772000": {"name": "Open Arms",     "org": "Proactiva Open Arms",  "flag": "ESP", "role": "SAR",
                  "imo": "7325887", "callsign": "EGGX", "status": "active"},
    "235105994": {"name": "Astral",        "org": "Proactiva Open Arms",  "flag": "GBR", "role": "SAR-support",
                  "status": "unverified"},
    # Sea Watch
    "211879870": {"name": "Sea Watch 5",   "org": "Sea Watch",            "flag": "DEU", "role": "SAR",
                  "imo": "9421556", "callsign": "DCDR2", "status": "active"},
    "211883350": {"name": "Aurora",        "org": "Sea Watch",            "flag": "DEU", "role": "SAR",
                  "callsign": "DJVX2", "status": "active"},
    # Sea-Eye
    "218049720": {"name": "Sea-Eye 5",     "org": "Sea-Eye",              "flag": "DEU", "role": "SAR",
                  "callsign": "DIZS2", "status": "active"},
    "211428870": {"name": "Mediterranea",  "org": "Mediterranea Saving Humans", "flag": "DEU", "role": "SAR",
                  "imo": "7214753", "callsign": "DHUQ2", "status": "active", "note": "ex-Sea-Eye 4"},
    "247536000": {"name": "Mare Jonio",    "org": "Mediterranea Saving Humans", "flag": "ITA", "role": "SAR",
                  "imo": "7222669", "status": "active"},
    # Salvamento Marítimo Humanitario
    "224069840": {"name": "Aita Mari",     "org": "Salvamento Marítimo Humanitario", "flag": "ESP", "role": "SAR",
                  "imo": "9248851", "callsign": "EBXC", "status": "active"},
    # SOS Humanity (ex-Sea-Watch 4, same hull IMO 9704918)
    "257091000": {"name": "Humanity 1",    "org": "SOS Humanity",         "flag": "NOR", "role": "SAR",
                  "imo": "9704918", "status": "unverified"},
    # Louise Michel (Banksy-funded collective)
    "211322990": {"name": "Louise Michel", "org": "Louise Michel",        "flag": "DEU", "role": "SAR",
                  "callsign": "DCXD", "status": "active"},
    # EMERGENCY ONG
    "352001404": {"name": "Life Support",  "org": "EMERGENCY",            "flag": "PAN", "role": "SAR",
                  "imo": "9250206", "callsign": "HOA7461", "status": "active"},
    # ResQship (sailing monitoring vessel)
    "211472620": {"name": "Nadir",         "org": "ResQship",             "flag": "DEU", "role": "SAR-support",
                  "callsign": "DFQD2", "status": "active"},

    # ── Coastguards (major responders) ────────────────────────────────────────
    # Guardia Costiera (Italian Coast Guard) flagship vessels
    "247330700": {"name": "Diciotti",         "org": "Guardia Costiera ITA", "flag": "ITA", "role": "coastguard",
                  "imo": "9690420", "callsign": "IHEW", "status": "active"},
    "247330500": {"name": "Dattilo",          "org": "Guardia Costiera ITA", "flag": "ITA", "role": "coastguard",
                  "callsign": "IGUB", "status": "active"},
    "247329600": {"name": "Bruno Gregoretti", "org": "Guardia Costiera ITA", "flag": "ITA", "role": "coastguard",
                  "imo": "9655523", "callsign": "IGSD", "status": "active"},
    # Malta Armed Forces
    "249165000": {"name": "P61 Diciotti",     "org": "Armed Forces of Malta", "flag": "MLT", "role": "coastguard",
                  "imo": "4594920", "status": "unverified"},
}

# ── Vessels to monitor but with unconfirmed MMSI (kept out of NGO_VESSELS so
#    they never cause a false NGO tag). Tracked manually / via registry name. ──
UNCONFIRMED_MMSI: dict[str, dict[str, Any]] = {
    # Italian Navy Cassiopea-class OPVs (pennant P401–P404) — Mare Nostrum-era
    # migration patrol, no reliable public MMSI.
    "Cassiopea (P401)": {"org": "Marina Militare ITA", "role": "surveillance"},
    "Libra (P402)":     {"org": "Marina Militare ITA", "role": "surveillance"},
    "Spica (P403)":     {"org": "Marina Militare ITA", "role": "surveillance"},
    "Vega (P404)":      {"org": "Marina Militare ITA", "role": "surveillance"},
    # Frontex surveillance assets (chartered, rotating) — no fixed MMSI.
    "Derfflinger":      {"org": "Frontex",             "role": "surveillance"},
}

# Twitter handles for social monitoring (no @ prefix)
NGO_TWITTER_HANDLES = [
    "alarm_phone",       # Alarm Phone — public distress and SAR reports
    "MSF_Sea",           # MSF Sea Rescue
    "openarms_fund",     # Open Arms
    "sosmediterranee",   # SOS Méditerranée
    "seawatchcrew",      # Sea Watch crew reports
    "SOShumanity",       # SOS Humanity
    "SeaEye4",           # Sea-Eye
    "ResQship",          # ResQship
    "emergencyita",      # Emergency ONG
    "watchthemed",       # Watch The Med (civilian monitoring network)
    "InfoMigrants",      # InfoMigrants (multilingual news)
    "IOM_Italy",         # IOM Italy
    "UNHCR_Italia",      # UNHCR Italy
]

_MMSI_SET = set(NGO_VESSELS.keys())


def is_ngo(mmsi: str) -> bool:
    return str(mmsi) in _MMSI_SET


def get_ngo_info(mmsi: str) -> dict[str, Any] | None:
    return NGO_VESSELS.get(str(mmsi))


def ngo_mmsi_set() -> frozenset[str]:
    return frozenset(_MMSI_SET)
