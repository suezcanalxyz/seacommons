from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from core.domain.events import NormalizedEvent

# Only consider events from the last N minutes for the live vessel picture
_LIVE_WINDOW_MINUTES = 60


def _entity_id(event: NormalizedEvent) -> str:
    return event.source.vessel_id or event.source.device_id or "ownship"


class VesselStateAggregator:
    def build(self, events: List[dict]) -> Dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=_LIVE_WINDOW_MINUTES)

        normalized = []
        for event in events:
            try:
                e = NormalizedEvent.model_validate(event)
                if e.timestamp >= cutoff:
                    normalized.append(e)
            except Exception:
                continue

        vessels: dict[str, dict[str, Any]] = {}
        raw_ais_counter: Counter[str] = Counter()

        for event in normalized:
            vessel_id = _entity_id(event)
            snapshot = vessels.setdefault(
                vessel_id,
                {
                    "vessel_id": vessel_id,
                    "ship_name": None,
                    "last_seen": None,
                    "event_count": 0,
                    "last_position": None,
                    "navigation": {},
                    "sources": [],
                    "statuses": [],
                    "payload": {},
                },
            )

            snapshot["event_count"] += 1
            snapshot["last_seen"] = event.timestamp.isoformat()

            source_name = event.source.adapter or event.source.protocol
            if source_name not in snapshot["sources"]:
                snapshot["sources"].append(source_name)

            if event.status and event.status not in snapshot["statuses"]:
                snapshot["statuses"].append(event.status)

            if event.payload:
                snapshot["payload"].update(event.payload)
                if event.payload.get("ship_name"):
                    snapshot["ship_name"] = event.payload["ship_name"]

            if event.event_type == "position_fix" and event.lat is not None and event.lon is not None:
                snapshot["last_position"] = {
                    "lat": event.lat,
                    "lon": event.lon,
                    "timestamp": event.timestamp.isoformat(),
                    "altitude": event.altitude,
                }
                snapshot["navigation"] = {
                    "course": event.course,
                    "speed": event.speed,
                    "heading": event.heading,
                }

            if event.event_type == "vessel_track" and event.status == "raw_ais_received":
                raw_ais_counter[vessel_id] += 1

        vessel_list = sorted(
            vessels.values(),
            key=lambda vessel: vessel["last_seen"] or "",
            reverse=True,
        )

        features = []
        for vessel in vessel_list:
            position = vessel.get("last_position")
            if not position:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [position["lon"], position["lat"]],
                    },
                    "properties": {
                        "vessel_id": vessel["vessel_id"],
                        "ship_name": vessel.get("ship_name") or vessel["vessel_id"],
                        "last_seen": vessel["last_seen"],
                        "event_count": vessel["event_count"],
                        "course": vessel["navigation"].get("course"),
                        "speed": vessel["navigation"].get("speed"),
                        "heading": vessel["navigation"].get("heading"),
                        "sources": vessel["sources"],
                        "statuses": vessel["statuses"],
                        "destination": vessel["payload"].get("destination", ""),
                        "ship_type": vessel["payload"].get("ship_type"),
                        "imo": vessel["payload"].get("imo"),
                        "ais_class": vessel["payload"].get("class", "A"),
                    },
                }
            )

        ownship = vessels.get("ownship")
        return {
            "summary": {
                "vessel_count": len(vessel_list),
                "positioned_vessels": len(features),
                "raw_ais_entities": sum(raw_ais_counter.values()),
            },
            "ownship": ownship,
            "vessels": vessel_list,
            "geojson": {
                "type": "FeatureCollection",
                "features": features,
            },
        }
