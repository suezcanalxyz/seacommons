from datetime import datetime, timezone

from core.intel.attack_pipeline import build_attack_context_feature


def _report(obs_id, group, *, at="2026-10-28T10:30:00+00:00", lat=None, lon=None):
    return {
        "observation_id": obs_id,
        "observed_at": at,
        "lat": lat,
        "lon": lon,
        "provenance": {
            "mmsi": "636019532",
            "imo": "9348625",
            "independence_group": group,
            "report_kind": "possible_maritime_attack",
        },
    }


def test_report_to_ais_context_is_review_only_and_uses_publication_time():
    feature = build_attack_context_feature(
        [_report("obs-a", "official")],
        [{
            "mmsi": "636019532",
            "ts": "2026-10-28T10:29:00+00:00",
            "lat": 43.2659,
            "lon": 28.8149,
        }],
    )
    assert feature is not None
    props = feature["properties"]
    assert props["episode_family"] == "reported_attack_context"
    assert props["verification_status"] == "single_source_observed"
    assert props["publication_state"] == "internal"
    assert props["behaviour_context"]["attack_confirmed"] is False
    assert props["behaviour_context"]["publication_allowed"] is False
    assert props["behaviour_context"]["requires_operator_review"] is True
    assert props["behaviour_context"]["report_time_basis"] == "rss_publication_time_not_attack_occurrence_time"
    assert props["behaviour_context"]["track_context_fix_count"] == 1
    assert props["behaviour_context"]["closest_track_to_publication_minutes"] == 1.0


def test_two_independent_reports_mark_multi_source_observed_not_confirmed():
    feature = build_attack_context_feature(
        [
            _report("obs-a", "official"),
            _report("obs-b", "independent_media", at="2026-10-28T10:45:00+00:00"),
        ],
        [],
    )
    assert feature is not None
    props = feature["properties"]
    assert props["verification_status"] == "multi_source_observed"
    assert set(props["independence_groups"]) == {"official", "independent_media"}
    assert props["behaviour_context"]["attack_confirmed"] is False


def test_explicit_report_coordinate_can_be_context_geometry_without_attack_claim():
    feature = build_attack_context_feature(
        [_report("obs-a", "official", lat=43.26, lon=28.81)],
        [],
    )
    assert feature is not None
    assert feature["geometry"] == {"type": "Point", "coordinates": [28.81, 43.26]}
    assert feature["properties"]["behaviour_context"]["explicit_report_coordinates"] is True
    assert feature["properties"]["publication_state"] == "internal"


def test_report_without_vessel_identity_cannot_create_attack_context():
    row = _report("obs-a", "official")
    row["provenance"]["mmsi"] = None
    row["provenance"]["imo"] = None
    assert build_attack_context_feature([row], []) is None
