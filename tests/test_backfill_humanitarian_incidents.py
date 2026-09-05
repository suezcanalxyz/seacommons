from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from core.intel.backfill_humanitarian_incidents import find_candidates, run
from core.intel.humanitarian_incident import get_incident


@pytest.fixture(autouse=True)
def _tables():
    from core.db.models import HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import engine, session_scope

    HumanitarianIncidentDB.__table__.create(bind=engine(), checkfirst=True)
    IncidentTransitionDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(HumanitarianIncidentDB).delete()
        db.query(IncidentTransitionDB).delete()
    yield


def _insert_humanitarian_event(*, event_id: str, drift_job_id: str | None = None):
    from core.db.models import IntelEventDB
    from core.db.session import session_scope

    meta = {
        "is_distress": True,
        "maritime_domain": "sar",
        "source_policy": "operator_published",
        "publication_status": "published",
    }
    if drift_job_id:
        meta.update({"drift_status": "completed", "drift_job_id": drift_job_id})
    with session_scope() as db:
        db.add(IntelEventDB(
            id=event_id, timestamp_utc=datetime.now(timezone.utc).isoformat(),
            type="distress", severity="high", lat=35.5, lon=14.1,
            title="Humanitarian distress report", text="Rescue is urgent",
            url=f"https://example.test/{event_id}", source="Alarm Phone",
            maritime_domain="sar", meta=meta,
        ))


def test_persisted_humanitarian_event_without_incident_is_candidate():
    event_id = f"legacy-humanitarian-{uuid.uuid4()}"
    _insert_humanitarian_event(event_id=event_id)

    candidates = find_candidates(limit=500)
    assert any(candidate.event_id == event_id for candidate in candidates)


def test_dry_run_never_creates_incident():
    event_id = f"legacy-dry-{uuid.uuid4()}"
    _insert_humanitarian_event(event_id=event_id)

    report = run(apply=False, limit=500)
    assert report["scanned"] >= 1
    assert report["created"] == 0
    assert get_incident(event_id) is None


def test_apply_creates_canonical_incident_for_legacy_event():
    event_id = f"legacy-apply-{uuid.uuid4()}"
    _insert_humanitarian_event(event_id=event_id)

    report = run(apply=True, limit=500)
    incident = get_incident(event_id)
    assert report["created"] >= 1
    assert incident is not None
    assert incident["incident_status"] == "active"


def test_incident_then_drift_pointer_backfills_in_order():
    from core.intel.backfill_current_drift import run as run_drift_backfill
    from core.intel.drift_ownership import get_current_drift_id

    event_id = f"legacy-drift-{uuid.uuid4()}"
    _insert_humanitarian_event(event_id=event_id, drift_job_id="legacy-job-1")

    assert run(apply=True, limit=500)["created"] >= 1
    assert run_drift_backfill(apply=True, limit=500)["backfilled"] >= 1
    assert get_current_drift_id(event_id) == "legacy-job-1"


def test_cli_defaults_to_dry_run_and_prints_json(monkeypatch, capsys):
    import core.intel.backfill_humanitarian_incidents as module

    calls = []
    monkeypatch.setattr(module, "run", lambda **kwargs: calls.append(kwargs) or {"scanned": 3, "created": 0})
    assert module.main(["--limit", "25", "--days", "14"]) == 0
    assert calls == [{"apply": False, "limit": 25, "days": 14}]
    assert '"created": 0' in capsys.readouterr().out


def test_cli_apply_is_explicit(monkeypatch):
    import core.intel.backfill_humanitarian_incidents as module

    calls = []
    monkeypatch.setattr(module, "run", lambda **kwargs: calls.append(kwargs) or {"scanned": 1, "created": 1})
    assert module.main(["--apply"]) == 0
    assert calls[0]["apply"] is True
