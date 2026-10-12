"""Regression tests for the retained-history Overall contract.

Counts represent retained Intel events, never confirmed humanitarian incidents.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_overall_returns_cumulative_months_and_semantics(monkeypatch):
    from core.api.main import app
    from core.api.routes import ops

    monkeypatch.setattr(ops, "_overall_cache", None)
    monkeypatch.setattr(ops, "_retained_intel_history", lambda: {
        "total_events": 378826,
        "positioned_events": 378107,
        "unpositioned_events": 719,
        "oldest_event_utc": "2026-05-01T00:00:00Z",
        "newest_event_utc": "2026-10-12T10:00:00Z",
        "by_type": [{"type": "distress", "count": 42}],
        "monthly": [{"month": "2026-05", "count": 100}, {"month": "2026-10", "count": 200}],
    })
    response = TestClient(app).get("/api/v1/ops/overall")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "retained_intel_events"
    assert payload["intel_record"]["total_events"] == 378826
    assert [row["month"] for row in payload["intel_record"]["monthly"]] == ["2026-05", "2026-10"]
    assert "not confirmed incidents" in payload["count_semantics"].lower()
    assert "payload_ref" not in response.text


def test_overall_fails_closed_on_database_errors(monkeypatch):
    from core.api.main import app
    from core.api.routes import ops

    monkeypatch.setattr(ops, "_overall_cache", None)
    def broken():
        raise RuntimeError("database temporarily unavailable")
    monkeypatch.setattr(ops, "_retained_intel_history", broken)
    response = TestClient(app).get("/api/v1/ops/overall")
    assert response.status_code == 503
    assert response.json()["detail"] == "Overall data temporarily unavailable"
    assert "database temporarily unavailable" not in response.text
