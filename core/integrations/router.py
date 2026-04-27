from __future__ import annotations

from typing import Iterable, List

from core.domain.events import NormalizedEvent
from core.integrations.ais.adapter import AISAdapter
from core.integrations.base import IntegrationAdapter
from core.sensors.nmea0183.parser import NMEA0183Adapter


class IntegrationRouter:
    def __init__(self, adapters: Iterable[IntegrationAdapter] | None = None):
        self.adapters = list(adapters or [NMEA0183Adapter(), AISAdapter()])

    def route(self, payload: str) -> List[NormalizedEvent]:
        events: List[NormalizedEvent] = []
        for adapter in self.adapters:
            parsed = list(adapter.parse(payload))
            if parsed:
                events.extend(parsed)
        return events
