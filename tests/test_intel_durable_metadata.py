# SPDX-License-Identifier: AGPL-3.0-or-later
"""Durable metadata transitions after AIS churn evicts a SAR event from RAM."""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from core.intel.store import IntelStore


def _mock_session(monkeypatch, row):
    class Session:
        def get(self, _model, key):
            return row if row is not None and key == "evicted-case" else None

        def flush(self):
            pass

    @contextmanager
    def session_scope():
        yield Session()

    monkeypatch.setattr("core.db.session.session_scope", session_scope)


def test_evicted_case_drift_status_is_durably_merged(monkeypatch):
    row = SimpleNamespace(
        meta={
            "coordinate_source": "media_ocr_consensus",
            "location_uncertainty_m": 3200,
            "drift_status": "completed",
            "drift_job_id": "old-job",
        },
        linked_mmsi="",
    )
    _mock_session(monkeypatch, row)
    store = IntelStore(maxlen=1)  # empty deque: case is durable-only

    assert store.update_metadata(
        "intel:evicted-case",
        metadata={
            "drift_status": "computing",
            "drift_requested_at": "2026-11-02T00:00:00+00:00",
        },
    )
    assert row.meta["drift_status"] == "computing"
    assert row.meta["drift_job_id"] == "old-job"
    assert row.meta["location_uncertainty_m"] == 3200
    assert row.meta["coordinate_source"] == "media_ocr_consensus"

    assert store.update_metadata(
        "evicted-case",
        metadata={"drift_status": "completed", "drift_job_id": "new-job"},
        linked_mmsi="123456789",
    )
    assert row.meta["drift_status"] == "completed"
    assert row.meta["drift_job_id"] == "new-job"
    assert row.linked_mmsi == "123456789"


def test_evicted_case_metadata_update_rejects_missing_durable_row(monkeypatch):
    _mock_session(monkeypatch, None)
    store = IntelStore(maxlen=1)
    assert store.update_metadata(
        "intel:evicted-case", metadata={"drift_status": "completed"}
    ) is False


def test_evicted_case_metadata_merge_follows_prior_fifo_writes(monkeypatch):
    row = SimpleNamespace(meta={"source": "alarm_phone"}, linked_mmsi="")
    _mock_session(monkeypatch, row)
    store = IntelStore(maxlen=1)

    # Simulate an older asynchronous persistence callback that would otherwise
    # overwrite the drift transition if the fallback bypassed the FIFO queue.
    store._enqueue_persist(
        lambda: setattr(row, "meta", {"source": "alarm_phone", "evidence": "raw"})
    )
    assert store.update_metadata(
        "evicted-case", metadata={"drift_status": "completed"}
    )
    assert row.meta == {
        "source": "alarm_phone",
        "evidence": "raw",
        "drift_status": "completed",
    }
