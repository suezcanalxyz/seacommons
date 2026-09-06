from __future__ import annotations

from core.db import models


def test_maritime_episode_model_contract() -> None:
    assert hasattr(models, "MaritimeEpisodeDB"), "MaritimeEpisodeDB model is required"
    table = models.MaritimeEpisodeDB.__table__
    expected = {
        "episode_id", "episode_family", "subject_ids", "start_at", "end_at",
        "observation_ids", "feature_ids", "independence_groups",
        "verification_status", "behaviour_context", "alternative_explanations",
        "evidence_fingerprint", "method_version", "status", "created_at", "updated_at",
    }
    assert expected <= set(table.columns.keys())
    assert table.c.episode_id.primary_key


def test_hypothesis_episode_link_is_nullable_for_legacy_rows() -> None:
    table = models.InvestigationHypothesisDB.__table__
    assert "episode_id" in table.columns
    assert table.c.episode_id.nullable is True
