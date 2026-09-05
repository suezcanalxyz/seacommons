"""Provider-neutral satellite evidence contract for Live/Play."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal

TemporalRelation = Literal["reverse", "nearest", "forward"]


@dataclass(frozen=True)
class SatelliteObservation:
    observation_id: str
    incident_id: str
    provider: str
    mission: str
    product_id: str
    acquisition_time: str
    discovered_at: str
    footprint: dict[str, Any] | None
    bbox: list[float] | None
    sensor_type: str
    temporal_relation: TemporalRelation
    temporal_delta_s: float
    asset_ref: str
    source_url: str
    provenance: dict[str, Any]
    resolution_m: float | None = None
    cloud_cover: float | None = None
    polarisation: list[str] | None = None
    evidence_status: str = "contextual"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def persist_observations(observations: list[SatelliteObservation]) -> int:
    """Persist metadata idempotently by deterministic observation_id."""
    from core.db.models import SatelliteObservationDB
    from core.db.session import session_scope
    from core.intel.lifecycle import parse_utc

    created = 0
    with session_scope() as db:
        for observation in observations:
            if db.get(SatelliteObservationDB, observation.observation_id) is not None:
                continue
            discovered = parse_utc(observation.discovered_at)
            db.add(SatelliteObservationDB(
                observation_id=observation.observation_id,
                incident_id=observation.incident_id,
                provider=observation.provider,
                mission=observation.mission,
                product_id=observation.product_id,
                acquisition_time=observation.acquisition_time,
                discovered_at=(discovered or datetime.now(timezone.utc)).replace(tzinfo=None),
                footprint=observation.footprint,
                bbox=observation.bbox,
                sensor_type=observation.sensor_type,
                temporal_relation=observation.temporal_relation,
                temporal_delta_s=observation.temporal_delta_s,
                asset_ref=observation.asset_ref,
                source_url=observation.source_url,
                provenance=observation.provenance,
                resolution_m=observation.resolution_m,
                cloud_cover=observation.cloud_cover,
                polarisation=observation.polarisation,
                evidence_status=observation.evidence_status,
            ))
            created += 1
    return created


def list_incident_observations(incident_id: str) -> list[SatelliteObservation]:
    from core.db.models import SatelliteObservationDB
    from core.db.session import session_scope

    with session_scope() as db:
        rows = (
            db.query(SatelliteObservationDB)
            .filter(SatelliteObservationDB.incident_id == incident_id)
            .order_by(SatelliteObservationDB.acquisition_time.asc())
            .all()
        )
        return [SatelliteObservation(
            observation_id=row.observation_id,
            incident_id=row.incident_id,
            provider=row.provider,
            mission=row.mission,
            product_id=row.product_id,
            acquisition_time=row.acquisition_time,
            discovered_at=row.discovered_at.replace(tzinfo=timezone.utc).isoformat()
            if row.discovered_at else "",
            footprint=row.footprint,
            bbox=list(row.bbox) if row.bbox else None,
            sensor_type=row.sensor_type,
            temporal_relation=row.temporal_relation,
            temporal_delta_s=float(row.temporal_delta_s or 0),
            asset_ref=row.asset_ref or "",
            source_url=row.source_url or "",
            provenance=dict(row.provenance or {}),
            resolution_m=row.resolution_m,
            cloud_cover=row.cloud_cover,
            polarisation=list(row.polarisation) if row.polarisation else None,
            evidence_status=row.evidence_status or "contextual",
        ) for row in rows]
