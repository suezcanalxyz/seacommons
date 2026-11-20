from core.mda.track_discontinuity import (
    analyze_track_discontinuities,
    track_feature_collection,
)


def fix(ts, lat, lon, source="ais"):
    return {"ts": ts, "lat": lat, "lon": lon, "source": source}


def test_xt_exploration_jump_is_physically_impossible_not_a_port_call():
    result = analyze_track_discontinuities([
        fix("2026-11-18T10:21:33Z", 37.20875, 15.18848),
        fix("2026-11-18T10:32:44Z", 36.47340, 14.77830),
    ])
    assert len(result["segments"]) == 1
    segment = result["segments"][0]
    assert segment["elapsed_seconds"] == 671
    assert 85 < segment["distance_km"] < 95
    assert 240 < segment["implied_speed_knots"] < 290
    assert segment["classification"] == "physically_implausible_jump"
    assert segment["is_observed_route"] is False
    assert segment["port_call"] == "not_established"
    assert segment["spoofing"] == "not_established"


def test_long_interval_does_not_assert_sailed_route_or_port_visit():
    result = analyze_track_discontinuities([
        fix("2026-11-18T14:35:17+00:00", 36.47340, 14.77830),
        fix("2026-11-18T17:12:09+00:00", 37.20875, 15.18848),
    ])
    s = result["segments"][0]
    assert s["elapsed_seconds"] == 9412
    assert s["classification"] == "unobserved_interval"
    assert s["is_observed_route"] is False
    assert s["port_call"] == "not_established"


def test_rejects_out_of_order_ambiguous_and_invalid_fix_timestamps():
    result = analyze_track_discontinuities([
        fix("2026-11-18T10:32:44Z", 36.4734, 14.7783),
        fix("2026-11-18T10:21:33Z", 37.20875, 15.18848),
        fix("2026-11-18T11:00:00", 0, 0),  # no timezone
        fix("2026-11-18T12:00:00Z", 95, 0),  # invalid latitude
    ])
    assert result["valid_fix_count"] == 2
    assert result["out_of_order_pairs"] == 1
    assert result["segments"] == []


def test_dense_valid_route_has_no_fabricated_gap():
    result = analyze_track_discontinuities([
        fix("2026-11-18T10:00:00Z", 36.47, 14.77),
        fix("2026-11-18T10:10:00Z", 36.49, 14.79),
        fix("2026-11-18T10:20:00Z", 36.51, 14.81),
    ])
    assert result["total_flagged_segments"] == 0


def test_public_track_never_draws_across_impossible_jump_or_gap():
    collection = track_feature_collection([
        fix("2026-11-18T10:21:33Z", 37.20875, 15.18848),
        fix("2026-11-18T10:32:44Z", 36.47340, 14.77830),
        fix("2026-11-18T10:40:44Z", 36.49340, 14.79830),
        fix("2026-11-18T12:40:44Z", 36.51340, 14.81830),
    ])

    assert len(collection["features"]) == 1
    assert collection["features"][0]["geometry"]["coordinates"] == [
        [14.77830, 36.47340],
        [14.79830, 36.49340],
    ]
    assert collection["features"][0]["properties"]["is_observed_route"] is False
