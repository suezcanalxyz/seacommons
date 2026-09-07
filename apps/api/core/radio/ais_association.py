# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, String

from core.db.models import Base
from core.radio.provider import DecodedRadioMessage


class RadioAISAssociationDB(Base):
    """Audit record linking decoded DSC evidence to recent AIS history."""

    __tablename__ = "radio_ais_associations"

    observation_id = Column(String(64), primary_key=True)
    mmsi = Column(String(16), nullable=False, index=True)
    match_status = Column(String(32), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    distance_km = Column(Float)
    ais_observed_at = Column(String(40))
    episode_eligible = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class RadioAISAssociation:
    observation_id: str
    mmsi: str
    match_status: str
    confidence: float
    distance_km: float | None
    ais_observed_at: str | None
    episode_eligible: bool


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_ts(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _recent_ais_points(mmsi: str, observed_at: datetime) -> list[dict]:
    from core.vessels.track_store import track_store

    since = observed_at - timedelta(minutes=30)
    return track_store.track(mmsi, since=since, limit=120)


def associate_dsc_with_ais(
    message: DecodedRadioMessage,
    *,
    observation_id: str,
) -> RadioAISAssociation:
    payload = message.payload if isinstance(message.payload, dict) else {}
    mmsi = str(payload.get("mmsi") or "").strip()
    if not mmsi:
        raise ValueError("DSC AIS association requires MMSI")

    points = _recent_ais_points(mmsi, message.observed_at)
    latest = points[-1] if points else None
    if latest is None:
        return RadioAISAssociation(observation_id, mmsi, "unmatched", 0.2, None, None, False)

    ais_ts = _parse_ts(latest.get("ts"))
    age_s = abs((message.observed_at - ais_ts).total_seconds()) if ais_ts else None
    temporal_ok = age_s is not None and age_s <= 30 * 60
    radio_lat = payload.get("latitude")
    radio_lon = payload.get("longitude")

    if radio_lat is None or radio_lon is None:
        return RadioAISAssociation(
            observation_id,
            mmsi,
            "identity_only",
            0.8 if temporal_ok else 0.65,
            None,
            ais_ts.isoformat() if ais_ts else None,
            False,
        )

    try:
        distance = _haversine_km(
            float(radio_lat),
            float(radio_lon),
            float(latest["lat"]),
            float(latest["lon"]),
        )
    except (KeyError, TypeError, ValueError):
        return RadioAISAssociation(
            observation_id,
            mmsi,
            "identity_only",
            0.7 if temporal_ok else 0.55,
            None,
            ais_ts.isoformat() if ais_ts else None,
            False,
        )

    if temporal_ok and distance <= 25.0:
        status, confidence, eligible = "strong", 0.95, True
    elif temporal_ok and distance <= 75.0:
        status, confidence, eligible = "weak", 0.65, False
    else:
        status, confidence, eligible = "conflict", 0.35, False

    return RadioAISAssociation(
        observation_id,
        mmsi,
        status,
        confidence,
        round(distance, 2),
        ais_ts.isoformat() if ais_ts else None,
        eligible,
    )


def persist_association(db, association: RadioAISAssociation):
    row = db.query(RadioAISAssociationDB).filter_by(observation_id=association.observation_id).first()
    values = {
        "mmsi": association.mmsi,
        "match_status": association.match_status,
        "confidence": association.confidence,
        "distance_km": association.distance_km,
        "ais_observed_at": association.ais_observed_at,
        "episode_eligible": association.episode_eligible,
    }
    if row is None:
        row = RadioAISAssociationDB(observation_id=association.observation_id, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    db.flush()
    return row


def associate_and_persist_dsc(
    message: DecodedRadioMessage,
    *,
    observation_id: str,
) -> RadioAISAssociation | None:
    payload = message.payload if isinstance(message.payload, dict) else {}
    if not str(payload.get("mmsi") or "").strip():
        return None
    association = associate_dsc_with_ais(message, observation_id=observation_id)
    from core.db.session import session_scope

    with session_scope() as db:
        persist_association(db, association)
    return association


def public_association(association: RadioAISAssociation) -> dict[str, object]:
    return {
        "mmsi": association.mmsi,
        "match_status": association.match_status,
        "confidence": association.confidence,
        "distance_km": association.distance_km,
        "ais_observed_at": association.ais_observed_at,
        "episode_eligible": association.episode_eligible,
    }


def persist_strong_radio_ais_episode(
    message: DecodedRadioMessage,
    association: RadioAISAssociation,
):
    if not association.episode_eligible or association.match_status != "strong":
        return None

    from core.intel.episode_store import save_episode

    payload = message.payload if isinstance(message.payload, dict) else {}
    geometry = None
    lat = payload.get("latitude")
    lon = payload.get("longitude")
    if lat is not None and lon is not None:
        try:
            geometry = {"type": "Point", "coordinates": [float(lon), float(lat)]}
        except (TypeError, ValueError):
            geometry = None

    material = f"{association.observation_id}|{association.mmsi}|radio_dsc_ais"
    episode_id = "radio-ais:" + hashlib.blake2s(material.encode(), digest_size=12).hexdigest()
    observed = message.observed_at.isoformat()
    feature = {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "episode_id": episode_id,
            "episode_family": "radio_dsc_ais",
            "subject_ids": [f"mmsi:{association.mmsi}"],
            "observation_ids": [association.observation_id],
            "feature_ids": [],
            "independence_groups": ["radio", "ais"],
            "verification_status": "cross_modal_correlated",
            "behaviour_context": {
                "radio_ais_match_status": association.match_status,
                "radio_ais_confidence": association.confidence,
                "radio_ais_distance_km": association.distance_km,
            },
            "alternative_explanations": [
                "DSC position may be stale or manually entered",
                "AIS position may be delayed or absent",
            ],
            "first_observed_at": observed,
            "last_observed_at": observed,
            "episode_status": "active",
        },
    }
    return save_episode(feature)
