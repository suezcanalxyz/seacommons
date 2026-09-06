# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

from core.radio.provider import _normalize_identifier

_MAX_AUDIO_DURATION_SECONDS = 300.0
_ALLOWED_RETENTION_POLICIES = frozenset({"24h", "7d", "30d"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: str, *, field_name: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text[:max_chars]


def _aware(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


@dataclass(frozen=True)
class AudioEvidenceArtifact:
    physical_lineage: str
    receiver_id: str
    frequency_hz: int
    channel: str
    started_at: datetime
    ended_at: datetime
    content_sha256: str
    storage_ref: str
    mime_type: str
    codec: str
    source_terms: str
    retention_policy: str
    source_observation_ids: tuple[str, ...]
    artifact_type: str = field(init=False, default="audio")
    artifact_id: str = field(init=False)

    def __post_init__(self) -> None:
        lineage = _normalize_identifier(self.physical_lineage, field="physical_lineage")
        receiver = _normalize_identifier(self.receiver_id, field="receiver_id")
        if self.frequency_hz <= 0:
            raise ValueError("frequency_hz must be positive")
        channel = _required_text(self.channel, field_name="channel", max_chars=64)
        started_at = _aware(self.started_at, field_name="started_at")
        ended_at = _aware(self.ended_at, field_name="ended_at")
        if ended_at <= started_at:
            raise ValueError("ended_at must be after started_at")
        duration = (ended_at - started_at).total_seconds()
        if duration > _MAX_AUDIO_DURATION_SECONDS:
            raise ValueError("audio duration exceeds maximum bounded duration")

        content_hash = str(self.content_sha256 or "").strip().lower()
        if _SHA256_RE.fullmatch(content_hash) is None:
            raise ValueError("content_sha256 must be a 64-character hexadecimal sha256")
        storage_ref = _required_text(self.storage_ref, field_name="storage_ref", max_chars=512)
        mime_type = _required_text(self.mime_type, field_name="mime_type", max_chars=128).lower()
        if not mime_type.startswith("audio/"):
            raise ValueError("mime_type must be an audio MIME type")
        codec = _required_text(self.codec, field_name="codec", max_chars=32).lower()
        source_terms = _required_text(self.source_terms, field_name="source_terms", max_chars=512)
        retention = str(self.retention_policy or "").strip().lower()
        if retention not in _ALLOWED_RETENTION_POLICIES:
            raise ValueError("retention_policy must be one of 24h, 7d, or 30d")

        links = tuple(dict.fromkeys(str(value).strip() for value in self.source_observation_ids if str(value).strip()))
        if not links or len(links) > 32:
            raise ValueError("source_observation_ids must contain between 1 and 32 identifiers")
        if any(len(value) > 128 for value in links):
            raise ValueError("source_observation_ids contains an overlong identifier")

        material = "|".join(
            (
                lineage,
                content_hash,
                started_at.isoformat(),
                ended_at.isoformat(),
            )
        )
        artifact_id = f"audio:{hashlib.blake2s(material.encode('utf-8'), digest_size=16).hexdigest()}"

        object.__setattr__(self, "physical_lineage", lineage)
        object.__setattr__(self, "receiver_id", receiver)
        object.__setattr__(self, "channel", channel)
        object.__setattr__(self, "content_sha256", content_hash)
        object.__setattr__(self, "storage_ref", storage_ref)
        object.__setattr__(self, "mime_type", mime_type)
        object.__setattr__(self, "codec", codec)
        object.__setattr__(self, "source_terms", source_terms)
        object.__setattr__(self, "retention_policy", retention)
        object.__setattr__(self, "source_observation_ids", links)
        object.__setattr__(self, "artifact_id", artifact_id)

    @property
    def duration_seconds(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()
