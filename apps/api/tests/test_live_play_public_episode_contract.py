from datetime import datetime, timedelta, timezone

from core.intel.episode_lifecycle import public_episode_clock, visible_in_live


def test_ongoing_case_visible_in_both_surfaces_after_24_hours():
    now = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
    detected = now - timedelta(hours=53)
    item = {"incident_id": "episode:stable", "reported_at": detected.isoformat(), "incident_status": "active"}
    result = public_episode_clock(item, now=now)
    assert result["incident_id"] == item["incident_id"]
    assert result["play_eligible"] is True
    assert result["ongoing"] is True
    assert result["elapsed_seconds"] == 53 * 3600
    assert visible_in_live(detected_at=detected, status="active", now=now)


def test_closed_old_case_leaves_live_but_remains_play_eligible():
    now = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
    detected = now - timedelta(hours=53)
    item = {"reported_at": detected.isoformat(), "resolved_at": (detected + timedelta(hours=28)).isoformat(), "incident_status": "resolved"}
    result = public_episode_clock(item, now=now)
    assert result["play_eligible"] is True
    assert result["ongoing"] is False
    assert result["elapsed_seconds"] == 28 * 3600
    assert not visible_in_live(detected_at=detected, status="resolved", now=now)


def test_recent_closed_case_stays_live_until_24h():
    now = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
    detected = now - timedelta(hours=8)
    assert visible_in_live(detected_at=detected, status="resolved", now=now)
    assert not public_episode_clock({"reported_at": detected.isoformat(), "incident_status": "resolved"}, now=now)["play_eligible"]


def test_unknown_outcome_is_not_misrepresented_as_ongoing_distress():
    now = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
    detected = now - timedelta(days=90)
    result = public_episode_clock({"reported_at": detected.isoformat(), "incident_status": "outcome_unknown"}, now=now)
    assert result["play_eligible"] is True
    assert result["ongoing"] is False
    assert result["elapsed_seconds"] is None
    assert not visible_in_live(detected_at=detected, status="outcome_unknown", now=now)


def test_future_timestamp_is_not_an_active_clock_or_500_error():
    now = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
    detected = now + timedelta(minutes=10)
    result = public_episode_clock({"reported_at": detected.isoformat(), "incident_status": "active"}, now=now)
    assert result["clock_status"] == "future_timestamp"
    assert result["play_eligible"] is False
    assert result["ongoing"] is False
    assert result["elapsed_seconds"] is None


def test_closed_episode_projection_overrides_stale_open_analysis():
    from types import SimpleNamespace
    from core.api.routes.play import _episode_projection

    detected = datetime(2026, 11, 17, 10, tzinfo=timezone.utc)
    row = SimpleNamespace(
        episode_id="episode:stable", episode_family="gap_episode", status="resolved",
        behaviour_context={"analysis": {"resolution_state": "open", "publication_state": "published"}},
        independence_groups=["modality:ais"], verification_status="single_source_observed",
        start_at=detected, end_at=detected + timedelta(hours=53), updated_at=detected + timedelta(hours=54),
        geometry={"type": "Point", "coordinates": [12.0, 35.0]},
        subject_ids=["subj:mmsi:123456789"], observation_ids=["ais:origin", "ais:reappearance"],
        alternative_explanations=[],
    )
    projected = _episode_projection(row)
    assert projected["incident_status"] == "resolved"
    clock = public_episode_clock(projected, now=detected + timedelta(hours=60))
    assert clock["ongoing"] is False
    assert clock["elapsed_seconds"] == 53 * 3600
