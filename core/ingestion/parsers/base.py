# SPDX-License-Identifier: AGPL-3.0-or-later
"""Abstract base parser + shared CoordinateExtractor."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Tuple

from core.ingestion.signal import DistressSignal


class CoordinateExtractor:
    """
    Multi-strategy coordinate extractor.
    Handles Italian, English, Arabic, French, Greek, Amharic.
    Returns (lat, lon, confidence, method).
    """

    # 1. Shared location links
    _RE_GMAPS_Q   = re.compile(r'maps\.google\.com/\?q=(-?\d+\.?\d*),(-?\d+\.?\d*)')
    _RE_GMAPS_LL  = re.compile(r'maps\.google\.com/.*[?&]ll=(-?\d+\.?\d*),(-?\d+\.?\d*)')
    _RE_GOOG_MAPS = re.compile(r'google\.com/maps\?.*ll=(-?\d+\.?\d*),(-?\d+\.?\d*)')
    _RE_GMAPS_AT  = re.compile(r'@(-?\d+\.?\d*),(-?\d+\.?\d*)')

    # 2. Decimal degrees explicit
    _RE_DEC_NS = re.compile(
        r'(-?\d{1,3}\.?\d*)\s*[°]?\s*([NS])\s+(-?\d{1,3}\.?\d*)\s*[°]?\s*([EW])',
        re.IGNORECASE
    )
    _RE_DEC_PLAIN = re.compile(
        r'(?:lat[:\s]*)?(-?\d{1,3}\.\d{3,})[,\s]+(?:lon[:\s]*)?(-?\d{1,3}\.\d{3,})'
    )
    _RE_DEC_LABELED = re.compile(
        r'lat[itude]*\s*[:=]\s*(-?\d{1,3}\.?\d*)\s+lon[gitude]*\s*[:=]\s*(-?\d{1,3}\.?\d*)',
        re.IGNORECASE
    )

    # 3. Degrees minutes
    _RE_DM = re.compile(
        r'(\d{1,3})[°\s]\s*(\d{1,2})[\'′\s]\s*([NS])\s+'
        r'(\d{1,3})[°\s]\s*(\d{1,2})[\'′\s]\s*([EW])',
        re.IGNORECASE
    )

    # 4. Alarm Phone structured format
    _RE_ALARM_POS = re.compile(r'[Pp]osition\s*[:=]\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)')

    # Vessel type keywords (multi-language)
    _VESSEL_RUBBER = re.compile(
        r'gommone|rubber\s*boat|zodiac|schlauchboot|canot\s*pneumatique|قارب\s*مطاطي|λαστιχένια',
        re.IGNORECASE)
    _VESSEL_WOODEN = re.compile(
        r'barca\s*legno|wooden\s*boat|barque\s*en\s*bois|قارب\s*خشبي', re.IGNORECASE)
    _VESSEL_SAIL   = re.compile(r'barca\s*a\s*vela|sailboat|voilier|شراعية', re.IGNORECASE)

    # Condition keywords
    _COND_SINKING = re.compile(
        r'affonda|sinking|يغرق|coule|βυθίζ|ist\s*am\s*sinken', re.IGNORECASE)
    _COND_WATER   = re.compile(
        r'acqua\s*dentro|taking\s*water|ماء\s*بالداخل|prend\s*l\'eau|παίρνει\s*νερά',
        re.IGNORECASE)
    _COND_ENGINE  = re.compile(
        r'motore\s*rotto|engine\s*(broken|failure|dead)|المحرك\s*معطل|moteur\s*en\s*panne',
        re.IGNORECASE)

    # Medical / children
    _MEDICAL = re.compile(
        r'medico|medical|حاجة\s*طبية|médical|urgenza|emergency|blessé|جريح', re.IGNORECASE)
    _CHILDREN = re.compile(
        r'bambini|children|أطفال|enfants|kinder|παιδιά', re.IGNORECASE)

    # Person count — Arabic-Indic numerals handled below
    _RE_PERSONS = re.compile(
        r'(?:about|more\s+than|at\s+least|circa|oltre|più\s+di|أكثر\s+من|environ)?\s*'
        r'([\d٠-٩]+)\s*'
        r'(?:persons?|people|persone|شخص|أشخاص|personnes?|Personen)',
        re.IGNORECASE
    )

    @staticmethod
    def _arabic_to_int(s: str) -> int:
        """Convert Arabic-Indic digits (٠١٢٣٤٥٦٧٨٩) to int."""
        table = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
        return int(s.translate(table))

    def extract_coords(self, text: str) -> Tuple[Optional[float], Optional[float], float, str]:
        """Return (lat, lon, confidence, method). lat/lon None if not found."""

        # 1. Google Maps shared location
        for pat in [self._RE_GMAPS_Q, self._RE_GMAPS_LL, self._RE_GOOG_MAPS, self._RE_GMAPS_AT]:
            m = pat.search(text)
            if m:
                lat, lon = float(m.group(1)), float(m.group(2))
                if self._valid(lat, lon):
                    return lat, lon, 0.98, "shared_location"

        # 4. Alarm Phone position format (before generic decimal)
        m = self._RE_ALARM_POS.search(text)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if self._valid(lat, lon):
                return lat, lon, 0.92, "alarm_phone_format"

        # 2a. Labeled decimal
        m = self._RE_DEC_LABELED.search(text)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if self._valid(lat, lon):
                return lat, lon, 0.95, "decimal_labeled"

        # 2b. N/S E/W explicit
        m = self._RE_DEC_NS.search(text)
        if m:
            lat = float(m.group(1)) * (-1 if m.group(2).upper() == 'S' else 1)
            lon = float(m.group(3)) * (-1 if m.group(4).upper() == 'W' else 1)
            if self._valid(lat, lon):
                return lat, lon, 0.95, "decimal_explicit"

        # 2c. Plain decimal pair (must have ≥3 decimal digits to avoid false positives)
        m = self._RE_DEC_PLAIN.search(text)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
            if self._valid(lat, lon):
                return lat, lon, 0.95, "decimal_plain"

        # 3. Degrees minutes
        m = self._RE_DM.search(text)
        if m:
            lat = int(m.group(1)) + int(m.group(2)) / 60.0
            if m.group(3).upper() == 'S':
                lat = -lat
            lon = int(m.group(4)) + int(m.group(5)) / 60.0
            if m.group(6).upper() == 'W':
                lon = -lon
            if self._valid(lat, lon):
                return lat, lon, 0.90, "degrees_minutes"

        # 5. Natural language heuristics (low confidence)
        conf, lat, lon = self._natural_language(text)
        if lat is not None:
            return lat, lon, conf, "natural_language"

        return None, None, 0.0, "none"

    def extract_persons(self, text: str) -> Optional[int]:
        m = self._RE_PERSONS.search(text)
        if m:
            raw = m.group(1)
            try:
                return self._arabic_to_int(raw)
            except Exception:
                return None
        # Fallback: any number followed by 'pers' or 'people' etc.
        m2 = re.search(r'([\d٠-٩]+)\s+(?:persons?|people|persone|شخص)', text, re.IGNORECASE)
        if m2:
            try:
                return self._arabic_to_int(m2.group(1))
            except Exception:
                pass
        return None

    def extract_vessel_type(self, text: str) -> Optional[str]:
        if self._VESSEL_RUBBER.search(text):
            return "rubber_boat"
        if self._VESSEL_WOODEN.search(text):
            return "wooden_boat"
        if self._VESSEL_SAIL.search(text):
            return "sailboat"
        return None

    def extract_vessel_condition(self, text: str) -> Optional[str]:
        if self._COND_SINKING.search(text):
            return "sinking"
        if self._COND_WATER.search(text):
            return "taking_water"
        if self._COND_ENGINE.search(text):
            return "engine_failure"
        return None

    def extract_medical(self, text: str) -> bool:
        return bool(self._MEDICAL.search(text))

    def extract_children(self, text: str) -> bool:
        return bool(self._CHILDREN.search(text))

    def detect_language(self, text: str) -> Optional[str]:
        try:
            from langdetect import detect
            return detect(text)
        except Exception:
            return None

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _valid(lat: float, lon: float) -> bool:
        return -90 <= lat <= 90 and -180 <= lon <= 180

    _NL_REFS = {
        # landmark → (lat, lon)
        'lampedusa':      (35.507, 12.611),
        'malta':          (35.899, 14.514),
        'sicily':         (37.6, 14.0),
        'sicilia':        (37.6, 14.0),
        'tunisia':        (34.0, 9.0),
        'libya':          (25.0, 17.0),
        'libia':          (25.0, 17.0),
        'tripoli':        (32.9, 13.2),
        'benghazi':       (32.1, 20.07),
        'crete':          (35.2, 24.9),
        'creta':          (35.2, 24.9),
        'greece':         (39.0, 22.0),
        'grecia':         (39.0, 22.0),
        'lesvos':         (39.2, 26.3),
        'lesbos':         (39.2, 26.3),
        'turkey':         (39.0, 35.0),
        'turchia':        (39.0, 35.0),
    }

    def _natural_language(self, text: str) -> Tuple[float, Optional[float], Optional[float]]:
        text_lower = text.lower()
        for landmark, (lat, lon) in self._NL_REFS.items():
            if landmark in text_lower:
                # Try to extract distance/bearing
                dist_m = re.search(
                    r'(\d+)\s*(?:miglia|miles?|nm|nautical)', text_lower)
                bearing_m = re.search(
                    r'(?:verso|toward|direction)?\s*(nord|north|sud|south|est|east|ovest|west)',
                    text_lower)
                if dist_m:
                    dist = int(dist_m.group(1)) * 1.852 / 111.32  # nm → degrees approx
                    bearing = 0.0
                    if bearing_m:
                        b = bearing_m.group(1)
                        if b in ('nord', 'north'): bearing = 0
                        elif b in ('est', 'east'): bearing = 90
                        elif b in ('sud', 'south'): bearing = 180
                        elif b in ('ovest', 'west'): bearing = 270
                    import math
                    dlat = dist * math.cos(math.radians(bearing))
                    dlon = dist * math.sin(math.radians(bearing)) / math.cos(math.radians(lat))
                    return 0.60, lat + dlat, lon + dlon
                return 0.55, lat, lon
        return 0.0, None, None


class BaseParser(ABC):
    """All channel parsers inherit from this."""

    _extractor = CoordinateExtractor()

    @abstractmethod
    def can_parse(self, raw: str) -> bool:
        """Return True if this parser can handle the input."""

    @abstractmethod
    def parse(
        self, raw: str, source_channel: str,
        source_id: str, received_at: datetime,
    ) -> DistressSignal:
        """Extract a DistressSignal from raw text."""
