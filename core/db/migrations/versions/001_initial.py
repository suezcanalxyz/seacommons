"""001 initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

Creates tables:
- forensic_events  (append-only, signed)
- anomaly_events
- drift_results
- alert_events
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── forensic_events ────────────────────────────────────────────────────────
    op.create_table(
        "forensic_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(64), nullable=False, unique=True),
        sa.Column("sensor_source", sa.String(32), nullable=False),
        sa.Column("anomaly_type", sa.String(64), nullable=False),
        sa.Column("timestamp_utc", sa.String(32), nullable=False),
        sa.Column("location_lat", sa.Float, nullable=True),
        sa.Column("location_lon", sa.Float, nullable=True),
        sa.Column("raw_value", sa.Float, nullable=True),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("platform_id", sa.String(64), nullable=False),
        sa.Column("ed25519_signature", sa.Text, nullable=True),
        sa.Column("blake3_chain", sa.Text, nullable=True),
        sa.Column("miniseed_b64", sa.Text, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_forensic_events_timestamp", "forensic_events", ["timestamp_utc"])
    op.create_index("ix_forensic_events_sensor", "forensic_events", ["sensor_source"])

    # ── anomaly_events ─────────────────────────────────────────────────────────
    op.create_table(
        "anomaly_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("sensor_source", sa.String(32), nullable=False),
        sa.Column("anomaly_type", sa.String(64), nullable=False),
        sa.Column("timestamp_utc", sa.String(32), nullable=False),
        sa.Column("location_lat", sa.Float, nullable=True),
        sa.Column("location_lon", sa.Float, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("platform_id", sa.String(64), nullable=False),
        sa.Column("raw_value", sa.Float, nullable=True),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_anomaly_events_timestamp", "anomaly_events", ["timestamp_utc"])

    # ── drift_results ──────────────────────────────────────────────────────────
    op.create_table(
        "drift_results",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False, unique=True),
        sa.Column("origin_lat", sa.Float, nullable=False),
        sa.Column("origin_lon", sa.Float, nullable=False),
        sa.Column("model", sa.String(32), nullable=False),
        sa.Column("duration_h", sa.Float, nullable=False),
        sa.Column("n_particles", sa.Integer, nullable=False),
        sa.Column("centroid_lat", sa.Float, nullable=True),
        sa.Column("centroid_lon", sa.Float, nullable=True),
        sa.Column("search_area_km2", sa.Float, nullable=True),
        sa.Column("geojson", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ── alert_events ───────────────────────────────────────────────────────────
    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("classification", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("sources_json", sa.Text, nullable=False),
        sa.Column("urgent", sa.Boolean, nullable=False, default=False),
        sa.Column("timestamp_utc", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_alert_events_timestamp", "alert_events", ["timestamp_utc"])


def downgrade() -> None:
    op.drop_table("alert_events")
    op.drop_table("drift_results")
    op.drop_table("anomaly_events")
    op.drop_table("forensic_events")
