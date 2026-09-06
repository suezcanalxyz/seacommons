from __future__ import annotations

import pytest


def _policy(**overrides):
    from core.evidence.audio_policy import AudioAcquisitionPolicy

    values = {
        "enabled": True,
        "max_clip_seconds": 60,
        "retention_policy": "7d",
        "storage_prefix": "object://restricted-audio/",
    }
    values.update(overrides)
    return AudioAcquisitionPolicy(**values)


def test_policy_is_disabled_by_default_from_config():
    from core.config import config
    from core.evidence.audio_policy import policy_from_config

    assert config.AUDIO_EVIDENCE_ENABLED is False
    policy = policy_from_config()
    assert policy.enabled is False
    assert policy.authorize(duration_seconds=30, terms_status="allowed", source_terms="ok") == (False, "disabled")


def test_allowed_terms_bounded_duration_and_storage_authorize_capture():
    policy = _policy()
    assert policy.authorize(duration_seconds=30, terms_status="allowed", source_terms="operator-permission") == (True, "allowed")


@pytest.mark.parametrize("status", ["unknown", "blocked", "", "ALLOW"])
def test_unclear_or_blocked_terms_fail_closed(status):
    policy = _policy()
    assert policy.authorize(duration_seconds=30, terms_status=status, source_terms="operator-permission") == (False, "terms_not_allowed")


def test_missing_source_terms_storage_or_bad_retention_fail_closed():
    assert _policy(storage_prefix="").authorize(duration_seconds=30, terms_status="allowed", source_terms="ok") == (False, "storage_unconfigured")
    assert _policy(retention_policy="forever").authorize(duration_seconds=30, terms_status="allowed", source_terms="ok") == (False, "retention_not_allowed")
    assert _policy().authorize(duration_seconds=30, terms_status="allowed", source_terms="") == (False, "source_terms_missing")


def test_duration_must_be_positive_and_within_policy_cap():
    policy = _policy(max_clip_seconds=60)
    assert policy.authorize(duration_seconds=0, terms_status="allowed", source_terms="ok") == (False, "invalid_duration")
    assert policy.authorize(duration_seconds=61, terms_status="allowed", source_terms="ok") == (False, "duration_exceeds_limit")
    assert policy.authorize(duration_seconds=60, terms_status="allowed", source_terms="ok") == (True, "allowed")


def test_policy_max_can_never_enable_continuous_or_over_five_minute_capture():
    from core.evidence.audio_policy import AudioAcquisitionPolicy

    with pytest.raises(ValueError, match="max_clip_seconds"):
        AudioAcquisitionPolicy(enabled=True, max_clip_seconds=301, retention_policy="7d", storage_prefix="object://clips/")
