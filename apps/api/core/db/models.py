# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLAlchemy ORM models — append-only forensic and operational tables."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, DateTime, JSON, Text, create_engine
)
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class ForensicEvent(Base):
    """Append-only forensic log — one row per signed event."""
    __tablename__ = "forensic_events"
    event_id         = Column(String(36), primary_key=True)
    timestamp_utc    = Column(String(32), nullable=False)
    classification   = Column(String(64), nullable=False, index=True)
    confidence       = Column(Float, nullable=False)
    position         = Column(JSON)
    vessel_id        = Column(String(32))
    contributing_sensors = Column(JSON)
    sensor_data      = Column(JSON)
    drift_result     = Column(JSON)
    waveform_miniseed_b64 = Column(Text, default="")
    rinex_dtec_b64   = Column(Text, default="")
    public_key       = Column(String(128))
    hash_blake3      = Column(String(64))
    signature_ed25519 = Column(String(128))
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AnomalyEvent(Base):
    """All detected anomalies from any sensor channel."""
    __tablename__ = "anomaly_events"
    event_id      = Column(String(36), primary_key=True)
    timestamp_utc = Column(String(32), nullable=False)
    anomaly_type  = Column(String(64), nullable=False, index=True)
    sensor_source = Column(String(32), nullable=False, index=True)
    confidence    = Column(Float, nullable=False)
    lat           = Column(Float)
    lon           = Column(Float)
    data          = Column(JSON)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DriftResultDB(Base):
    """Computed drift trajectories — GeoJSON stored as JSON."""
    __tablename__ = "drift_results"
    drift_id      = Column(String(36), primary_key=True)
    event_id      = Column(String(36), index=True)
    domain        = Column(String(32))
    lat           = Column(Float)
    lon           = Column(Float)
    trajectory    = Column(JSON)
    cone_6h       = Column(JSON)
    cone_12h      = Column(JSON)
    cone_24h      = Column(JSON)
    impact_point  = Column(JSON)
    metadata_json = Column("metadata", JSON)
    status        = Column(String(32), default="completed")
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AlertEvent(Base):
    """Distress alerts from /api/v1/alert."""
    __tablename__ = "alert_events"
    event_id      = Column(String(36), primary_key=True)
    timestamp_utc = Column(String(32), nullable=False)
    lat           = Column(Float)
    lon           = Column(Float)
    persons       = Column(Float)
    vessel_type   = Column(String(64))
    domain        = Column(String(32))
    status        = Column(String(32), default="processing")
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def create_all(database_url: str) -> None:
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    # Self-test with SQLite in-memory
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ev = ForensicEvent(
            event_id="test-001",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            classification="test",
            confidence=0.9,
            position={"lat": 35.5, "lon": 14.0, "alt": 0, "source": "manual"},
        )
        session.add(ev)
        session.commit()
        count = session.query(ForensicEvent).count()
    print(f"DB models self-test OK: {count} forensic event(s) created")
