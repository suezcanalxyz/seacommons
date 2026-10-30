# SPDX-License-Identifier: AGPL-3.0-or-later
"""Replay and contradiction regressions for SAR episode corroboration.

Pure tests: no database, provider network, or production writes.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.intel.satellite_observation import (
    _merged_provenance, _reconcile_association, _reconcile_observation_replay,
)


def _row(status=None, episode=None, evidence="contextual"):
    return SimpleNamespace(
        association_status=status, episode_id=episode, evidence_status=evidence,
    )


@pytest.mark.parametrize(
    "old_status,old_episode,old_evidence,new_status,new_episode,new_evidence,expected",
    [
        # Initial contextual candidate can be promoted on exact provider match.
        ("unmatched_candidate", None, "contextual", "strong", "episode:a", "associated",
         ("strong", "episode:a", "associated")),
        # Replaying an old contextual detection cannot strip a strong link.
        ("strong", "episode:a", "associated", "unmatched_candidate", None, "contextual",
         ("strong", "episode:a", "associated")),
        # Same-episode replay is idempotent.
        ("strong", "episode:a", "associated", "strong", "episode:a", "associated",
         ("strong", "episode:a", "associated")),
        # A conflicting episode must never overwrite the previously linked episode.
        ("strong", "episode:a", "associated", "strong", "episode:b", "associated",
         ("conflict", None, "contextual")),
        # Explicit conflicting provider identity revokes automatic corroboration.
        ("strong", "episode:a", "associated", "conflict", None, "contextual",
         ("conflict", None, "contextual")),
        # A subsequent automatic replay cannot silently clear a conflict.
        ("conflict", None, "contextual", "strong", "episode:a", "associated",
         ("conflict", None, "contextual")),
        # Unmatched evidence cannot attach an episode just because one was supplied.
        ("unmatched_candidate", None, "contextual", "unmatched_candidate", "episode:a",
         "associated", ("unmatched_candidate", None, "contextual")),
        # A routine quicklook without a match retains null association fields.
        (None, None, "contextual", None, None, "contextual",
         (None, None, "contextual")),
        # Strong identity requires an actual canonical episode identifier.
        ("unmatched_candidate", None, "contextual", "strong", None, "associated",
         ("provider_matched_unresolved", None, "contextual")),
    ],
)
def test_replay_never_fabricates_or_silently_changes_episode(
    old_status, old_episode, old_evidence, new_status, new_episode, new_evidence, expected,
):
    existing = _row(old_status, old_episode, old_evidence)
    incoming = _row(new_status, new_episode, new_evidence)
    _reconcile_association(existing, incoming)
    assert (
        existing.association_status,
        existing.episode_id,
        existing.evidence_status,
    ) == expected


def test_nested_case_target_is_deduplicated_without_hash_error():
    """Provider JSON may contain nested target attributes, not just scalars."""
    target = {
        "role": {"kind": "drift", "labels": ["primary", "secondary"]},
        "lat": [35.5, 35.6], "lon": 14.2, "at": {"utc": "2026-10-30T00:00:00Z"},
        "search_direction": ["forward"], "drift_id": "drift:1",
        "trajectory_index": {"index": 0}, "note": "first source",
    }
    replay = dict(target, note="second source")
    merged = _merged_provenance(
        {"case_targets": [target]},
        {"case_targets": [replay]},
    )
    assert merged["case_targets"] == [target]


def test_malformed_case_target_containers_do_not_abort_ingestion():
    merged = _merged_provenance(
        {"case_targets": {"role": "invalid"}, "source": "existing"},
        {"case_targets": [{"role": "valid", "lat": 35.5}, "bad", None]},
    )
    assert merged["source"] == "existing"
    assert merged["case_targets"] == [{"role": "valid", "lat": 35.5}]
    assert _merged_provenance([], {"case_targets": []}) == {}
    assert _merged_provenance({"source": "kept"}, ["malformed"]) == {"source": "kept"}


def test_scalar_case_target_replay_keeps_existing_identity_fields():
    target = {"role": "last_seen", "lat": 35.5, "lon": 14.2, "at": "2026-10-30T00:00:00Z"}
    merged = _merged_provenance(
        {"case_targets": [target], "provider": "original"},
        {"case_targets": [dict(target, extra="new")], "provider": "latest"},
    )
    assert merged["provider"] == "latest"
    assert merged["case_targets"] == [target]


def test_contextual_replay_preserves_strong_match_provenance_and_merges_targets():
    existing = _row("strong", "episode:a", "associated")
    existing.provenance = {
        "association_method": "provider_exact_mmsi",
        "provider_matched": True,
        "case_targets": [{"role": "last_seen", "lat": 35.5}],
    }
    incoming = _row("unmatched_candidate", None, "contextual")
    incoming.provenance = {
        "association_method": "none", "provider_matched": False,
        "case_targets": [{"role": "drift", "lat": 35.6}],
    }
    _reconcile_observation_replay(existing, incoming)
    assert (existing.association_status, existing.episode_id, existing.evidence_status) == (
        "strong", "episode:a", "associated",
    )
    assert existing.provenance["association_method"] == "provider_exact_mmsi"
    assert existing.provenance["provider_matched"] is True
    assert len(existing.provenance["case_targets"]) == 2


def test_conflicting_episode_records_quarantine_reason_in_provenance():
    existing = _row("strong", "episode:a", "associated")
    existing.provenance = {"association_method": "provider_exact_mmsi"}
    incoming = _row("strong", "episode:b", "associated")
    incoming.provenance = {"association_method": "provider_exact_mmsi"}
    _reconcile_observation_replay(existing, incoming)
    assert (existing.association_status, existing.episode_id, existing.evidence_status) == (
        "conflict", None, "contextual",
    )
    assert existing.provenance["association_method"] == "conflict_requires_review"
    assert existing.provenance["association_conflict"] == {
        "previous_status": "strong",
        "previous_episode_id": "episode:a",
        "incoming_status": "strong",
        "incoming_episode_id": "episode:b",
    }


def test_conflict_reason_survives_automatic_replay():
    existing = _row("strong", "episode:a", "associated")
    existing.provenance = {"association_method": "provider_exact_mmsi"}
    incoming = _row("strong", "episode:b", "associated")
    incoming.provenance = {"association_method": "provider_exact_mmsi"}
    _reconcile_observation_replay(existing, incoming)
    reason = dict(existing.provenance["association_conflict"])

    later = _row("strong", "episode:c", "associated")
    later.provenance = {
        "association_method": "provider_exact_mmsi",
        "association_conflict": {"previous_episode_id": "forged"},
    }
    _reconcile_observation_replay(existing, later)
    assert existing.association_status == "conflict"
    assert existing.episode_id is None
    assert existing.evidence_status == "contextual"
    assert existing.provenance["association_method"] == "conflict_requires_review"
    assert existing.provenance["association_conflict"] == reason
