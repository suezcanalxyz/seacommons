from core.intel.assessment import build_assessment


def test_position_integrity_assessment_uses_trigger_metrics():
    result = build_assessment({
        "type": "ais_anomaly",
        "anomaly_type": "position_jump",
        "maritime_domain": "grey_zone",
        "linked_mmsi": "372497000",
        "movement_evidence": {
            "distance_km": 625.4,
            "time_delta_s": 660,
            "implied_speed_kn": 1840.0,
        },
        "independent_source_count": 1,
    })
    assert result is not None
    assert "625.4 km" in result.interpretation
    assert "1840 kn" in result.interpretation
    assert "not proof" in result.caveats[0].lower()


def test_public_categories_get_distinct_assessments():
    cases = [
        ({"type": "ais_rendezvous", "anomaly_type": "rendezvous", "maritime_domain": "grey_zone"}, "rendezvous"),
        ({"type": "ais_anomaly", "anomaly_type": "loiter", "maritime_domain": "grey_zone"}, "remained"),
        ({"type": "correlated_alert", "anomaly_type": "infrastructure_proximity", "maritime_domain": "grey_zone", "infrastructure": {"name": "Cable A"}}, "infrastructure"),
        ({"type": "vessel_identity", "anomaly_type": "identity_mismatch", "maritime_domain": "grey_zone"}, "identity"),
        ({"type": "gdacs", "maritime_domain": "context"}, "regional hazard"),
        ({"type": "news", "maritime_domain": "context"}, "public reporting"),
    ]
    interpretations = []
    for payload, expected in cases:
        result = build_assessment(payload)
        assert result is not None
        assert expected in result.interpretation.lower()
        interpretations.append(result.interpretation)
    assert len(set(interpretations)) == len(interpretations)
