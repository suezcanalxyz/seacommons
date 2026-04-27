from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import List

from core.domain.events import NormalizedEvent


DEFAULT_STORE_PATH = Path("core/data/integration_events.jsonl")


class IntegrationEventStore:
    def __init__(self, path: Path | str = DEFAULT_STORE_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def append(self, event: NormalizedEvent) -> None:
        line = json.dumps(event.model_dump(mode="json"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def append_many(self, events: List[NormalizedEvent]) -> None:
        if not events:
            return
        lines = [json.dumps(event.model_dump(mode="json")) for event in events]
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(line + "\n")

    def recent(self, limit: int = 50) -> List[dict]:
        if not self.path.exists():
            return []

        with self._lock:
            with self.path.open("r", encoding="utf-8") as handle:
                lines = handle.readlines()

        return [json.loads(line) for line in lines[-limit:] if line.strip()]

    def all(self) -> List[dict]:
        if not self.path.exists():
            return []

        with self._lock:
            with self.path.open("r", encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]
