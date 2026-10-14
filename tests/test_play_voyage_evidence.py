"""Canonical PLAY dossier AIS reconstruction, no secondary store."""
from datetime import datetime, timezone
from unittest.mock import patch
from core.api.routes.play import _canonical_voyage_evidence


def test_gap_reconstruction_uses_existing_track_store():
    track = [
        {"ts": datetime(2026, 10, 12, 8, tzinfo=timezone.utc), "lat": 37.0, "lon": 15.0, "sog": 8, "source": "aisstream"},
        {"ts": datetime(2026, 10, 12, 11, tzinfo=timezone.utc), "lat": 37.4, "lon": 15.8, "sog": 7, "source": "aisstream"},
    ]
    with patch('core.vessels.track_store.track_store.track', return_value=track) as read, patch('core.api.routes.mda._derive_recent_port_calls', return_value=[]):
        output = _canonical_voyage_evidence({'247123456'}, start_at='2026-10-12T08:00:00Z', end_at='2026-10-12T11:00:00Z')
    vessel = output['vessels'][0]
    assert read.call_count == 1
    assert vessel['observed_fix_count'] == 2
    assert vessel['observed_gaps'][0]['duration_min'] == 180
    assert 'not the observed route' in vessel['limits']
    assert vessel['track_line']['type'] == 'LineString'


def test_no_mmsi_no_invented_voyage():
    output = _canonical_voyage_evidence({'piracy', 'unknown'}, start_at='2026-10-12T08:00:00Z', end_at=None)
    assert output['vessels'] == []
    assert output['status'] == 'no_retained_ais_fixes'


def test_malformed_position_excluded():
    track = [{"ts": datetime(2026, 10, 12, tzinfo=timezone.utc), "lat": 500, "lon": 15}]
    with patch('core.vessels.track_store.track_store.track', return_value=track), patch('core.api.routes.mda._derive_recent_port_calls', return_value=[]):
        output = _canonical_voyage_evidence({'247123456'}, start_at='2026-10-12T08:00:00Z', end_at=None)
    assert output['vessels'][0]['observed_fix_count'] == 0
