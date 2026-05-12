# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Known SAR NGO and coastguard vessel database.

MMSIs verified against MarineTraffic public data (2024-2025).
Mark any vessel with MMSI in this dict as a priority track.
"""
from __future__ import annotations
from typing import Any

# ── NGO SAR Fleet ─────────────────────────────────────────────────────────────
NGO_VESSELS: dict[str, dict[str, Any]] = {
    # SOS Méditerranée
    "247430700": {"name": "Ocean Viking",      "org": "SOS Méditerranée",         "flag": "NOR", "role": "SAR"},
    # MSF / SOS Méditerranée shared vessel
    "247383300": {"name": "Geo Barents",       "org": "MSF / SOS Méditerranée",   "flag": "NOR", "role": "SAR"},
    # Open Arms
    "224228880": {"name": "Open Arms",         "org": "Proactiva Open Arms",      "flag": "ESP", "role": "SAR"},
    "224230540": {"name": "Astral",            "org": "Proactiva Open Arms",      "flag": "ESP", "role": "SAR-support"},
    # Sea Watch
    "229962000": {"name": "Sea Watch 3",       "org": "Sea Watch",                "flag": "DEU", "role": "SAR"},
    "248220000": {"name": "Sea Watch 4",       "org": "Sea Watch / United4Rescue","flag": "MLT", "role": "SAR"},
    # SOS Humanity
    "257091000": {"name": "Humanity 1",        "org": "SOS Humanity",             "flag": "NOR", "role": "SAR"},
    # Sea-Eye
    "211267420": {"name": "Nadir",             "org": "Sea-Eye",                  "flag": "DEU", "role": "SAR"},
    "211185810": {"name": "Aurora",            "org": "Sea-Eye",                  "flag": "DEU", "role": "SAR"},
    # Louise Michel
    "538009597": {"name": "Louise Michel",     "org": "Banksy / LM Foundation",   "flag": "BHS", "role": "SAR"},
    # Emergency ONG
    "247432800": {"name": "Life Support",      "org": "Emergency ONG",            "flag": "ITA", "role": "SAR"},
    # ResQship
    "211812890": {"name": "Minden",            "org": "ResQship",                 "flag": "DEU", "role": "SAR"},
    # Médecins du Monde
    "319085700": {"name": "Aquarius",          "org": "Médecins du Monde",        "flag": "GIB", "role": "SAR"},

    # ── Coastguards (major responders) ────────────────────────────────────────
    # Guardia Costiera (Italian Coast Guard) flagship vessels
    "247320000": {"name": "Diciotti",          "org": "Guardia Costiera ITA",     "flag": "ITA", "role": "coastguard"},
    "247242000": {"name": "Dattilo",           "org": "Guardia Costiera ITA",     "flag": "ITA", "role": "coastguard"},
    "247272600": {"name": "Bruno Gregoretti",  "org": "Guardia Costiera ITA",     "flag": "ITA", "role": "coastguard"},
    # Malta Armed Forces
    "249165000": {"name": "P61 Diciotti",      "org": "Armed Forces of Malta",    "flag": "MLT", "role": "coastguard"},
    # Frontex (EU Border Agency vessels — chartered)
    "538005179": {"name": "Triton",            "org": "Frontex",                  "flag": "MLT", "role": "surveillance"},
}

# Twitter handles for social monitoring (no @ prefix)
NGO_TWITTER_HANDLES = [
    "alarm__phone",      # Alarm Phone — posts distress calls with GPS coords
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

# RSS/web feeds for maritime news
NEWS_FEEDS = [
    # Alarm Phone calls archive (HTML scrape)
    {"url": "https://alarmphone.org/en/calls/",       "type": "html",    "label": "Alarm Phone"},
    # IOM Missing Migrants (public JSON API)
    {"url": "https://missingmigrants.iom.int/api/incidents?route=Mediterranean&status=Verified&page=1",
                                                       "type": "iom_api", "label": "IOM Missing Migrants"},
    # ReliefWeb Mediterranean emergency feeds
    {"url": "https://reliefweb.int/updates/rss.xml",  "type": "rss",     "label": "ReliefWeb"},
    # UNHCR news
    {"url": "https://www.unhcr.org/rss/news.rss",     "type": "rss",     "label": "UNHCR"},
    # InfoMigrants RSS
    {"url": "https://www.infomigrants.net/en/rss",    "type": "rss",     "label": "InfoMigrants"},
    # MarineTraffic news
    {"url": "https://www.marinetraffic.com/blog/feed/","type": "rss",     "label": "MarineTraffic"},
]

_MMSI_SET = set(NGO_VESSELS.keys())


def is_ngo(mmsi: str) -> bool:
    return str(mmsi) in _MMSI_SET


def get_ngo_info(mmsi: str) -> dict[str, Any] | None:
    return NGO_VESSELS.get(str(mmsi))


def ngo_mmsi_set() -> frozenset[str]:
    return frozenset(_MMSI_SET)
