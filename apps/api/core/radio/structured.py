# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.radio.provider import _normalize_identifier

_DSC_CATEGORIES = frozenset({"distress", "urgency", "safety", "routine", "unknown"})
_MAX_NAVTEX_TEXT_CHARS = 8192
_MAX_FREE_TEXT_CHARS = 256


def _required_text(value: str, *, field: str, max_chars: int = _MAX_FREE_TEXT_CHARS) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    return text[:max_chars]


def _validate_common(
    *,
    receiver_id: str,
    physical_lineage: str,
    observed_at: datetime,
    frequency_hz: int,
    raw_evidence_ref: str,
    decoder_message_id: str,
) -> tuple[str, str, str, str]:
    receiver = _normalize_identifier(receiver_id, field="receiver_id")
    lineage = _normalize_identifier(physical_lineage, field="physical_lineage")
    raw_ref = _required_text(raw_evidence_ref, field="raw_evidence_ref", max_chars=512)
    message_id = _required_text(decoder_message_id, field="decoder_message_id", max_chars=256)
    if frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return receiver, lineage, raw_ref, message_id


@dataclass(frozen=True)
class DSCObservation:
    receiver_id: str
    physical_lineage: str
    observed_at: datetime
    frequency_hz: int
    source_terms: str | None
    raw_evidence_ref: str
    decoder_message_id: str
    category: str
    mmsi: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    nature_code: str | None = None
    field_presence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        receiver, lineage, raw_ref, message_id = _validate_common(
            receiver_id=self.receiver_id,
            physical_lineage=self.physical_lineage,
            observed_at=self.observed_at,
            frequency_hz=self.frequency_hz,
            raw_evidence_ref=self.raw_evidence_ref,
            decoder_message_id=self.decoder_message_id,
        )
        category = str(self.category or "").strip().lower()
        if category not in _DSC_CATEGORIES:
            category = "unknown"
        mmsi = str(self.mmsi or "").strip() or None
        if mmsi is not None and (not mmsi.isdigit() or len(mmsi) > 9):
            raise ValueError("mmsi must be numeric and at most 9 digits")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("coordinates require both latitude and longitude")
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            raise ValueError("latitude out of range")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise ValueError("longitude out of range")

        object.__setattr__(self, "receiver_id", receiver)
        object.__setattr__(self, "physical_lineage", lineage)
        object.__setattr__(self, "raw_evidence_ref", raw_ref)
        object.__setattr__(self, "decoder_message_id", message_id)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "mmsi", mmsi)
        object.__setattr__(
            self,
            "nature_code",
            str(self.nature_code or "").strip().lower()[:64] or None,
        )
        object.__setattr__(self, "source_terms", str(self.source_terms or "").strip() or None)
        object.__setattr__(
            self,
            "field_presence",
            tuple(sorted({str(name).strip().lower() for name in self.field_presence if str(name).strip()})),
        )


@dataclass(frozen=True)
class NAVTEXObservation:
    receiver_id: str
    physical_lineage: str
    observed_at: datetime
    frequency_hz: int
    source_terms: str | None
    raw_evidence_ref: str
    decoder_message_id: str
    station_id: str
    subject_id: str
    message_id: str
    area: str | None
    text: str

    def __post_init__(self) -> None:
        receiver, lineage, raw_ref, decoder_message_id = _validate_common(
            receiver_id=self.receiver_id,
            physical_lineage=self.physical_lineage,
            observed_at=self.observed_at,
            frequency_hz=self.frequency_hz,
            raw_evidence_ref=self.raw_evidence_ref,
            decoder_message_id=self.decoder_message_id,
        )
        station_id = _required_text(self.station_id, field="station_id", max_chars=8).upper()
        subject_id = _required_text(self.subject_id, field="subject_id", max_chars=8).upper()
        message_id = _required_text(self.message_id, field="message_id", max_chars=32)
        text = str(self.text or "").strip()
        if not text:
            raise ValueError("text must not be empty")

        object.__setattr__(self, "receiver_id", receiver)
        object.__setattr__(self, "physical_lineage", lineage)
        object.__setattr__(self, "raw_evidence_ref", raw_ref)
        object.__setattr__(self, "decoder_message_id", decoder_message_id)
        object.__setattr__(self, "station_id", station_id)
        object.__setattr__(self, "subject_id", subject_id)
        object.__setattr__(self, "message_id", message_id)
        object.__setattr__(self, "area", str(self.area or "").strip()[:128] or None)
        object.__setattr__(self, "text", text[:_MAX_NAVTEX_TEXT_CHARS])
        object.__setattr__(self, "source_terms", str(self.source_terms or "").strip() or None)
