from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from core.intel.drift_ownership import get_current_drift_id


@pytest.mark.parametrize(
    ("lifecycle", "status", "expected"),
    [
        ("resolved", "resolved", None),
        ("archived", "outcome_unknown", None),
        ("needs_review", "resolved", None),
        ("needs_review", "needs_review", "legacy-job"),
    ],
)
def test_terminal_legacy_pointer_is_never_current(monkeypatch, lifecycle, status, expected):
    from core.db import session as db_session

    row = SimpleNamespace(
        lifecycle=lifecycle, incident_status=status, current_drift_id="legacy-job"
    )

    class FakeSession:
        def get(self, _model, _id):
            return row

    @contextmanager
    def fake_scope():
        yield FakeSession()

    monkeypatch.setattr(db_session, "session_scope", fake_scope)
    assert get_current_drift_id("example") == expected
