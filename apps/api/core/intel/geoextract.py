# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Extract geographic coordinates and classify severity from free-text.

Strategy (in order):
  1. Explicit decimal coords  ("35.5N 12.3E", "35.5, 12.3")
  2. Degrees-minutes          ("35°30'N 12°15'E")
  3. Known Mediterranean place names (longest-match first)
  4. None — caller decides whether to discard or use a default zone
"""
from __future__ import annotations
import re
from typing import Optional

# ── Mediterranean gazetteer ───────────────────────────────────────────────────
# (lat, lon) centroids of places frequently mentioned in SAR/migration reports.
# Sorted by specificity (more-specific entries shadow generic ones in matching).
_PLACES: dict[str, tuple[float, float]] = {
    # Departure points (Libya/Tunisia)
    "zuwara":              (32.92, 12.08),
    "zuwarah":             (32.92, 12.08),
    "sabrata":             (32.79, 12.48),
    "misrata":             (32.37, 15.09),
    "khums":               (32.64, 14.26),
    "tripoli":             (32.90, 13.18),
    "benghazi":            (32.12, 20.07),
    "derna":               (32.75, 22.65),
    "sfax":                (34.74, 10.76),
    "sousse":              (35.83, 10.64),
    "kairouan":            (35.68, 10.10),
    "zarzis":              (33.50, 11.11),
    "gabes":               (33.88, 10.10),
    "jerba":               (33.80, 10.85),
    "medenine":            (33.35, 10.50),
    "ben gardane":         (33.14, 11.22),
    "thyna":               (34.71, 10.72),
    # Italian arrival points
    "lampedusa":           (35.50, 12.60),
    "linosa":              (35.87, 12.86),
    "pantelleria":         (36.83, 11.96),
    "porto empedocle":     (37.29, 13.53),
    "agrigento":           (37.31, 13.58),
    "pozzallo":            (36.73, 14.85),
    "augusta":             (37.23, 15.22),
    "catania":             (37.50, 15.09),
    "palermo":             (38.12, 13.35),
    "trapani":             (38.02, 12.51),
    "mazara del vallo":    (37.66, 12.59),
    "marsala":             (37.80, 12.44),
    "messina":             (38.19, 15.56),
    "reggio calabria":     (38.11, 15.65),
    "calabria":            (38.11, 16.55),
    "croton":              (39.08, 17.13),
    "crotone":             (39.08, 17.13),
    "taranto":             (40.46, 17.25),
    "bari":                (41.12, 16.87),
    "brindisi":            (40.63, 17.95),
    "lecce":               (40.35, 18.17),
    "ancona":              (43.61, 13.50),
    # Malta
    "malta":               (35.90, 14.51),
    "valletta":            (35.90, 14.51),
    "sliema":              (35.91, 14.50),
    # Greece (Aegean route)
    "lesvos":              (39.10, 26.55),
    "mytilene":            (39.10, 26.55),
    "chios":               (38.37, 26.14),
    "samos":               (37.75, 26.97),
    "kos":                 (36.89, 27.29),
    "rhodes":              (36.43, 28.22),
    "dodecanese":          (36.50, 28.00),
    "piraeus":             (37.94, 23.65),
    "athens":              (37.98, 23.73),
    # Turkey (departure Aegean)
    "izmir":               (38.42, 27.14),
    "cesme":               (38.33, 26.30),
    "bodrum":              (37.03, 27.43),
    "marmaris":            (36.85, 28.26),
    "canakkale":           (40.15, 26.41),
    "dikili":              (39.07, 26.89),
    "kusadasi":            (37.86, 27.26),
    # Sea zones
    "strait of sicily":    (37.00, 11.50),
    "sicilian channel":    (37.00, 11.50),
    "sicily channel":      (37.00, 11.50),
    "canal de sicile":     (37.00, 11.50),
    "canal de sicilia":    (37.00, 11.50),
    "central mediterranean": (35.00, 15.00),
    "central med":         (35.00, 15.00),
    "sicily":              (37.60, 14.01),
    "sardinia":            (40.10, 9.10),
    "aegean sea":          (37.50, 25.00),
    "aegean":              (37.50, 25.00),
    "ionian sea":          (38.00, 20.00),
    "ionian":              (38.00, 20.00),
    "tyrrhenian":          (40.00, 12.00),
    "adriatic":            (42.00, 15.00),
    "libyan waters":       (32.00, 15.00),
    "libyan coast":        (32.00, 15.00),
    "tunisian waters":     (37.00, 10.00),
    "tunisian coast":      (37.00, 10.00),
    "libya":               (27.00, 17.00),
    "tunisia":             (33.89, 9.53),
    "mediterranean":       (35.00, 18.00),
    "med sea":             (35.00, 18.00),
    # Red Sea / Horn (wider coverage for non-Med SAR)
    "suez":                (30.00, 32.54),
    "suez canal":          (30.70, 32.34),
    "red sea":             (20.00, 38.00),
    "gulf of aden":        (12.00, 47.00),
    "horn of africa":      (11.00, 51.00),
    "somalia":             (5.00, 46.00),
    "djibouti":            (11.82, 42.59),
    "aden":                (12.78, 45.03),
}

# Sorted longest-first for greedy matching
_PLACES_SORTED = sorted(_PLACES.items(), key=lambda x: -len(x[0]))

# ── Distress & emergency keyword sets ────────────────────────────────────────
DISTRESS_KW = frozenset([
    # English
    "mayday", "sos", "distress", "sinking", "capsized", "capsize",
    "overloaded", "taking water", "engine failure", "boat missing",
    "people drowning", "drowning", "rescue operation", "shipwreck",
    "overcrowded boat", "rubber boat sinking", "missing migrants",
    # Italian
    "naufragio", "affondamento", "dispersi", "soccorso in mare",
    "barcone", "barconi", "imbarcazione in difficoltà", "affogati",
    # French
    "naufrage", "détresse maritime", "embarcation en difficulté",
    # Arabic (transliterated common forms in Latin-script tweets)
    "gharaq", "gharak", "markab yughraq",
    # Generic SAR
    "man overboard", "mob alert", "epirb", "121.5", "406 mhz",
    "pyrotechnic", "flare sighted", "life raft", "lifeboat",
])

RESCUE_KW = frozenset([
    "rescue", "rescued", "rescuing", "soccorso", "salvato", "salvati",
    "recovered", "safely aboard", "brought on board", "onboard safe",
    "picked up", "intercepted", "towed to safety",
])

INFO_KW = frozenset([
    "spotted", "detected", "reported", "vessel sighted", "boat sighted",
    "monitoring", "in contact", "following", "tracking",
])

_CRITICAL_TERMS = frozenset([
    "mayday", "sinking", "capsized", "drowning", "dispersi",
    "غرق", "naufragio", "man overboard", "life raft",
])
_HIGH_TERMS = frozenset([
    "distress", "sos", "rescue operation", "soccorso", "naufrage",
    "overloaded", "engine failure", "missing migrants",
])
_MEDIUM_TERMS = frozenset([
    "spotted", "rubber boat", "zodiac", "dinghy", "barcone",
    "contact lost", "missing", "irregolari", "migranti",
])

# ── Regex patterns ────────────────────────────────────────────────────────────
_RE_DECIMAL_NS = re.compile(
    r"(\d{1,2}(?:\.\d{1,5})?)\s*°?\s*[Nn][,\s/]+(\d{1,3}(?:\.\d{1,5})?)\s*°?\s*[Ee]"
)
_RE_DECIMAL_PAIR = re.compile(
    r"(?<!\d)([+-]?(?:3[0-9]|4[0-4])\.\d{2,5})[,\s/]+([+-]?(?:[0-3]?\d|1[0-7]\d)\.\d{2,5})(?!\d)"
)
_RE_DMS = re.compile(
    r"(\d{1,2})[°º](\d{1,2})['’]?\s*[Nn][,\s]+(\d{1,3})[°º](\d{1,2})['’]?\s*[Ee]"
)
_RE_POSITION_LABEL = re.compile(
    r"(?:position|pos|coord|gps|location)[:\s]+([^\n]{5,60})", re.I
)


def extract_coords(text: str) -> Optional[tuple[float, float]]:
    """
    Return (lat, lon) from text, or None.
    Tries multiple strategies in order of precision.
    """
    # 0. Look for "Position: ..." prefix first — common in Alarm Phone tweets
    m = _RE_POSITION_LABEL.search(text)
    snippet = m.group(1) if m else text

    # 1. Decimal with N/E suffix  e.g. "35.5N 12.3E"
    m = _RE_DECIMAL_NS.search(snippet) or _RE_DECIMAL_NS.search(text)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if _valid(lat, lon):
            return lat, lon

    # 2. Decimal pair  e.g. "35.52, 12.30" (restricted to Mediterranean range)
    m = _RE_DECIMAL_PAIR.search(snippet) or _RE_DECIMAL_PAIR.search(text)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if _valid(lat, lon):
            return lat, lon

    # 3. DMS  e.g. "35°30'N 12°15'E"
    m = _RE_DMS.search(text)
    if m:
        lat = int(m.group(1)) + int(m.group(2)) / 60.0
        lon = int(m.group(3)) + int(m.group(4)) / 60.0
        if _valid(lat, lon):
            return lat, lon

    # 4. Place name gazetteer (longest match first)
    tl = text.lower()
    for place, coords in _PLACES_SORTED:
        if place in tl:
            return coords

    return None


def _valid(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180


def is_distress(text: str) -> bool:
    """True if text contains any distress keyword."""
    tl = text.lower()
    return any(kw in tl for kw in DISTRESS_KW)


def is_rescue(text: str) -> bool:
    tl = text.lower()
    return any(kw in tl for kw in RESCUE_KW)


def classify_severity(text: str) -> str:
    """Return 'critical' | 'high' | 'medium' | 'low'."""
    tl = text.lower()
    if any(kw in tl for kw in _CRITICAL_TERMS):
        return "critical"
    if any(kw in tl for kw in _HIGH_TERMS):
        return "high"
    if any(kw in tl for kw in _MEDIUM_TERMS):
        return "medium"
    return "low"
