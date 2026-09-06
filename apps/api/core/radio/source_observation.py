# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import json

from core.intel.source_observation import SourceObservation, record_observation
from core.radio.provider import RadioObservation

_SOURCE_POLICY = "configured_remote_receiver"
_OBSERVATION_TYPE = "remote_radio_signal"
_SERVICE = "maritime"
_LANE = "intelligence"


def _source_name(observation: RadioObservation) -> str:
    # Physical receiver is the evidence source. Provider/frontend is transport provenance.
    return f"radio_receiver:{observation.physical_lineage}"


def _delivery_key(observation: RadioObservation) -> str:
    if observation.provider_message_id:
        native = observation.provider_message_id
    else:
        native = "|".join(
            (
                observation.session_id or "no_session",
                observation.observed_at.isoformat(),
                str(observation.frequency_hz),
                observation.mode,
            )
        )
    digest = hashlib.blake2s(
        f"{observation.provider}:{native}".encode("utf-8"), digest_size=16
    ).hexdigest()
    return f"radio:{digest}"


def _bounded_payload(observation: RadioObservation) -> str:
    payload = {
        "frequency_hz": observation.frequency_hz,
        "mode": observation.mode,
        "signal_dbm": observation.signal_dbm,
        "signal_dbfs": observation.signal_dbfs,
        "snr_db": observation.snr_db,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def persist_radio_observation(db, observation: RadioObservation) -> SourceObservation:
    """Persist bounded radio metadata without waveform/audio or domain mutation."""
    return record_observation(
        db,
        service=_SERVICE,
        lane=_LANE,
        observation_type=_OBSERVATION_TYPE,
        source_name=_source_name(observation),
        source_policy=_SOURCE_POLICY,
        source_id=_delivery_key(observation),
        observed_at=observation.observed_at.isoformat(),
        raw_payload=_bounded_payload(observation),
        subject_refs=[],
        provenance={
            "receiver_id": observation.receiver_id,
            "provider": observation.provider,
            "physical_lineage": observation.physical_lineage,
            "source_terms": observation.source_terms or "",
            "session_present": bool(observation.session_id),
        },
    )
