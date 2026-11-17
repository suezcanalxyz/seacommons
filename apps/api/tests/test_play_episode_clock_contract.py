from datetime import datetime, timedelta, timezone

from core.intel.episode_lifecycle import PLAY_DELAY, elapsed_seconds, play_eligible


def test_play_clock_is_independent_of_case_resolution():
    detected = datetime(2026, 11, 17, 9, tzinfo=timezone.utc)
    now = detected + timedelta(hours=27)
    assert PLAY_DELAY == timedelta(hours=24)
    assert play_eligible(detected_at=detected, now=now)
    assert elapsed_seconds(started_at=detected, ended_at=None, now=now) == 27 * 3600
    assert elapsed_seconds(started_at=detected, ended_at=detected + timedelta(hours=25), now=now) == 25 * 3600
