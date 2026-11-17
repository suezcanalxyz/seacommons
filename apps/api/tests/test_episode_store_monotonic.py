"""Persistence must survive rolling LIVE snapshots without losing evidence."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from core.intel.episode_store import merge_episode_values


START = datetime(2026, 11, 17, 10, tzinfo=timezone.utc)


def current():
    return SimpleNamespace(
        episode_family="gap_episode", subject_ids=["subj:mmsi:123456789"],
        start_at=START, end_at=START + timedelta(hours=26),
        geometry={"type": "Point", "coordinates": [12.0, 34.0]},
        observation_ids=["ais:first", "ais:second"], feature_ids=["feature:first"],
        independence_groups=["modality:ais"], alternative_explanations=["coverage"],
        behaviour_context={"analysis": {"publication_state": "published"}, "case_opening": {"reason_codes": ["GAP"]}},
        verification_status="single_source_multi_indicator", method_version="maritime-episode-v1", status="active",
    )


def incoming(*, hours, status="active"):
    return dict(
        start_at=START + timedelta(hours=1), end_at=START + timedelta(hours=hours),
        observation_ids=["ais:second", "ais:third"], feature_ids=["feature:second"],
        independence_groups=["modality:ais"], alternative_explanations=["delayed_feed"],
        behaviour_context={"analysis": {"publication_state": "internal"}},
        verification_status="single_source_observed", method_version="maritime-episode-v1", status=status,
        geometry={"type": "Point", "coordinates": [13.0, 35.0]},
    )


def test_incremental_update_preserves_first_detection_and_all_observations():
    row = merge_episode_values(current(), incoming(hours=53))
    assert row["start_at"] == START
    assert row["end_at"] == START + timedelta(hours=53)
    assert row["observation_ids"] == ["ais:first", "ais:second", "ais:third"]
    assert row["feature_ids"] == ["feature:first", "feature:second"]
    assert row["alternative_explanations"] == ["coverage", "delayed_feed"]
    assert row["behaviour_context"]["case_opening"]["reason_codes"] == ["GAP"]
    # Fresh explicit privacy-policy updates must still be honoured.
    assert row["behaviour_context"]["analysis"]["publication_state"] == "internal"


def test_out_of_order_snapshot_cannot_rewind_position_or_publication_decision():
    row = merge_episode_values(current(), incoming(hours=12, status="resolved"))
    assert row["end_at"] == START + timedelta(hours=26)
    assert row["geometry"]["coordinates"] == [12.0, 34.0]
    assert row["status"] == "active"
    assert row["behaviour_context"]["analysis"]["publication_state"] == "published"
    assert "ais:third" in row["observation_ids"]


def test_closed_episode_does_not_silently_reopen():
    previous = current()
    previous.status = "resolved"
    row = merge_episode_values(previous, incoming(hours=53, status="active"))
    assert row["status"] == "resolved"


def test_repeat_is_idempotent_for_evidence_and_fingerprint():
    previous = current()
    first = merge_episode_values(previous, incoming(hours=53))
    for field, value in first.items():
        setattr(previous, field, value)
    second = merge_episode_values(previous, incoming(hours=53))
    assert first["observation_ids"] == second["observation_ids"]
    assert first["evidence_fingerprint"] == second["evidence_fingerprint"]
