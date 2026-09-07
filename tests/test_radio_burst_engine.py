from datetime import datetime, timedelta, timezone

from core.radio.provider import RadioObservation


def _obs(receiver: str, seconds: int, dbm: float) -> RadioObservation:
    return RadioObservation(
        receiver_id=receiver, provider="kiwisdr", physical_lineage=receiver,
        frequency_hz=2_187_500, mode="usb",
        observed_at=datetime(2026, 9, 7, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        signal_dbm=dbm, source_terms="allowed", session_id="s",
    )


def test_detector_emits_one_burst_only_after_signal_returns_to_baseline():
    from core.radio.burst import RadioBurstDetector

    detector = RadioBurstDetector(trigger_delta_db=8.0, release_delta_db=3.0, min_samples=2)
    assert detector.ingest(_obs("rx1", 0, -100)) == ()
    assert detector.ingest(_obs("rx1", 1, -100)) == ()
    assert detector.ingest(_obs("rx1", 2, -87)) == ()
    assert detector.ingest(_obs("rx1", 3, -85)) == ()
    bursts = detector.ingest(_obs("rx1", 4, -99))
    assert len(bursts) == 1
    burst = bursts[0]
    assert burst.sample_count == 2
    assert burst.peak_signal_db == -85
    assert burst.physical_lineage == "rx1"


def test_short_single_sample_spike_is_not_promoted_to_burst():
    from core.radio.burst import RadioBurstDetector

    detector = RadioBurstDetector(trigger_delta_db=8.0, release_delta_db=3.0, min_samples=2)
    detector.ingest(_obs("rx1", 0, -100))
    detector.ingest(_obs("rx1", 1, -86))
    assert detector.ingest(_obs("rx1", 2, -100)) == ()


def test_multi_receiver_correlation_counts_independent_lineages_only():
    from core.radio.burst import RadioBurst, correlate_bursts

    t0 = datetime(2026, 9, 7, tzinfo=timezone.utc)
    a = RadioBurst("a", "rx-a", 2_187_500, t0, t0 + timedelta(seconds=2), 3, -82, -86)
    b = RadioBurst("b", "rx-b", 2_187_500, t0 + timedelta(seconds=1), t0 + timedelta(seconds=3), 4, -79, -84)
    duplicate = RadioBurst("c", "rx-a", 2_187_500, t0 + timedelta(seconds=1), t0 + timedelta(seconds=2), 2, -80, -83)
    event = correlate_bursts((a, b, duplicate), window_seconds=5)
    assert event.independent_receivers == 2
    assert set(event.physical_lineages) == {"rx-a", "rx-b"}
    assert 0.0 < event.confidence <= 1.0
