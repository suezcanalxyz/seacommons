# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Mapping, Any

from core.radio.structured import DSCObservation

_DSC_FIELDS = frozenset({"category", "mmsi", "latitude", "longitude", "nature_code"})


def _stable_decoder_id(
    payload: Mapping[str, Any],
    *,
    physical_lineage: str,
    observed_at: datetime,
    frequency_hz: int,
) -> str:
    bounded = {key: payload.get(key) for key in sorted(_DSC_FIELDS) if key in payload}
    encoded = json.dumps(
        {
            "physical_lineage": str(physical_lineage),
            "observed_at": observed_at.isoformat(),
            "frequency_hz": int(frequency_hz),
            "payload": bounded,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.blake2s(encoded.encode("utf-8"), digest_size=16).hexdigest()
    return f"dsc_{digest}"


def normalize_dsc_decoder_message(
    payload: Mapping[str, Any],
    *,
    receiver_id: str,
    physical_lineage: str,
    observed_at: datetime,
    frequency_hz: int,
    source_terms: str | None,
    raw_evidence_ref: str,
) -> DSCObservation:
    if not isinstance(payload, Mapping):
        raise ValueError("DSC decoder payload must be a mapping")

    decoder_message_id = str(
        payload.get("message_id") or payload.get("decoder_message_id") or ""
    ).strip()
    if not decoder_message_id:
        decoder_message_id = _stable_decoder_id(
            payload,
            physical_lineage=physical_lineage,
            observed_at=observed_at,
            frequency_hz=frequency_hz,
        )

    present = tuple(sorted(key for key in _DSC_FIELDS if key in payload and payload.get(key) is not None))
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")

    return DSCObservation(
        receiver_id=receiver_id,
        physical_lineage=physical_lineage,
        observed_at=observed_at,
        frequency_hz=frequency_hz,
        source_terms=source_terms,
        raw_evidence_ref=raw_evidence_ref,
        decoder_message_id=decoder_message_id,
        category=str(payload.get("category") or "unknown"),
        mmsi=str(payload.get("mmsi") or "").strip() or None,
        latitude=float(latitude) if latitude is not None else None,
        longitude=float(longitude) if longitude is not None else None,
        nature_code=str(payload.get("nature_code") or "").strip() or None,
        field_presence=present,
    )


def dsc_classification_metadata(observation: DSCObservation) -> dict[str, str]:
    return {
        "service": "maritime",
        "lane": "safety",
        "observation_type": "dsc_message",
        "dsc_category": observation.category,
    }
