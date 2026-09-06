# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

_MAX_TEXT = 20_000


def _required(value: str, field_name: str, max_chars: int = 256) -> str:
    text = str(value or '').strip()
    if not text:
        raise ValueError(f'{field_name} must not be empty')
    return text[:max_chars]


@dataclass(frozen=True)
class DerivedAudioTranscript:
    artifact_id: str
    artifact_sha256: str
    text: str
    language: str | None
    engine: str
    model: str
    model_version: str
    created_at: datetime
    transcript_id: str = field(init=False)
    derived: bool = field(init=False, default=True)
    canonical_authority: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        artifact_id = _required(self.artifact_id, 'artifact_id')
        sha = str(self.artifact_sha256 or '').strip().lower()
        if len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('artifact_sha256 must be a 64-character sha256 hex digest')
        text = str(self.text or '').strip()
        if not text:
            raise ValueError('text must not be empty')
        text = text[:_MAX_TEXT]
        engine = _required(self.engine, 'engine', 128)
        model = _required(self.model, 'model', 128)
        model_version = _required(self.model_version, 'model_version', 128)
        language = str(self.language or '').strip().lower()[:32] or None
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError('created_at must be timezone-aware')
        material = '|'.join((artifact_id, sha, engine, model, model_version, language or '', text))
        transcript_id = 'atr:' + hashlib.blake2s(material.encode('utf-8'), digest_size=16).hexdigest()
        object.__setattr__(self, 'artifact_id', artifact_id)
        object.__setattr__(self, 'artifact_sha256', sha)
        object.__setattr__(self, 'text', text)
        object.__setattr__(self, 'engine', engine)
        object.__setattr__(self, 'model', model)
        object.__setattr__(self, 'model_version', model_version)
        object.__setattr__(self, 'language', language)
        object.__setattr__(self, 'transcript_id', transcript_id)
