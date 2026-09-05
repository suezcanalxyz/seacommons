from __future__ import annotations


def test_humanitarian_reconcile_job_calls_persisted_reconciler(monkeypatch):
    from core import scheduler

    calls = []

    def fake_reconcile_stale_incidents():
        calls.append(True)
        return 2

    monkeypatch.setattr(
        "core.intel.humanitarian_incident.reconcile_stale_incidents",
        fake_reconcile_stale_incidents,
    )
    scheduler._job_reconcile_humanitarian_incidents()
    assert calls == [True]


def test_incident_watch_job_claims_bounded_batch_and_executes_each(monkeypatch):
    from core import scheduler

    claimed = [
        {"watch_id": "watch:a", "incident_id": "a"},
        {"watch_id": "watch:b", "incident_id": "b"},
    ]
    calls = []

    monkeypatch.setattr(
        "core.intel.incident_watch.claim_due_watches",
        lambda **kwargs: claimed,
    )
    monkeypatch.setattr(
        "core.intel.incident_watch.run_claimed_watch",
        lambda watch_id, **kwargs: calls.append(watch_id) or {"executed": True},
    )

    scheduler._job_incident_watch()
    assert calls == ["watch:a", "watch:b"]


def test_scheduler_registers_incident_watch_job():
    from core import scheduler

    scheduler.stop()
    try:
        scheduler.start()
        ids = {job["id"] for job in scheduler.status()["jobs"]}
        assert "incident_watch" in ids
    finally:
        scheduler.stop()
