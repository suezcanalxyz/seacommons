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
