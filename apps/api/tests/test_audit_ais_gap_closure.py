"""The read-only provenance audit must not mistake flags for proof."""
from scripts.audit_ais_gap_closure import summarize_gap_attestations


def test_missing_attestation_on_closed_gap_is_flagged():
    report = summarize_gap_attestations([
        ('a', {'anomaly_type': 'gap', 'resolution_state': 'resolved'}),
        ('b', {'anomaly_type': 'long_gap', 'resolution_state': 'open'}),
        ('c', {'anomaly_type': 'other', 'resolution_state': 'resolved'}),
    ])
    assert report['gap_events'] == 2
    assert report['closed_without_attestation'] == 1
    assert report['missing_attestation'] == 2


def test_attestation_field_completeness_is_not_authentication():
    report = summarize_gap_attestations([
        ('a', {'anomaly_type': 'gap', 'resolution_state': 'resolved', 'reappearance_validation': {
            'identity_validated': True, 'source_validated': True, 'track_id': '1',
            'mmsi': '123', 'source': 'feed', 'observed_at': '2026-11-18T00:00:00+00:00',
        }}),
        ('b', {'anomaly_type': 'gap', 'resolution_state': 'resolved', 'reappearance_validation': {
            'identity_validated': True, 'source_validated': False,
        }}),
    ])
    assert report['attestation_fields_complete'] == 1
    assert report['closed_with_incomplete_attestation'] == 1
