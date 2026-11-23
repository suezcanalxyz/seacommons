# SPDX-License-Identifier: AGPL-3.0-or-later
"""P0 AIS retention gate: env approvals cannot bypass code-level fail-closed."""
from core.vessels import track_store


def test_retention_env_cannot_enable_unreviewed_deletion(monkeypatch):
    monkeypatch.setenv("AIS_PRUNE_APPROVED", "true")
    monkeypatch.setenv("AIS_RETENTION_POLICY_ID", "synthetic-test-only")
    monkeypatch.setattr(track_store, "_RETENTION_RELEASE_AUTHORIZED", False)
    # No DB or object-store credentials: prune must exit before touching either.
    store = track_store.TrackStore.__new__(track_store.TrackStore)
    assert store.prune(older_than_days=60) == 0
