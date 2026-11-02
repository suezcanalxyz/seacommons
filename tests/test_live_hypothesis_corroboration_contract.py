# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression for the public maritime hypothesis corroboration contract.

A published hypothesis can be mature enough for review without having two
independent evidence lineages. Its evidence_stage must never by itself
upgrade a Live claim to multi-source corroboration.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./core/data/test_live_hypothesis_corroboration.db")
os.environ.setdefault("RUNTIME_PROFILE", "operational")


@pytest.mark.parametrize(
    ("evidence_stage", "independent_source_count", "expected_corroborated"),
    [
        ("corroborated", None, False),
        ("corroborated", 1, False),
        ("corroborated", 2, True),
        ("assessed", 2, True),
    ],
)
def test_published_hypothesis_live_verification_requires_independent_lineages(
    monkeypatch, evidence_stage, independent_source_count, expected_corroborated
):
    from core.intel import hypothesis_publication
    from core.live.feed import _published_security_hypothesis_features

    props = {
        "id": "hyp:live-corroboration-regression",
        "episode_id": "episode:live-corroboration-regression",
        "hypothesis_type": "dark_transit",
        "title": "AIS gap requiring independent review",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_stage": evidence_stage,
        "reason_codes": [],
        "caveats": [],
    }
    if independent_source_count is not None:
        props["independent_source_count"] = independent_source_count

    monkeypatch.setattr(
        hypothesis_publication,
        "public_hypothesis_collection",
        lambda limit: {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [14.0, 35.0]},
                "properties": props,
            }],
        },
    )

    features = _published_security_hypothesis_features(limit=10)
    assert len(features) == 1
    public = features[0]["properties"]
    assert public["corroborated"] is expected_corroborated
    assert public["verification_status"] == (
        "multi_source_corroborated" if expected_corroborated else "derived"
    )
    assert ("corroborated" in public["facets"]) is expected_corroborated
    assert public["evidence_stage"] == evidence_stage
    assert "independence_groups" not in public
    if expected_corroborated:
        assert public["independent_source_count"] == 2
    else:
        assert public.get("independent_source_count", 0) < 2
