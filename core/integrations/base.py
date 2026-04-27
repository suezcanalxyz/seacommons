from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from core.domain.events import NormalizedEvent


class IntegrationAdapter(ABC):
    name: str = "integration"
    protocol: str = "unknown"

    @abstractmethod
    def parse(self, payload: str) -> Iterable[NormalizedEvent]:
        raise NotImplementedError
