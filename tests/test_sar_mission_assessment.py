from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fresh_assessments():
    from core.db.models import AssessmentDB
    from core.db.session import engine, session_scope

    AssessmentDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(AssessmentDB).filter(AssessmentDB.field_type == "sar_mission").delete()
    yield


def _response(*, state="probable_rescue_activity", coverage="coverage_present", providers=None, upstream=None):
    return {
        "ngo_vessels": [{
            "mmsi": "258479000", "name": "Ocean Viking", "org": "SOS Méditerranée",
            "mission_state": state, "coverage_status": coverage,
            "motion_flags": ["search_pattern"] if state == "probable_rescue_activity" else [],
            "track_providers": providers or ["aisstream", "aiscast"],
            "upstream_sources": upstream or ["aisstream", "volunteer"],
            "stations": ["mt-01"], "distance_nm": 4.2, "heading_toward": True,
            "eta_h": 0.4, "fix_age_min": 3,
        }],
    }


def test_persisted_sar_mission_assessment_is_idempotent_per_incident_asset():
    from core.intel.sar_mission_assessment import (
        get_sar_mission_assessments,
        persist_sar_mission_assessments,
    )

    first = persist_sar_mission_assessments("incident-1", _response())
    second = persist_sar_mission_assessments("incident-1", _response())
    assert first == second
    rows = get_sar_mission_assessments("incident-1")
    assert len(rows) == 1
    assert rows[0]["value"]["mission_state"] == "probable_rescue_activity"


def test_provider_degraded_caps_persisted_state_at_possible_response():
    from core.intel.sar_mission_assessment import persist_sar_mission_assessments

    row = persist_sar_mission_assessments(
        "incident-2", _response(state="probable_rescue_activity", coverage="provider_degraded")
    )[0]
    assert row["value"]["mission_state"] == "possible_response"
    assert "PROVIDER_DEGRADED_CAP" in row["value"]["reason_codes"]


def test_ais_only_input_can_never_persist_rescue_confirmed():
    from core.intel.sar_mission_assessment import persist_sar_mission_assessments

    row = persist_sar_mission_assessments("incident-3", _response(state="rescue_confirmed"))[0]
    assert row["value"]["mission_state"] == "probable_rescue_activity"
    assert "AIS_CONFIRMATION_CAP" in row["value"]["reason_codes"]


def test_multiple_ais_transports_remain_one_physical_independence_group():
    from core.intel.sar_mission_assessment import persist_sar_mission_assessments

    row = persist_sar_mission_assessments(
        "incident-4",
        _response(providers=["aisstream", "aiscast"], upstream=["aisstream", "aisstream"]),
    )[0]
    assert row["value"]["track_providers"] == ["aiscast", "aisstream"]
    assert row["value"]["upstream_sources"] == ["aisstream"]
    assert row["value"]["independence_groups"] == ["ais_sensor_lineage"]


@pytest.mark.parametrize("state", ["unrelated", "possible_response", "approaching", "on_scene", "probable_rescue_activity"])
def test_existing_descriptive_mission_states_persist_without_intent_inference(state):
    from core.intel.sar_mission_assessment import persist_sar_mission_assessments

    row = persist_sar_mission_assessments(f"incident-{state}", _response(state=state))[0]
    assert row["value"]["mission_state"] == state
    assert "intent" not in row["value"]
    assert "risk_score" not in row["value"]
