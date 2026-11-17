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
