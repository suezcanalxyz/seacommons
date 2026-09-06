# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import re
from datetime import datetime

from core.radio.structured import NAVTEXObservation

_HEADER_RE = re.compile(r"^ZCZC\s+([A-Z])([A-Z])(\d{2})$")


def _normalize_block(block: str) -> list[str]:
    text = str(block or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("NAVTEX block must not be empty")
    return [line.rstrip() for line in text.split("\n")]


def _deterministic_id(
    normalized_block: str,
    *,
    physical_lineage: str,
    observed_at: datetime,
    frequency_hz: int,
) -> str:
    material = "|".join(
        (
            str(physical_lineage),
            observed_at.isoformat(),
            str(int(frequency_hz)),
            normalized_block,
        )
    )
    digest = hashlib.blake2s(material.encode("utf-8"), digest_size=16).hexdigest()
    return f"navtex_{digest}"


def parse_navtex_block(
    block: str,
    *,
    receiver_id: str,
    physical_lineage: str,
    observed_at: datetime,
    frequency_hz: int,
    source_terms: str | None,
    raw_evidence_ref: str,
    area: str | None = None,
    decoder_message_id: str | None = None,
) -> NAVTEXObservation:
    lines = _normalize_block(block)
    header = _HEADER_RE.fullmatch(lines[0].strip().upper())
    if header is None:
        raise ValueError("invalid NAVTEX header")
    if len(lines) < 2 or lines[-1].strip().upper() != "NNNN":
        raise ValueError("NAVTEX terminator NNNN is required")

    body = "\n".join(line for line in lines[1:-1]).strip()
    if not body:
        raise ValueError("NAVTEX body must not be empty")

    station_id, subject_id, message_id = header.groups()
    normalized = "\n".join([f"ZCZC {station_id}{subject_id}{message_id}", body, "NNNN"])
    native_id = str(decoder_message_id or "").strip()
    if not native_id:
        native_id = _deterministic_id(
            normalized,
            physical_lineage=physical_lineage,
            observed_at=observed_at,
            frequency_hz=frequency_hz,
        )

    return NAVTEXObservation(
        receiver_id=receiver_id,
        physical_lineage=physical_lineage,
        observed_at=observed_at,
        frequency_hz=frequency_hz,
        source_terms=source_terms,
        raw_evidence_ref=raw_evidence_ref,
        decoder_message_id=native_id,
        station_id=station_id,
        subject_id=subject_id,
        message_id=message_id,
        area=area,
        text=body,
    )
