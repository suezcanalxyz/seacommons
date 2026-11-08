"""Fail-closed AIS retention release regression guard (#335).

A production environment variable must never be enough to delete AIS evidence.
This test intentionally does not connect to PostgreSQL or object storage.
"""
from __future__ import annotations

from core.vessels import track_store


def test_retention_release_gate_is_hard_disabled(monkeypatch):
    """Prevent an accidental release before the canonical restore drill passes."""
    assert track_store._RETENTION_RELEASE_AUTHORIZED is False


def test_prune_refuses_even_with_all_environment_approvals(monkeypatch):
    """Adversarial operator configuration must not bypass release authorization."""
    monkeypatch.setenv("AIS_PRUNE_APPROVED", "true")
    monkeypatch.setenv("AIS_RETENTION_POLICY_ID", "test-policy-do-not-release")
    monkeypatch.setenv("OBJECT_STORAGE_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY", "test")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_KEY", "test")
    store = track_store.TrackStore()
    assert store.prune(older_than_days=1) == 0
