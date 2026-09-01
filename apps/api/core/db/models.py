# SPDX-License-Identifier: AGPL-3.0-or-later
"""SQLAlchemy ORM models — append-only forensic and operational tables."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, Column, String, Float, Integer, DateTime, Index, JSON, Text,
    UniqueConstraint, ForeignKey, create_engine
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


class VesselTrackDB(Base):
    """Time-series of AIS positions per MMSI — the primitive the dark-vessel
    detectors (gap, rendezvous / STS, loiter, spoof-pattern, identity history)
    are built on. Throttled to at most one row per MMSI per ~60 s at write time
    and pruned to a rolling window (config VESSEL_TRACK_RETENTION_DAYS)."""
    __tablename__ = "vessel_tracks"
    id            = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    mmsi          = Column(String(16), nullable=False)
    ts            = Column(DateTime, nullable=False)          # AIS-reported time
    received_at   = Column(DateTime, nullable=False)          # our wall clock at receipt
    lat           = Column(Float, nullable=False)
    lon           = Column(Float, nullable=False)
    sog           = Column(Float)                              # knots
    cog           = Column(Float)                              # degrees
    heading       = Column(Float)                              # degrees, None if 511
    nav_status    = Column(Integer)
    source        = Column(String(24), nullable=False, default="aisstream")

    __table_args__ = (
        Index("ix_vessel_tracks_mmsi_ts", "mmsi", "ts"),
        Index("ix_vessel_tracks_ts", "ts"),
    )


class SanctionedVesselDB(Base):
    """Aggregated sanctioned-vessel reference (OpenSanctions + OFAC SDN), rebuilt
    daily by core.mda.identity.refresh_sanctions()."""
    __tablename__ = "sanctioned_vessels"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    source_list = Column(String(24), nullable=False, index=True)
    name        = Column(String(200), default="")
    name_upper  = Column(String(200), index=True)
    imo         = Column(String(10), index=True)
    mmsi        = Column(String(12), index=True)
    program     = Column(String(160), default="")
    listed_on   = Column(String(12))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))


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


class IntelEventDB(Base):
    """Lightweight log of intel events from all scraping channels."""
    __tablename__ = "intel_events"
    id            = Column(String(16),  primary_key=True)
    timestamp_utc = Column(String(32),  nullable=False, index=True)
    type          = Column(String(32),  nullable=False, index=True)
    severity      = Column(String(16),  nullable=False, index=True)
    lat           = Column(Float)
    lon           = Column(Float)
    title         = Column(String(256), nullable=False)
    text          = Column(Text,        default="")
    url           = Column(String(512), default="")
    source        = Column(String(64),  nullable=False, index=True)
    linked_mmsi   = Column(String(16),  default="")
    meta          = Column(JSON,        default=dict)
    created_at    = Column(DateTime,    default=lambda: datetime.now(timezone.utc))
    # ── Canonical live classification (docs/fixes.md Phase 2.2 / 3.2) ──────────
    # Dual-written alongside `meta` for one release. All nullable / defaulted so
    # the migration is safe on a populated table; store the enum *.value string.
    schema_version           = Column(Integer,     nullable=False, server_default="1")
    source_timestamp_utc     = Column(String(32))
    received_at              = Column(DateTime,    default=lambda: datetime.now(timezone.utc))
    maritime_domain          = Column(String(32),  index=True)
    operational_tier         = Column(String(16),  index=True)
    humanitarian_case_type   = Column(String(32),  index=True)
    incident_lifecycle       = Column(String(16),  index=True)
    location_status          = Column(String(32))
    coordinate_review_status = Column(String(40))
    location_uncertainty_m   = Column(Float)


class IngestedSignalDB(Base):
    """Canonical inbound signal; external delivery key makes webhooks idempotent."""
    __tablename__ = "ingested_signals"
    signal_id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.organization_id"), nullable=True, index=True)
    connector_id = Column(String(36), ForeignKey("connectors.connector_id"), nullable=True, index=True)
    source_channel = Column(String(32), nullable=False, index=True)
    source_id = Column(String(256), nullable=False)
    provider_message_id = Column(String(256), nullable=True)
    payload = Column(JSON, nullable=False)
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        UniqueConstraint(
            "source_channel", "provider_message_id", name="uq_ingested_signal_delivery"
        ),
    )


class CaseDB(Base):
    __tablename__ = "cases"
    case_id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.organization_id"), nullable=True, index=True)
    title = Column(String(256), nullable=False)
    status = Column(String(32), nullable=False, default="open", index=True)
    case_type = Column(
        String(32), nullable=False, default="distress_sar",
        server_default="distress_sar", index=True,
    )
    priority = Column(String(16), nullable=False, default="medium", index=True)
    sensitivity = Column(String(16), nullable=False, default="restricted")
    summary = Column(Text, default="")
    lat = Column(Float)
    lon = Column(Float)
    persons = Column(Float)
    assigned_to = Column(String(256))
    retention_until = Column(DateTime)
    legal_hold = Column(Integer, nullable=False, default=0)
    created_by = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CaseSignalDB(Base):
    __tablename__ = "case_signals"
    case_id = Column(String(36), ForeignKey("cases.case_id", ondelete="CASCADE"), primary_key=True)
    signal_id = Column(String(36), ForeignKey("ingested_signals.signal_id", ondelete="CASCADE"), primary_key=True)
    linked_by = Column(String(256), nullable=False)
    linked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CaseIntelEventDB(Base):
    """Bridge between a case and the OSINT intel events that triggered / support it.

    ``case_signals`` only links messaging-channel signals (``ingested_signals``);
    OSINT events live in ``intel_events`` and had no path to a case. The
    correlation/fusion engine writes rows here when it auto-opens a case, and
    the operator can link more. No FK to ``intel_events`` — an intel event row
    is persisted on a background thread and may not exist yet when the link is
    made; the id is stable regardless.
    """

    __tablename__ = "case_intel_events"
    case_id = Column(String(36), ForeignKey("cases.case_id", ondelete="CASCADE"), primary_key=True)
    event_id = Column(String(32), primary_key=True)
    role = Column(String(32), nullable=False, default="contributing")
    linked_by = Column(String(256), nullable=False)
    linked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CaseTimelineDB(Base):
    __tablename__ = "case_timeline"
    entry_id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(32), nullable=False)
    actor = Column(String(256), nullable=False)
    body = Column(Text, default="")
    data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class CaseAttachmentDB(Base):
    __tablename__ = "case_attachments"
    attachment_id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False, index=True)
    object_key = Column(String(512), nullable=False, unique=True)
    filename = Column(String(256), nullable=False)
    content_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    uploaded_by = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class AuditLogDB(Base):
    __tablename__ = "audit_log"
    audit_id = Column(String(36), primary_key=True)
    actor = Column(String(256), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(64), nullable=False, index=True)
    data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class JobDB(Base):
    __tablename__ = "jobs"
    job_id = Column(String(36), primary_key=True)
    job_type = Column(String(64), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="queued", index=True)
    payload = Column(JSON, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    available_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    lease_until = Column(DateTime)
    worker_id = Column(String(128))
    last_error = Column(Text)
    result = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class WorkerHeartbeatDB(Base):
    __tablename__ = "worker_heartbeats"
    worker_id = Column(String(128), primary_key=True)
    hostname = Column(String(256), nullable=False)
    process_id = Column(Integer, nullable=False)
    current_job_id = Column(String(36))
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class OrganizationDB(Base):
    __tablename__ = "organizations"
    organization_id = Column(String(36), primary_key=True)
    name = Column(String(256), nullable=False, unique=True)
    slug = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class MembershipDB(Base):
    __tablename__ = "memberships"
    organization_id = Column(String(36), ForeignKey("organizations.organization_id", ondelete="CASCADE"), primary_key=True)
    subject = Column(String(256), primary_key=True)
    role = Column(String(32), nullable=False, default="member")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ConnectorDB(Base):
    """Partner-owned inbound channel.

    Provider credentials are never stored here. ``secret_ref`` points to an
    external secret manager entry controlled by the deployment environment.
    """
    __tablename__ = "connectors"
    connector_id = Column(String(36), primary_key=True)
    organization_id = Column(
        String(36),
        ForeignKey("organizations.organization_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = Column(String(32), nullable=False, index=True)
    display_name = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False, default="pending", index=True)
    external_account_id = Column(String(128))
    external_channel_id = Column(String(128), nullable=False)
    display_address = Column(String(128))
    secret_ref = Column(String(256))
    publication_policy = Column(String(16), nullable=False, default="private")
    configuration = Column(JSON, default=dict)
    created_by = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_seen_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint(
            "provider", "external_channel_id", name="uq_connector_provider_channel"
        ),
    )


class CaseAccessDB(Base):
    __tablename__ = "case_access"
    case_id = Column(String(36), ForeignKey("cases.case_id", ondelete="CASCADE"), primary_key=True)
    subject = Column(String(256), primary_key=True)
    permission = Column(String(16), nullable=False, default="read")
    granted_by = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DeletionRequestDB(Base):
    __tablename__ = "deletion_requests"
    request_id = Column(String(36), primary_key=True)
    organization_id = Column(String(36), ForeignKey("organizations.organization_id"), nullable=True)
    resource_type = Column(String(64), nullable=False)
    resource_id = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="pending", index=True)
    requested_by = Column(String(256), nullable=False)
    reviewed_by = Column(String(256))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = Column(DateTime)


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
