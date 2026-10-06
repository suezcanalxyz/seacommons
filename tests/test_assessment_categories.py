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


def test_gap_assessment_uses_canonical_duration_and_never_reports_zero_when_unknown():
    result = build_assessment({
        "type": "ais_anomaly",
        "anomaly_type": "gap",
        "maritime_domain": "grey_zone",
        "linked_mmsi": "352004886",
        "current_silent_seconds": 5400,
        "gap_still_open": True,
        "reception_expectation": "healthy",
        "reason_codes": ["PROLONGED_OFFSHORE_GAP", "LOCAL_AIS_COVERAGE_HEALTHY"],
    })
    assert result is not None
    assert "90 min" in result.observation
    assert "90 minutes" in result.interpretation
    assert "still open" in result.interpretation
    assert result.classification_version == "assessment-v2"

    unknown = build_assessment({
        "type": "ais_anomaly",
        "anomaly_type": "gap",
        "maritime_domain": "grey_zone",
        "linked_mmsi": "352004886",
    })
    assert unknown is not None
    assert "0 min" not in unknown.observation


def test_spoofing_interpretation_uses_case_specific_detector_context():
    result = build_assessment({
        "type": "ais_anomaly",
        "anomaly_type": "position_jump",
        "maritime_domain": "grey_zone",
        "linked_mmsi": "372497000",
        "movement_evidence": {
            "distance_km": 625.4,
            "time_delta_s": 660,
            "implied_speed_kn": 1840,
        },
        "reason_codes": [
            "SUSTAINED_POSITION_RELOCATION",
            "NO_COINCIDENT_MULTI_VESSEL_GLITCH",
            "OPEN_SEA_CONTEXT",
        ],
        "offshore_context": {"offshore": True, "distance_from_coast_km": 81},
    })
    assert result is not None
    assert "625.4 km" in result.interpretation
    assert "1840 kn" in result.interpretation
    assert "no coincident multi-vessel glitch" in result.interpretation.lower()
    assert "81 km from the coast" in result.interpretation


def test_rendezvous_and_infrastructure_interpretations_use_case_metrics():
    rendezvous = build_assessment({
        "type": "ais_rendezvous",
        "anomaly_type": "rendezvous",
        "maritime_domain": "grey_zone",
        "linked_mmsi": "111111111",
        "partner_mmsi": "222222222",
        "min_distance_nm": 0.18,
        "duration_minutes": 74,
        "reason_codes": ["SUSTAINED_OPEN_SEA_RENDEZVOUS"],
    })
    assert rendezvous is not None
    assert "222222222" in rendezvous.interpretation
    assert "0.18 nm" in rendezvous.interpretation
    assert "74 minutes" in rendezvous.interpretation

    infrastructure = build_assessment({
        "type": "correlated_alert",
        "anomaly_type": "infrastructure_proximity",
        "maritime_domain": "grey_zone",
        "infrastructure": {"name": "Cable Alpha", "distance_km": 1.7},
        "duration_minutes": 46,
        "reason_codes": ["SUSTAINED_INFRASTRUCTURE_PROXIMITY"],
    })
    assert infrastructure is not None
    assert "Cable Alpha" in infrastructure.interpretation
    assert "1.7 km" in infrastructure.interpretation
    assert "46 minutes" in infrastructure.interpretation
