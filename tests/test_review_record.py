from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone

import pytest


def _review(**overrides):
    from core.review.contracts import ReviewRecord

    values = {
        "target_type": "humanitarian_resolution",
        "target_id": "resolution:abc123",
        "target_version": "humanitarian-resolution-v1",
        "evidence_snapshot_id": "xev:0123456789abcdef",
        "decision": "approve",
        "rationale": "Evidence reviewed against the attached immutable snapshot.",
        "actor": "operator:alice",
        "reviewed_at": datetime(2026, 9, 6, 20, 45, tzinfo=timezone.utc),
        "requested_transition": "resolved",
    }
    values.update(overrides)
    return ReviewRecord(**values)


def test_review_record_is_frozen_normalized_and_deterministic():
    first = _review(actor=" Operator Alice ")
    second = _review(actor="operator_alice")
    assert first.review_id == second.review_id
    assert first.actor == "operator_alice"
    with pytest.raises(FrozenInstanceError):
        first.rationale = "changed"  # type: ignore[misc]


def test_exact_replay_is_same_review_identity_but_changed_decision_is_new_identity():
    first = _review()
    second = _review()
    rejected = _review(decision="reject", requested_transition=None)
    assert first.review_id == second.review_id
    assert rejected.review_id != first.review_id


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"target_type": "magic"}, "target_type"),
        ({"target_id": ""}, "target_id"),
        ({"target_version": ""}, "target_version"),
        ({"evidence_snapshot_id": ""}, "evidence_snapshot_id"),
        ({"decision": "publish"}, "decision"),
        ({"rationale": ""}, "rationale"),
        ({"actor": ""}, "actor"),
        ({"reviewed_at": datetime(2026, 9, 6, 20, 45)}, "timezone"),
    ],
)
def test_review_record_values_fail_closed(overrides, match):
    with pytest.raises(ValueError, match=match):
        _review(**overrides)


def test_approve_requires_requested_transition_but_other_decisions_do_not():
    with pytest.raises(ValueError, match="requested_transition"):
        _review(decision="approve", requested_transition=None)
    assert _review(decision="reject", requested_transition=None).requested_transition is None
    assert _review(decision="needs_more_evidence", requested_transition=None).requested_transition is None


def test_rationale_is_bounded_and_transition_remains_closed_vocabulary():
    record = _review(rationale="x" * 5000, requested_transition="resolved")
    assert len(record.rationale) == 2000
    with pytest.raises(ValueError, match="requested_transition"):
        _review(requested_transition="x" * 200)


def test_contract_contains_no_direct_truth_or_raw_evidence_fields():
    names = {field.name for field in fields(type(_review()))}
    for forbidden in (
        "lifecycle", "publication_status", "published", "incident_status",
        "raw_evidence", "raw_payload", "mmsi", "imo", "callsign", "transcript",
    ):
        assert forbidden not in names


def test_snapshot_reference_cannot_embed_sensitive_or_raw_evidence_material():
    for bad in (
        "raw:audio-bytes-here",
        "mmsi:247123456",
        "imo:1234567",
        "callsign:ABC123",
        "transcript:MAYDAY MAYDAY",
    ):
        with pytest.raises(ValueError, match="evidence_snapshot_id"):
            _review(evidence_snapshot_id=bad)


def test_target_specific_requested_transition_vocabulary_is_fail_closed():
    assert _review(requested_transition="resolved").requested_transition == "resolved"
    assert _review(target_type="maritime_hypothesis", target_id="hyp:v1:gap:1", target_version="candidate", requested_transition="collecting").requested_transition == "collecting"
    with pytest.raises(ValueError, match="requested_transition"):
        _review(requested_transition="published")
