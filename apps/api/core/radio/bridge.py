# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib

from core.radio.provider import DecodedRadioMessage, RadioObservation


def _persist_radio_observation(observation: RadioObservation) -> None:
    from core.db.session import session_scope
    from core.observability import record_remote_radio_event
    from core.radio.source_observation import persist_radio_observation

    try:
        with session_scope() as db:
            persist_radio_observation(db, observation)
        record_remote_radio_event(
            provider=observation.provider, state="connected", outcome="observation"
        )
    except Exception:
        record_remote_radio_event(
            provider=observation.provider, state="connected", outcome="persist_failed"
        )
        raise


def handle_radio_observation(observation: RadioObservation) -> None:
    """Persist signal-level receiver metadata; never infer a structured message."""
    _persist_radio_observation(observation)


def _raw_evidence_ref(message: DecodedRadioMessage) -> str:
    native = message.provider_message_id
    if not native:
        material = "|".join(
            (
                message.kind,
                message.physical_lineage,
                message.observed_at.isoformat(),
                str(message.frequency_hz),
            )
        )
        native = hashlib.blake2s(material.encode("utf-8"), digest_size=12).hexdigest()
    return f"radio-decoded:{message.provider}:{native}"


def get_structured_radio_runtime():
    from core.radio.structured_runtime import get_structured_radio_runtime as _get

    return _get()


def handle_decoded_radio_message(message: DecodedRadioMessage) -> dict[str, object]:
    """Route only explicit decoder output into the existing structured boundary."""
    runtime = get_structured_radio_runtime()
    common = {
        "receiver_id": message.receiver_id,
        "physical_lineage": message.physical_lineage,
        "observed_at": message.observed_at,
        "frequency_hz": message.frequency_hz,
        "source_terms": message.source_terms,
        "raw_evidence_ref": _raw_evidence_ref(message),
    }
    if message.kind == "dsc":
        return runtime.ingest_dsc(message.payload, **common)
    return runtime.ingest_navtex(
        message.payload,
        decoder_message_id=message.provider_message_id,
        **common,
    )


def radio_acquisition_status() -> dict[str, object]:
    from core.config import config
    from core.radio.runtime import get_remote_radio_status

    status = get_remote_radio_status(include_receivers=True)
    if not status.get("enabled"):
        state = "disabled"
    elif int(status.get("started") or 0) == 0:
        state = "offline"
    elif int(status.get("failed") or 0) > 0:
        state = "degraded"
    else:
        receivers = status.get("receivers") or []
        state = "live" if any(row.get("state") == "connected" for row in receivers) else "degraded"
    return {
        "state": state,
        "structured_enabled": bool(config.STRUCTURED_RADIO_ENABLED),
        "configured": int(status.get("configured") or 0),
        "started": int(status.get("started") or 0),
        "failed": int(status.get("failed") or 0),
        "receivers": list(status.get("receivers") or []),
    }


def register_radio_acquisition_status() -> None:
    from core.acquisition.status import register_acquisition_status

    register_acquisition_status("radio", "Radio", radio_acquisition_status)
