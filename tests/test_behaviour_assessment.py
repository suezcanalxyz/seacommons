from datetime import datetime, timedelta, timezone

from core.mda.behavioural_baseline import BehaviouralBaseline


def _baseline():
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    end = datetime(2026, 8, 31, tzinfo=timezone.utc)
    return BehaviouralBaseline(
        baseline_id="vbl:test", subject_id="subj:imo:9848388", primary_mmsi="229113000", primary_imo="9848388",
        window_start=start, window_end=end, sample_count=200, history_days=30,
        route_model={"kind": "grid_corridor", "cell_deg": 0.05, "cells": [[35.90, 14.30], [36.00, 14.40]], "sample_count": 200},
        speed_model={"sample_count": 180, "p05": 12.0, "p25": 15.0, "p50": 17.0, "p75": 19.0, "p95": 22.0},
        port_model={"call_count": 20, "recurrent_ports": ["Malta", "Gozo"], "recurrent_pairs": [["Malta", "Gozo"], ["Gozo", "Malta"]]},
        silence_model={"sample_count": 199, "p50_seconds": 120.0, "p95_seconds": 600.0, "max_seconds": 900.0},
        evidence_fingerprint="abc",
    )


def test_assessment_fails_closed_without_baseline():
    from core.mda.behaviour_assessment import assess_behaviour

    result = assess_behaviour([], None, evaluated_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert result.status == "insufficient_history"
    assert result.reason_codes == ("INSUFFICIENT_HISTORY",)


def test_recurrent_corridor_and_normal_gap_are_expected():
    from core.mda.behaviour_assessment import assess_behaviour

    t0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    track = [
        {"ts": t0.isoformat(), "lat": 35.91, "lon": 14.31, "sog": 17.0, "port": "Malta"},
        {"ts": (t0 + timedelta(minutes=5)).isoformat(), "lat": 35.99, "lon": 14.39, "sog": 18.0, "port": "Gozo"},
    ]
    result = assess_behaviour(track, _baseline(), evaluated_at=t0 + timedelta(minutes=5))
    assert result.status == "expected"
    assert result.reason_codes == ()
    assert result.dimensions["route"]["status"] == "expected"
    assert result.dimensions["silence"]["status"] == "expected"


def test_route_deviation_and_long_silence_are_unusual():
    from core.mda.behaviour_assessment import assess_behaviour

    t0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    track = [
        {"ts": t0.isoformat(), "lat": 35.90, "lon": 14.30, "sog": 17.0},
        {"ts": (t0 + timedelta(hours=2)).isoformat(), "lat": 35.20, "lon": 13.20, "sog": 30.0},
    ]
    result = assess_behaviour(track, _baseline(), evaluated_at=t0 + timedelta(hours=2))
    assert result.status == "unusual"
    assert "ROUTE_DEVIATION" in result.reason_codes
    assert "UNUSUAL_AIS_SILENCE" in result.reason_codes
    assert "UNUSUAL_SPEED_PROFILE" in result.reason_codes
    assert result.dimensions["route"]["distance_nm"] > result.dimensions["route"]["threshold_nm"]
