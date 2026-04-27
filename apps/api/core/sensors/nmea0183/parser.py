from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable, Optional

from core.domain.events import NormalizedEvent, SourceRef
from core.integrations.base import IntegrationAdapter


def _parse_lat_lon(value: str, hemisphere: str) -> Optional[float]:
    if not value or not hemisphere:
        return None

    split_at = 2 if hemisphere in {"N", "S"} else 3
    degrees = float(value[:split_at])
    minutes = float(value[split_at:])
    decimal = degrees + minutes / 60.0
    if hemisphere in {"S", "W"}:
        decimal *= -1
    return decimal


def _parse_hms(raw: str) -> Optional[datetime]:
    if not raw or len(raw) < 6:
        return None

    hours = int(raw[0:2])
    minutes = int(raw[2:4])
    seconds = int(float(raw[4:]))
    today = date.today()
    return datetime(today.year, today.month, today.day, hours, minutes, seconds, tzinfo=timezone.utc)


class NMEA0183Adapter(IntegrationAdapter):
    name = "nmea0183"
    protocol = "nmea0183"

    def parse(self, payload: str) -> Iterable[NormalizedEvent]:
        sentence = payload.strip()
        if not sentence.startswith("$"):
            return []

        fields = sentence.split(",")
        sentence_type = fields[0][-3:]

        if sentence_type == "RMC":
            event = self._parse_rmc(fields, sentence)
            return [event] if event else []

        if sentence_type == "GGA":
            event = self._parse_gga(fields, sentence)
            return [event] if event else []

        return []

    def _parse_rmc(self, fields: list[str], sentence: str) -> Optional[NormalizedEvent]:
        if len(fields) < 9 or fields[2] != "A":
            return None

        return NormalizedEvent(
            event_type="position_fix",
            timestamp=_parse_hms(fields[1]) or datetime.now(timezone.utc),
            source=SourceRef(
                protocol=self.protocol,
                adapter=self.name,
                transport="serial_or_tcp",
                raw_sentence=sentence,
            ),
            lat=_parse_lat_lon(fields[3], fields[4]),
            lon=_parse_lat_lon(fields[5], fields[6]),
            speed=float(fields[7]) if fields[7] else None,
            course=float(fields[8]) if fields[8] else None,
            status="valid",
            payload={"sentence_type": "RMC"},
        )

    def _parse_gga(self, fields: list[str], sentence: str) -> Optional[NormalizedEvent]:
        if len(fields) < 10:
            return None

        quality = fields[6]
        if quality in {"", "0"}:
            return None

        return NormalizedEvent(
            event_type="position_fix",
            timestamp=_parse_hms(fields[1]) or datetime.now(timezone.utc),
            source=SourceRef(
                protocol=self.protocol,
                adapter=self.name,
                transport="serial_or_tcp",
                raw_sentence=sentence,
            ),
            lat=_parse_lat_lon(fields[2], fields[3]),
            lon=_parse_lat_lon(fields[4], fields[5]),
            altitude=float(fields[9]) if fields[9] else None,
            status="fix",
            payload={"sentence_type": "GGA", "quality": quality},
        )
