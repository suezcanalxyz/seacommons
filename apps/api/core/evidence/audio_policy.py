# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass

_ALLOWED_RETENTION = frozenset({"24h", "7d", "30d"})
_ABSOLUTE_MAX_CLIP_SECONDS = 300


@dataclass(frozen=True)
class AudioAcquisitionPolicy:
    enabled: bool
    max_clip_seconds: int
    retention_policy: str
    storage_prefix: str

    def __post_init__(self) -> None:
        if self.max_clip_seconds <= 0 or self.max_clip_seconds > _ABSOLUTE_MAX_CLIP_SECONDS:
            raise ValueError("max_clip_seconds must be between 1 and 300")
        object.__setattr__(self, "retention_policy", str(self.retention_policy or "").strip().lower())
        object.__setattr__(self, "storage_prefix", str(self.storage_prefix or "").strip())

    def authorize(
        self,
        *,
        duration_seconds: float,
        terms_status: str,
        source_terms: str,
    ) -> tuple[bool, str]:
        if not self.enabled:
            return False, "disabled"
        if not self.storage_prefix:
            return False, "storage_unconfigured"
        if self.retention_policy not in _ALLOWED_RETENTION:
            return False, "retention_not_allowed"
        if str(terms_status or "").strip() != "allowed":
            return False, "terms_not_allowed"
        if not str(source_terms or "").strip():
            return False, "source_terms_missing"
        if duration_seconds <= 0:
            return False, "invalid_duration"
        if duration_seconds > self.max_clip_seconds:
            return False, "duration_exceeds_limit"
        return True, "allowed"


def policy_from_config() -> AudioAcquisitionPolicy:
    from core.config import config

    return AudioAcquisitionPolicy(
        enabled=config.AUDIO_EVIDENCE_ENABLED,
        max_clip_seconds=config.AUDIO_EVIDENCE_MAX_CLIP_SECONDS,
        retention_policy=config.AUDIO_EVIDENCE_RETENTION_POLICY,
        storage_prefix=config.AUDIO_EVIDENCE_STORAGE_PREFIX,
    )
