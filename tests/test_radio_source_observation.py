from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from core.radio.provider import RadioObservation


def _radio_observation(**overrides):
    values = {
        "receiver_id": "openwebrx_med_rx",
        "provider": "openwebrx",
        "physical_lineage": "med_rx_01",
        "frequency_hz": 156_800_000,
        "mode": "nbfm",
        "observed_at": datetime(2026, 9, 6, 17, 0, tzinfo=timezone.utc),
        "signal_dbm": -82.5,
        "signal_dbfs": None,
        "snr_db": 11.0,
        "source_terms": "operator-permission",
        "provider_message_id": "msg-42",
        "session_id": "session-a",
    }
    values.update(overrides)
    return RadioObservation(**values)


def test_same_provider_session_message_replays_idempotently():
    from core.db.models import SourceObservationDB
    from core.db.session import session_scope
    from core.radio.source_observation import persist_radio_observation

    observation = _radio_observation()
    with session_scope() as db:
        first = persist_radio_observation(db, observation)
        second = persist_radio_observation(db, observation)
        assert first.replayed is False
        assert second.replayed is True
        assert first.observation_id == second.observation_id

    with session_scope() as db:
        rows = db.query(SourceObservationDB).filter_by(source_name="radio_receiver:med_rx_01").all()
        assert len(rows) == 1


def test_bridge_preserves_receiver_physical_lineage_and_terms_without_frontend_url():
    from core.db.session import session_scope
    from core.radio.source_observation import persist_radio_observation

    with session_scope() as db:
        persisted = persist_radio_observation(db, _radio_observation())

    assert persisted.service == "maritime"
    assert persisted.lane == "intelligence"
    assert persisted.observation_type == "remote_radio_signal"
    assert persisted.source_url == ""
    assert persisted.subject_refs == []
    assert persisted.provenance["receiver_id"] == "openwebrx_med_rx"
    assert persisted.provenance["provider"] == "openwebrx"
    assert persisted.provenance["physical_lineage"] == "med_rx_01"
    assert persisted.provenance["source_terms"] == "operator-permission"


def test_payload_is_bounded_metadata_only_without_audio_iq_transcript_or_mmsi():
    from core.db.models import SourceObservationDB
    from core.db.session import session_scope
    from core.radio.source_observation import persist_radio_observation

    expected_payload = {
        "frequency_hz": 156_800_000,
        "mode": "nbfm",
        "signal_dbm": -82.5,
        "signal_dbfs": None,
        "snr_db": 11.0,
    }
    encoded = json.dumps(expected_payload, sort_keys=True, separators=(",", ":"))
    with session_scope() as db:
        persisted = persist_radio_observation(db, _radio_observation())
        row = db.get(SourceObservationDB, persisted.observation_id)
        assert row.raw_payload_ref in (None, "")
        assert row.raw_payload_hash == hashlib.sha256(encoded.encode()).hexdigest()

    serialized = json.dumps({"payload": expected_payload, "provenance": persisted.provenance}).lower()
    for forbidden in ("audio", "waveform", "iq", "transcript", "mmsi", "callsign"):
        assert forbidden not in serialized


def test_bridge_never_creates_humanitarian_incident_or_lifecycle_transition():
    from core.db.models import HumanitarianIncidentDB, IncidentTransitionDB
    from core.db.session import session_scope
    from core.radio.source_observation import persist_radio_observation

    with session_scope() as db:
        before_incidents = db.query(HumanitarianIncidentDB).count()
        before_transitions = db.query(IncidentTransitionDB).count()
        persist_radio_observation(db, _radio_observation())
        assert db.query(HumanitarianIncidentDB).count() == before_incidents
        assert db.query(IncidentTransitionDB).count() == before_transitions


def test_missing_provider_delivery_id_still_has_stable_session_fallback():
    from core.db.session import session_scope
    from core.radio.source_observation import persist_radio_observation

    observation = _radio_observation(provider_message_id=None)
    with session_scope() as db:
        first = persist_radio_observation(db, observation)
        second = persist_radio_observation(db, observation)
    assert first.observation_id == second.observation_id
    assert second.replayed is True
