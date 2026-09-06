from __future__ import annotations

import json
from datetime import datetime, timezone


def _dsc(**overrides):
    from core.radio.structured import DSCObservation

    values = {
        "receiver_id": "owrx_med_rx",
        "physical_lineage": "med_rx_01",
        "observed_at": datetime(2026, 9, 6, 18, 0, tzinfo=timezone.utc),
        "frequency_hz": 2_187_500,
        "source_terms": "operator-permission",
        "raw_evidence_ref": "artifact:dsc:42",
        "decoder_message_id": "dsc-msg-42",
        "category": "distress",
        "mmsi": "123456789",
        "latitude": 35.5,
        "longitude": 14.2,
        "nature_code": "undesignated",
        "field_presence": ("category", "mmsi", "latitude", "longitude", "nature_code"),
    }
    values.update(overrides)
    return DSCObservation(**values)


def _navtex(**overrides):
    from core.radio.structured import NAVTEXObservation

    values = {
        "receiver_id": "kiwi_med_rx",
        "physical_lineage": "med_rx_01",
        "observed_at": datetime(2026, 9, 6, 18, 1, tzinfo=timezone.utc),
        "frequency_hz": 518_000,
        "source_terms": "operator-permission",
        "raw_evidence_ref": "artifact:navtex:17",
        "decoder_message_id": "navtex-msg-17",
        "station_id": "M",
        "subject_id": "B",
        "message_id": "42",
        "area": "central-mediterranean",
        "text": "GALE WARNING IN FORCE. DISTRESS TRAFFIC MAY BE PRESENT.",
    }
    values.update(overrides)
    return NAVTEXObservation(**values)


def test_same_dsc_decoder_key_replays_idempotently():
    from core.db.models import SourceObservationDB
    from core.db.session import session_scope
    from core.radio.structured_source_observation import persist_dsc_observation

    observation = _dsc()
    with session_scope() as db:
        first = persist_dsc_observation(db, observation)
        second = persist_dsc_observation(db, observation)
        assert first.replayed is False
        assert second.replayed is True
        assert first.observation_id == second.observation_id

    with session_scope() as db:
        rows = db.query(SourceObservationDB).filter_by(source_name="radio_receiver:med_rx_01").all()
        assert len(rows) == 1


def test_different_frontends_same_physical_lineage_share_source_boundary():
    from core.db.session import session_scope
    from core.radio.structured_source_observation import (
        persist_dsc_observation,
        persist_navtex_observation,
    )

    with session_scope() as db:
        dsc = persist_dsc_observation(db, _dsc(receiver_id="owrx_frontend"))
        navtex = persist_navtex_observation(db, _navtex(receiver_id="kiwi_frontend"))

    assert dsc.source_name == "radio_receiver:med_rx_01"
    assert navtex.source_name == "radio_receiver:med_rx_01"
    assert dsc.source_name == navtex.source_name


def test_dsc_persists_as_maritime_safety_with_bounded_structured_payload():
    from core.db.models import SourceObservationDB
    from core.db.session import session_scope
    from core.radio.structured_source_observation import persist_dsc_observation

    with session_scope() as db:
        persisted = persist_dsc_observation(db, _dsc())
        row = db.get(SourceObservationDB, persisted.observation_id)
        payload = json.loads(row.provenance["structured_payload"])

    assert persisted.service == "maritime"
    assert persisted.lane == "safety"
    assert persisted.observation_type == "dsc_message"
    assert payload["category"] == "distress"
    assert payload["mmsi"] == "123456789"
    assert payload["latitude"] == 35.5
    assert payload["longitude"] == 14.2
    assert payload["nature_code"] == "undesignated"
    assert payload["field_presence"] == ["category", "latitude", "longitude", "mmsi", "nature_code"]


def test_navtex_persists_as_maritime_context_without_emergency_or_humanitarian_authority():
    from core.db.models import SourceObservationDB
    from core.db.session import session_scope
    from core.radio.structured_source_observation import persist_navtex_observation

    with session_scope() as db:
        persisted = persist_navtex_observation(db, _navtex())
        row = db.get(SourceObservationDB, persisted.observation_id)
        payload = json.loads(row.provenance["structured_payload"])

    assert persisted.service == "maritime"
    assert persisted.lane == "safety"
    assert persisted.observation_type == "navtex_message"
    assert payload["station_id"] == "M"
    assert payload["subject_id"] == "B"
    assert payload["message_id"] == "42"
    assert "DISTRESS" in payload["text"]
    serialized = json.dumps({"payload": payload, "provenance": persisted.provenance}).lower()
    for forbidden in ("humanitarian", "lifecycle", "publication", "audio", "waveform", " iq "):
        assert forbidden not in serialized


def test_bridge_uses_raw_evidence_ref_without_persisting_waveform_body():
    from core.db.models import SourceObservationDB
    from core.db.session import session_scope
    from core.radio.structured_source_observation import persist_dsc_observation

    with session_scope() as db:
        persisted = persist_dsc_observation(db, _dsc(raw_evidence_ref="artifact:dsc:raw-frame-42"))
        row = db.get(SourceObservationDB, persisted.observation_id)
        raw_payload_ref = row.raw_payload_ref
        raw_payload_hash = row.raw_payload_hash
        serialized = json.dumps(row.provenance).lower()

    assert raw_payload_ref == "artifact:dsc:raw-frame-42"
    assert raw_payload_hash
    for forbidden in ("audio", "waveform", "iq_bytes", "transcript"):
        assert forbidden not in serialized


def test_bridge_never_creates_humanitarian_incident_or_lifecycle_transition():
    from core.db.models import HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import session_scope
    from core.radio.structured_source_observation import (
        persist_dsc_observation,
        persist_navtex_observation,
    )

    with session_scope() as db:
        before_incidents = db.query(HumanitarianIncidentDB).count()
        before_transitions = db.query(IncidentTransitionDB).count()
        persist_dsc_observation(db, _dsc(decoder_message_id="dsc-no-side-effect"))
        persist_navtex_observation(db, _navtex(decoder_message_id="navtex-no-side-effect"))
        assert db.query(HumanitarianIncidentDB).count() == before_incidents
        assert db.query(IncidentTransitionDB).count() == before_transitions
