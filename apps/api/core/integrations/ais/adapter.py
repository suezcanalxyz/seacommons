from __future__ import annotations

from typing import Iterable

from core.domain.events import NormalizedEvent, SourceRef
from core.integrations.base import IntegrationAdapter


class AISAdapter(IntegrationAdapter):
    name = "ais"
    protocol = "nmea0183-ais"

    def parse(self, payload: str) -> Iterable[NormalizedEvent]:
        sentence = payload.strip()
        if not sentence.startswith("!AIVDM") and not sentence.startswith("!AIVDO"):
            return []

        fields = sentence.split(",")
        if len(fields) < 6:
            return []

        return [
            NormalizedEvent(
                event_type="vessel_track",
                source=SourceRef(
                    protocol=self.protocol,
                    adapter=self.name,
                    transport="serial_or_udp",
                    raw_sentence=sentence,
                ),
                status="raw_ais_received",
                payload={
                    "sentence_type": fields[0],
                    "fragment_count": fields[1],
                    "fragment_number": fields[2],
                    "channel": fields[4],
                    "payload": fields[5],
                },
            )
        ]
