# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistence helpers for pilot mode."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from core.api.routes import forensic as forensic_routes
from core.db.models import AlertEvent, DriftResultDB, ForensicEvent
from core.db.session import session_scope
from core.forensic.packet import ForensicPacket


def create_alert(event_id: str, event: Any, status: str = "processing") -> None:
    with session_scope() as session:
        row = session.get(AlertEvent, event_id)
        if row is None:
            row = AlertEvent(
                event_id=event_id,
                timestamp_utc=event.timestamp.isoformat(),
                lat=event.lat,
                lon=event.lon,
                persons=event.persons,
                vessel_type=event.vessel_type,
                domain=event.domain,
                status=status,
            )
            session.add(row)
            return

        row.timestamp_utc = event.timestamp.isoformat()
        row.lat = event.lat
        row.lon = event.lon
        row.persons = event.persons
        row.vessel_type = event.vessel_type
        row.domain = event.domain
        row.status = status


def update_alert_status(event_id: str, status: str) -> None:
    with session_scope() as session:
        row = session.get(AlertEvent, event_id)
        if row is not None:
            row.status = status


def get_alert(event_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(AlertEvent, event_id)
        if row is None:
            return None
        drift = session.execute(
            select(DriftResultDB).where(DriftResultDB.event_id == event_id)
        ).scalar_one_or_none()
        return {
            "event_id": row.event_id,
            "event": {
                "lat": row.lat,
                "lon": row.lon,
                "timestamp": row.timestamp_utc,
                "persons": row.persons,
                "vessel_type": row.vessel_type,
                "domain": row.domain,
            },
            "drift_result": drift_to_dict(drift) if drift is not None else None,
            "status": row.status,
        }


def list_alerts() -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            select(AlertEvent).order_by(AlertEvent.created_at.desc())
        ).scalars().all()
        return [
            {
                "event_id": row.event_id,
                "event": {
                    "lat": row.lat,
                    "lon": row.lon,
                    "timestamp": row.timestamp_utc,
                    "persons": row.persons,
                    "vessel_type": row.vessel_type,
                    "domain": row.domain,
                },
                "status": row.status,
            }
            for row in rows
        ]


def create_drift_job(
    drift_id: str,
    *,
    event_id: str | None,
    lat: float,
    lon: float,
    domain: str,
    duration_h: int,
    started_at: datetime,
) -> None:
    with session_scope() as session:
        row = session.get(DriftResultDB, drift_id)
        if row is None:
            row = DriftResultDB(
                drift_id=drift_id,
                event_id=event_id,
                domain=domain,
                lat=lat,
                lon=lon,
                metadata_json={"start_time": started_at.isoformat(), "duration_h": duration_h},
                status="computing",
            )
            session.add(row)


def complete_drift_job(
    drift_id: str,
    *,
    event_id: str | None,
    lat: float,
    lon: float,
    domain: str,
    result: Any,
) -> None:
    with session_scope() as session:
        row = session.get(DriftResultDB, drift_id)
        if row is None:
            row = DriftResultDB(drift_id=drift_id)
            session.add(row)

        row.event_id = event_id
        row.domain = domain
        row.lat = lat
        row.lon = lon
        row.trajectory = result.trajectory
        row.cone_6h = result.cone_6h
        row.cone_12h = result.cone_12h
        row.cone_24h = result.cone_24h
        row.impact_point = result.impact_point
        row.metadata_json = result.metadata
        row.status = "completed"


def fail_drift_job(
    drift_id: str,
    *,
    event_id: str | None,
    lat: float,
    lon: float,
    domain: str,
    error_message: str,
) -> None:
    with session_scope() as session:
        row = session.get(DriftResultDB, drift_id)
        if row is None:
            row = DriftResultDB(drift_id=drift_id)
            session.add(row)

        row.event_id = event_id
        row.domain = domain
        row.lat = lat
        row.lon = lon
        row.metadata_json = {"error": error_message}
        row.status = "failed"


def get_drift(drift_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(DriftResultDB, drift_id)
        if row is None:
            return None
        return drift_to_dict(row)


def drift_to_dict(row: DriftResultDB | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "drift_id": row.drift_id,
        "event_id": row.event_id,
        "domain": row.domain,
        "lat": row.lat,
        "lon": row.lon,
        "trajectory": row.trajectory,
        "cone_6h": row.cone_6h,
        "cone_12h": row.cone_12h,
        "cone_24h": row.cone_24h,
        "impact_point": row.impact_point,
        "metadata": row.metadata_json or {},
        "status": getattr(row, "status", "completed"),
    }


def save_forensic_packet(packet_dict: dict[str, Any]) -> None:
    packet = ForensicPacket.model_validate(packet_dict)
    forensic_routes.store_packet(packet.model_dump(mode="json"))
    with session_scope() as session:
        row = session.get(ForensicEvent, packet.event_id)
        if row is None:
            row = ForensicEvent(event_id=packet.event_id)
            session.add(row)

        row.timestamp_utc = packet.timestamp_utc
        row.classification = packet.classification
        row.confidence = packet.confidence
        row.position = packet.position
        row.vessel_id = packet.vessel_id
        row.contributing_sensors = packet.contributing_sensors
        row.sensor_data = packet.sensor_data
        row.drift_result = packet.drift_result
        row.waveform_miniseed_b64 = packet.waveform_miniseed_b64
        row.rinex_dtec_b64 = packet.rinex_dtec_b64
        row.public_key = packet.public_key
        row.hash_blake3 = packet.hash_blake3
        row.signature_ed25519 = packet.signature_ed25519


def get_forensic_packet(event_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        row = session.get(ForensicEvent, event_id)
        if row is None:
            return None
        return {
            "event_id": row.event_id,
            "timestamp_utc": row.timestamp_utc,
            "classification": row.classification,
            "confidence": row.confidence,
            "position": row.position or {},
            "vessel_id": row.vessel_id or "",
            "contributing_sensors": row.contributing_sensors or [],
            "sensor_data": row.sensor_data or {},
            "drift_result": row.drift_result or {},
            "waveform_miniseed_b64": row.waveform_miniseed_b64 or "",
            "rinex_dtec_b64": row.rinex_dtec_b64 or "",
            "public_key": row.public_key or "",
            "hash_blake3": row.hash_blake3 or "",
            "signature_ed25519": row.signature_ed25519 or "",
        }


def list_forensic_packets(since: str | None = None) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.execute(
            select(ForensicEvent).order_by(ForensicEvent.created_at.desc())
        ).scalars().all()

        packets: list[dict[str, Any]] = []
        for row in rows:
            packet = get_forensic_packet(row.event_id)
            if packet is None:
                continue
            if since and packet.get("timestamp_utc", "") < since:
                continue
            packets.append(packet)
        return packets
