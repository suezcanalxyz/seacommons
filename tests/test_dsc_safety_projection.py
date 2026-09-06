from __future__ import annotations

from datetime import datetime, timezone
import uuid


def _dsc(**overrides):
    from core.radio.structured import DSCObservation

    values = {
        "receiver_id": "owrx_med_rx",
        "physical_lineage": "med_rx_01",
        "observed_at": datetime(2026, 9, 6, 18, 30, tzinfo=timezone.utc),
        "frequency_hz": 2_187_500,
        "source_terms": "operator-permission",
        "raw_evidence_ref": "artifact:dsc:99",
        "decoder_message_id": "dsc-msg-99",
        "category": "distress",
        "mmsi": "123456789",
        "latitude": 35.5,
        "longitude": 14.2,
        "nature_code": "undesignated",
        "field_presence": ("category", "mmsi", "latitude", "longitude", "nature_code"),
    }
    values.update(overrides)
    return DSCObservation(**values)


def test_distress_dsc_projects_bounded_maritime_safety_candidate():
    from core.intel.service_taxonomy import classify_service
    from core.radio.safety_projection import project_dsc_safety_candidate

    event = project_dsc_safety_candidate(_dsc(), evidence_observation_id="obs:dsc:99")
    assert event is not None
    assert event.type == "dsc_distress"
    assert event.severity == "critical"
    assert event.source == "radio_receiver:med_rx_01"
    assert event.linked_mmsi == "123456789"
    assert event.lat == 35.5 and event.lon == 14.2
    assert event.metadata["evidence_observation_id"] == "obs:dsc:99"
    assert event.metadata["receiver_id"] == "owrx_med_rx"
    classification = classify_service(event)
    assert classification.service == "maritime"
    assert classification.lane == "safety"


def test_non_distress_dsc_does_not_project_candidate():
    from core.radio.safety_projection import project_dsc_safety_candidate

    for category in ("urgency", "safety", "routine", "unknown"):
        assert project_dsc_safety_candidate(_dsc(category=category), evidence_observation_id="obs:x") is None


def test_navtex_has_no_direct_safety_candidate_projection():
    import core.radio.safety_projection as projection

    assert not hasattr(projection, "project_navtex_safety_candidate")


def test_replay_does_not_duplicate_candidate():
    from core.intel.store import intel_store
    from core.radio.safety_projection import ingest_dsc_safety_candidate

    observation = _dsc(decoder_message_id=f"dsc-replay-{uuid.uuid4().hex}")
    first = ingest_dsc_safety_candidate(observation, evidence_observation_id="obs:replay")
    second = ingest_dsc_safety_candidate(observation, evidence_observation_id="obs:replay")
    assert first is True
    assert second is False
    matches = [e for e in intel_store.events(limit=500) if e.metadata.get("evidence_observation_id") == "obs:replay"]
    assert len(matches) == 1


def test_projection_never_creates_humanitarian_incident_or_transition():
    from core.db.models import HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import session_scope
    from core.radio.safety_projection import ingest_dsc_safety_candidate

    with session_scope() as db:
        before_incidents = db.query(HumanitarianIncidentDB).count()
        before_transitions = db.query(IncidentTransitionDB).count()
    ingest_dsc_safety_candidate(_dsc(decoder_message_id="dsc-no-humanitarian"), evidence_observation_id="obs:nohum")
    with session_scope() as db:
        assert db.query(HumanitarianIncidentDB).count() == before_incidents
        assert db.query(IncidentTransitionDB).count() == before_transitions
