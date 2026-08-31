# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shadow-mode confidence model — docs/prompt.md phase 9."""
from __future__ import annotations

from core.intel import confidence


def test_source_reliability_ranks_official_above_unofficial():
    assert confidence.source_reliability("official_api") > confidence.source_reliability("unofficial")
    assert confidence.source_reliability("unknown_policy") == 0.5


def test_observation_freshness_decays_with_age_but_floors():
    fresh = confidence.observation_freshness(0)
    old = confidence.observation_freshness(48 * 3600)
    assert fresh > old
    assert old >= 0.2


def test_rule_strength_known_vs_unknown_rule():
    assert confidence.rule_strength("spoof_teleport") == 0.85
    assert confidence.rule_strength("nonexistent_rule") == 0.5


def test_persistence_rewards_more_samples_and_duration():
    thin = confidence.persistence(sample_count=1, duration_s=60)
    strong = confidence.persistence(sample_count=10, duration_s=3600)
    assert strong > thin


def test_coverage_quality_drops_under_jamming():
    clear = confidence.coverage_quality(0.0)
    jammed = confidence.coverage_quality(0.9)
    assert clear > jammed
    assert jammed >= 0.2


def test_contradicting_evidence_penalty_never_reaches_zero():
    assert confidence.contradicting_evidence_penalty(0) == 1.0
    assert confidence.contradicting_evidence_penalty(10) >= 0.1


def test_combine_is_mean_of_supplied_components_only():
    score = confidence.combine("ais_gap", rule_strength=0.6, source_reliability=1.0)
    assert score.value == 0.8
    assert score.rule_id == "ais_gap"
    assert set(score.components) == {"rule_strength", "source_reliability"}


def test_combine_with_no_components_is_neutral_default():
    score = confidence.combine("unknown")
    assert score.value == 0.5
    assert score.components == {}


def test_as_metadata_shape():
    score = confidence.combine("ais_gap", rule_strength=0.6)
    meta = score.as_metadata()
    assert meta["confidence"] == 0.6
    assert meta["rule_id"] == "ais_gap"
    assert meta["classification_version"] == confidence.CLASSIFICATION_VERSION
    assert meta["confidence_components"] == {"rule_strength": 0.6}
