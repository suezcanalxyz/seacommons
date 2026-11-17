"""Regression for lean durable event reads (no production DB writes)."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from core.db.models import IntelEventDB
from core.intel.store import IntelStore


def test_persisted_events_projection_preserves_filters_order_and_metadata(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    IntelEventDB.__table__.create(engine)
    now = datetime.now(timezone.utc)
    earlier = (now - timedelta(days=2)).isoformat()
    later = (now - timedelta(days=1)).isoformat()
    other = (now - timedelta(hours=12)).isoformat()
    with Session(engine) as session:
        session.add_all([
            IntelEventDB(id="a", timestamp_utc=earlier, type="news", severity="info", title="Earlier", source="source_a", text="first", meta={"key": "one"}),
            IntelEventDB(id="b", timestamp_utc=later, type="news", severity="info", title="Later", source="source_a", text="second", meta={"key": "two"}),
            IntelEventDB(id="c", timestamp_utc=other, type="news", severity="info", title="Other", source="source_b", text="third", meta={"key": "three"}),
        ])
        session.commit()

    @contextmanager
    def fake_session_scope():
        with Session(engine) as session:
            yield session

    monkeypatch.setattr("core.db.session.session_scope", fake_session_scope)
    sql = []
    @event.listens_for(engine, "before_cursor_execute")
    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            sql.append(statement)

    result = IntelStore().persisted_events(source="source_a", max_age_days=7, limit=2)
    assert [item.id for item in result] == ["b", "a"]
    assert result[0].metadata == {"key": "two"}
    assert result[0].text == "second"
    assert len(sql) == 1
    selected = sql[0].split(" FROM ")[0]
    assert "intel_events.created_at" not in selected
    assert "intel_events.schema_version" not in selected
    assert "intel_events.live_expires_at" not in selected
    assert "intel_events.meta" in selected
    engine.dispose()
