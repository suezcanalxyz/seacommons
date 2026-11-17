"""Regression: live-edge scans project only the required columns, without losing distress."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from core.db.models import IntelEventDB
from core.live_edge_publisher import LiveEdgePublisher, PublisherSettings


def test_collect_projects_required_fields_and_preserves_distress_under_ais_flood(
    tmp_path, monkeypatch
):
    eng = create_engine("sqlite:///:memory:")
    IntelEventDB.__table__.create(bind=eng)
    now = datetime.now(timezone.utc)
    with Session(eng) as session:
        session.add_all([
            IntelEventDB(
                id="distress-1",
                timestamp_utc=(now - timedelta(minutes=2)).isoformat(),
                type="distress", severity="critical",
                title="Distress", text="Source report",
                source="test_source", url="https://example.test/1",
                lat=35.1, lon=14.2, linked_mmsi="",
                meta={"location_status": "approximate", "test_key": "preserved"},
            ),
            IntelEventDB(
                id="spike-1",
                timestamp_utc=(now - timedelta(minutes=1)).isoformat(),
                type="ais_spike", severity="info",
                title="AIS", text="", source="test_source",
                lat=35.2, lon=14.3, meta={"test_key": "spike"},
            ),
        ])
        session.commit()

    session_state = {"open": False}

    @contextmanager
    def local_session_scope():
        with Session(eng) as session:
            session_state["open"] = True
            try:
                yield session
            finally:
                session_state["open"] = False

    monkeypatch.setattr("core.db.session.session_scope", local_session_scope)
    selected_sql = []

    def capture_sql(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selected_sql.append(statement)

    event.listen(eng, "before_cursor_execute", capture_sql)
    settings = PublisherSettings(
        edge_url="https://example.invalid/ingest", ingest_secret="test",
        node_id="test-node", outbox_path=tmp_path / "edge-outbox.db",
        scan_limit=1,
    )
    publisher = LiveEdgePublisher(settings)
    observed = []

    def public_stub(row, node_id, *, now, same_source):
        # Projection and outbox operations must never hold a PostgreSQL
        # read transaction open after both queries have materialized.
        assert session_state["open"] is False
        observed.append((row.id, row.meta, row.lat, row.lon, len(same_source)))
        return {"id": row.id + ":v1"}

    monkeypatch.setattr("core.live_edge_publisher.public_event_from_row", public_stub)
    try:
        assert publisher.collect() == 2
        assert {item[0] for item in observed} == {"distress-1", "spike-1"}
        distress = next(item for item in observed if item[0] == "distress-1")
        assert distress[1]["test_key"] == "preserved"
        assert distress[2:4] == (35.1, 14.2)
        assert distress[4] == 2
        assert len(selected_sql) == 2
        for statement in selected_sql:
            assert "intel_events.meta" in statement
            assert "intel_events.linked_mmsi" in statement
            assert "intel_events.created_at" not in statement
            assert "intel_events.live_expires_at" not in statement
    finally:
        publisher.client.close()
        publisher.outbox.connection.close()
        eng.dispose()
