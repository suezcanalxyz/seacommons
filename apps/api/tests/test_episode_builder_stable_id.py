"""A historical backfill must not renumber unrelated episode dossiers."""
from datetime import datetime, timedelta, timezone

from core.live.episode_builder import EpisodeSignal, build_episodes

T0 = datetime(2026, 11, 17, tzinfo=timezone.utc)


def signal(key, days):
    return EpisodeSignal(
        signal_id=key, subject_ids=("subj:mmsi:123456789",),
        family="gap_episode", observed_at=T0 + timedelta(days=days),
        lat=35.0, lon=12.0,
    )


def test_backfilled_older_unrelated_anomaly_does_not_shift_episode_id():
    initial = build_episodes([signal("first", 10), signal("followup", 11), signal("later", 20)])
    assert len(initial) == 2
    updated = build_episodes([signal("old", 0), signal("first", 10), signal("followup", 11), signal("later", 20)])
    assert len(updated) == 3
    assert [e.episode_id for e in initial] == [e.episode_id for e in updated[1:]]
    assert updated[1].signal_ids == ["first", "followup"]


def test_shuffled_input_keeps_stable_episode_ids():
    records = [signal("a", 0), signal("b", 1), signal("c", 10)]
    assert [e.episode_id for e in build_episodes(records)] == [e.episode_id for e in build_episodes(list(reversed(records)))]


def test_adding_followup_does_not_change_existing_id():
    first = build_episodes([signal("a", 0)])[0]
    updated = build_episodes([signal("a", 0), signal("b", 1)])[0]
    assert first.episode_id == updated.episode_id
