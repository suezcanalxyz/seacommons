"""A producer's unverified lifecycle label must never close an AIS gap."""
from datetime import datetime, timedelta, timezone

from core.live.vessel_episodes import coalesce_security_vessel_episodes


T0 = datetime(2026, 11, 17, tzinfo=timezone.utc)


def signal(key, hour, *, validated=False, lifecycle='active'):
    props = {
        'id': key, 'mmsi': '123456789', 'anomaly_type': 'gap',
        'timestamp_utc': (T0 + timedelta(hours=hour)).isoformat(),
        'incident_lifecycle': lifecycle,
        'resolution_state': 'resolved' if lifecycle == 'resolved' else 'open',
        'source': 'AIS',
    }
    if validated:
        props.update(identity_validated=True, source_validated=True)
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [12.0, 35.0]}, 'properties': props}


def test_unverified_gap_resolution_does_not_split_or_close_episode():
    episodes = coalesce_security_vessel_episodes([
        signal('gap', 0), signal('unverified_fix', 1, lifecycle='resolved'), signal('next', 2),
    ])
    assert len(episodes) == 1
    props = episodes[0]['properties']
    assert props['episode_signal_ids'] == ['gap', 'unverified_fix', 'next']
    assert props['resolution_state'] == 'open'


def test_unverified_latest_fix_cannot_claim_resolved():
    episodes = coalesce_security_vessel_episodes([signal('gap', 0), signal('bad', 1, lifecycle='resolved')])
    props = episodes[0]['properties']
    assert props.get('incident_lifecycle') != 'resolved'
    assert props['resolution_state'] == 'open'


def test_validated_reappearance_splits_next_episode():
    episodes = coalesce_security_vessel_episodes([
        signal('gap', 0), signal('verified', 1, validated=True, lifecycle='resolved'), signal('new', 2),
    ])
    assert len(episodes) == 2
    assert episodes[0]['properties']['episode_signal_ids'] == ['gap', 'verified']
    assert episodes[1]['properties']['episode_signal_ids'] == ['new']


def test_unverified_resolution_metadata_cannot_close_gap_without_open_peer():
    episodes = coalesce_security_vessel_episodes([signal('unverified_only', 0, lifecycle='resolved')])
    assert episodes[0]['properties']['resolution_state'] == 'open'


def test_validated_old_alert_cannot_authenticate_later_unverified_normal_track():
    original = signal('nuc', 0, validated=True)
    original['properties']['anomaly_type'] = 'not_under_command'
    episodes = coalesce_security_vessel_episodes([original], track_history={
        '123456789': [{'lon': 12.1, 'lat': 35.1, 'ts': (T0 + timedelta(hours=2)).isoformat(), 'nav_status': 0}],
    })
    assert episodes[0]['properties'].get('incident_lifecycle') != 'resolved'
    assert episodes[0]['properties']['resolution_state'] == 'open'


def test_safety_episode_requires_explicit_validated_closure_signal():
    original = signal('nuc', 0)
    original['properties']['anomaly_type'] = 'not_under_command'
    closing = signal('nuc-resolved', 1, validated=True, lifecycle='resolved')
    closing['properties']['anomaly_type'] = 'not_under_command'
    episodes = coalesce_security_vessel_episodes([original, closing])
    assert len(episodes) == 1
    assert episodes[0]['properties']['incident_lifecycle'] == 'resolved'
    assert episodes[0]['properties']['resolution_state'] == 'resolved'
