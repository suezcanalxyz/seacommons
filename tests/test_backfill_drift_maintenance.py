# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M8: auditable Drift-row maintenance command."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.db.models import DriftResultDB
from core.db.session import session_scope
from core.intel.backfill_drift_maintenance import find_candidates, run


def _insert(
    drift_id, *, status="computing", created_at=None,
    trajectory=None, cone_6h=None, cone_12h=None, cone_24h=None,
):
    with session_scope() as db:
        db.add(DriftResultDB(
            drift_id=drift_id, event_id=f"intel:{drift_id}", domain="ocean_sar",
            lat=35.5, lon=14.1, status=status,
            created_at=created_at or datetime.now(timezone.utc).replace(tzinfo=None),
            trajectory=trajectory, cone_6h=cone_6h, cone_12h=cone_12h, cone_24h=cone_24h,
            metadata_json={},
        ))


_GEOMETRY = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[14.0, 35.0]]}}


def test_a_recent_computing_job_is_not_stuck():
    _insert("recent-computing", status="computing")
    candidates = find_candidates()
    assert not any(c.drift_id == "recent-computing" for c in candidates)


def test_a_computing_job_older_than_the_threshold_is_stuck():
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)
    _insert("old-computing", status="computing", created_at=old)
    candidates = find_candidates()
    match = next(c for c in candidates if c.drift_id == "old-computing")
    assert match.reason == "stuck"


def test_a_completed_job_with_full_geometry_is_healthy():
    _insert(
        "healthy", status="completed",
        trajectory=_GEOMETRY, cone_6h=_GEOMETRY, cone_12h=_GEOMETRY, cone_24h=_GEOMETRY,
    )
    candidates = find_candidates()
    assert not any(c.drift_id == "healthy" for c in candidates)


def test_a_completed_job_missing_geometry_is_invalid():
    _insert("broken", status="completed", trajectory=_GEOMETRY)  # missing the cones
    candidates = find_candidates()
    match = next(c for c in candidates if c.drift_id == "broken")
    assert match.reason == "invalid"


def test_dry_run_counts_but_writes_nothing():
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)
    _insert("stuck-1", status="computing", created_at=old)

    report = run(apply=False)
    assert report["stuck"] == 1
    assert report["fixed"] == 0

    with session_scope() as db:
        row = db.get(DriftResultDB, "stuck-1")
        assert row.status == "computing"  # untouched


def test_apply_marks_candidates_failed_and_preserves_the_row():
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)
    _insert("stuck-2", status="computing", created_at=old)

    report = run(apply=True)
    assert report["fixed"] == 1

    with session_scope() as db:
        row = db.get(DriftResultDB, "stuck-2")
        assert row.status == "failed"
        assert row.lat == 35.5 and row.lon == 14.1  # original data preserved
        assert row.metadata_json["maintenance_log"][0]["reason"] == "stuck"


def test_rerunning_after_apply_is_idempotent_finds_nothing_more():
    """docs/fixes.md M8: restartable and idempotent."""
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)
    _insert("stuck-3", status="computing", created_at=old)

    first = run(apply=True)
    assert first["fixed"] == 1

    second = run(apply=True)
    assert second["scanned"] == 0
    assert second["fixed"] == 0


def test_maintenance_never_deletes_a_row():
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)
    _insert("stuck-4", status="computing", created_at=old)
    run(apply=True)
    with session_scope() as db:
        assert db.get(DriftResultDB, "stuck-4") is not None
