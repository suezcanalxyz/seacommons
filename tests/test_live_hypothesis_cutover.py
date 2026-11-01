from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.intel.hypothesis import new_hypothesis, transition
from core.intel.hypothesis_store import save_hypothesis
from core.intel.store import IntelEvent, intel_store
from core.live.feed import public_signal_collection


@pytest.fixture(autouse=True)
def _fresh_hypotheses():
    from core.db.models import InvestigationHypothesisDB, MaritimeEpisodeDB
    from core.db.session import session_scope
    with session_scope() as db:
        db.query(InvestigationHypothesisDB).delete()
        db.query(MaritimeEpisodeDB).filter(MaritimeEpisodeDB.episode_id == "episode:test:spoof").delete()
    with intel_store._lock:
        intel_store._events.clear(); intel_store._seen.clear()
    yield
    with session_scope() as db:
        db.query(InvestigationHypothesisDB).delete()
        db.query(MaritimeEpisodeDB).filter(MaritimeEpisodeDB.episode_id == "episode:test:spoof").delete()


def _publish_spoofing_hypothesis(*, independent_news: bool = False, news_derived_from_ais: bool = False):
    now = datetime.now(timezone.utc).isoformat()
    for event_id, lat, lon in (("spoof-a", 35.0, 14.0), ("spoof-b", 35.1, 14.1)):
        is_news = independent_news and event_id == "spoof-b"
        intel_store.add(IntelEvent(
            id=event_id, type="news" if is_news else "ais_anomaly", severity="high",
            lat=lat, lon=lon, title="independent report" if is_news else f"raw spoof detector output {event_id}",
            source="Independent maritime news" if is_news else "mda",
            timestamp_utc=now, linked_mmsi="211879870",
            metadata={
                "anomaly_type": "position_jump",
                "maritime_domain": "grey_zone",
                "publication_status": "published",
                "source_policy": "operator_published",
                **({"transport": "rss", **({"source_lineage": "ais_sensor_lineage"} if news_derived_from_ais else {})} if is_news else {}),
            },
        ), dedup_key=event_id)
    h = new_hypothesis(
        "hyp:test:spoof-published", "position_spoofing",
        ("subj:mmsi:211879870",), episode_id="episode:test:spoof",
    )
    h = replace(
        h, reason_codes=("position_jump",),
        evidence_links=("spoof-a", "spoof-b"), evidence_stage="corroborated",
    )
    for state in ("collecting", "review_ready", "assessed", "published"):
        h = transition(h, state, actor="test")
    save_hypothesis(h)
    if independent_news:
        # Persist the producer's canonical evidence-lineage decision. The
        # public hypothesis must never infer independence from stage/count.
        from core.intel.fusion import verification_for_event_ids
        from core.intel.episode_store import save_episode

        verification, groups, _evidence_count = verification_for_event_ids(
            list(h.evidence_links)
        )
        save_episode({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [14.1, 35.1]},
            "properties": {
                "episode_id": h.episode_id,
                "episode_family": "position_integrity",
                "subject_ids": ["subj:mmsi:211879870"],
                "observation_ids": list(h.evidence_links),
                "first_observed_at": now,
                "last_observed_at": now,
                "independence_groups": groups,
                "verification_status": verification,
                "analysis_state": "evidence",
                "publication_state": "published",
            },
        })
    return h.hypothesis_id


def test_live_security_uses_published_hypothesis_not_raw_detector_events():
    hypothesis_id = _publish_spoofing_hypothesis()
    collection = public_signal_collection(mode="maritime", days=1, limit=50)
    features = collection["features"]
    ids = {feature["properties"]["id"] for feature in features}
    feature = next(
        f for f in features
        if f["properties"].get("hypothesis_id") == hypothesis_id
    )
    assert feature["properties"].get("episode_id") == feature["properties"]["id"]
    assert "intel:spoof-a" not in ids
    assert "intel:spoof-b" not in ids
    assert feature["properties"]["hypothesis_type"] == "position_spoofing"
    assert feature["properties"]["hypothesis_state"] == "published"
    assert feature["properties"]["visual_category"] == "spoofing"
    # Two AIS detector events can share one lineage. Assessment maturity
    # must not be presented as independent-source corroboration.
    assert feature["properties"]["verification_status"] == "derived"
    assert feature["properties"]["corroborated"] is False
    assert "mmsi" not in feature["properties"]
    assert "linked_mmsi" not in feature["properties"]


@pytest.mark.parametrize(
    ("lineages", "corroborated"),
    [
        ([], False),
        (["ais:provider-a", "ais:provider-a"], False),
        (["ais:provider-a", "news:provider-b"], True),
    ],
)
def test_published_hypothesis_corroboration_requires_independent_lineage(
    monkeypatch, lineages, corroborated,
):
    """A corroborated assessment stage alone cannot assert two sources."""
    from core.intel import hypothesis_publication
    from core.live.feed import _published_security_hypothesis_features

    now = datetime.now(timezone.utc).isoformat()
    feature = {
        "type": "Feature",
        "id": "hyp:test:lineage",
        "geometry": {"type": "Point", "coordinates": [14.1, 35.5]},
        "properties": {
            "id": "hyp:test:lineage",
            "hypothesis_type": "dark_transit",
            "timestamp_utc": now,
            "evidence_stage": "corroborated",
            "independence_groups": lineages,
            "reason_codes": ["ais_gap"],
        },
    }
    monkeypatch.setattr(
        hypothesis_publication,
        "public_hypothesis_collection",
        lambda limit: {"type": "FeatureCollection", "features": [feature]},
    )
    projected = _published_security_hypothesis_features(limit=10)
    assert len(projected) == 1
    props = projected[0]["properties"]
    assert props["evidence_stage"] == "corroborated"
    assert props["corroborated"] is corroborated
    assert props["verification_status"] == (
        "multi_source_corroborated" if corroborated else "derived"
    )
    assert ("corroborated" in props["facets"]) is corroborated
    # Internal lineage labels must not be leaked through the public feature.
    assert "independence_groups" not in props


@pytest.mark.parametrize(
    ("groups", "verification", "expected_count"),
    [
        (["ais_sensor_lineage", "ais"], "multi_source_corroborated", 0),
        (["ais_sensor_lineage", "news:independent"], "single_source_multi_indicator", 0),
        (["ais_sensor_lineage", "ais", "news:independent"], "multi_source_corroborated", 2),
    ],
)
def test_persisted_episode_independence_reaches_live_without_leaking_groups(
    groups, verification, expected_count,
):
    """The real publication boundary must carry the verified aggregate.

    A synthetic Feature with independence_groups alone cannot establish that
    the actual hypothesis projection passes lineage metadata downstream.
    """
    from core.intel.episode_store import save_episode
    from core.intel.hypothesis_publication import public_hypothesis_collection
    from core.live.feed import _published_security_hypothesis_features

    hypothesis_id = _publish_spoofing_hypothesis()
    now = datetime.now(timezone.utc).isoformat()
    save_episode({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [14.1, 35.1]},
        "properties": {
            "episode_id": "episode:test:spoof",
            "episode_family": "position_integrity",
            "subject_ids": ["subj:mmsi:211879870"],
            "observation_ids": ["spoof-a", "spoof-b"],
            "first_observed_at": now,
            "last_observed_at": now,
            "independence_groups": groups,
            "verification_status": verification,
            "analysis_state": "evidence",
            "publication_state": "published",
        },
    })
    collection = public_hypothesis_collection(limit=20)
    projected = next(
        f for f in collection["features"]
        if f["properties"].get("hypothesis_id") == hypothesis_id
    )
    props = projected["properties"]
    assert props.get("independent_source_count", 0) == expected_count
    assert "independence_groups" not in props

    live = _published_security_hypothesis_features(limit=20)
    published = next(
        f for f in live if f["properties"].get("hypothesis_id") == hypothesis_id
    )["properties"]
    assert published["corroborated"] is (expected_count >= 2)
    assert published["verification_status"] == (
        "multi_source_corroborated" if expected_count >= 2 else "derived"
    )
    assert "independence_groups" not in published


def test_independent_news_corroborates_only_with_canonical_episode_lineage():
    hypothesis_id = _publish_spoofing_hypothesis(independent_news=True)
    collection = public_signal_collection(mode="maritime", days=1, limit=50)
    props = next(
        f["properties"] for f in collection["features"]
        if f["properties"].get("hypothesis_id") == hypothesis_id
    )
    assert props["verification_status"] == "multi_source_corroborated"
    assert props["corroborated"] is True
    assert "corroborated" in props["facets"]
    assert props["independent_source_count"] == 2
    assert "independence_groups" not in props
    assert "mmsi" not in props and "linked_mmsi" not in props


def test_republished_ais_news_cannot_upgrade_canonical_independence():
    hypothesis_id = _publish_spoofing_hypothesis(
        independent_news=True, news_derived_from_ais=True,
    )
    collection = public_signal_collection(mode="maritime", days=1, limit=50)
    props = next(
        f["properties"] for f in collection["features"]
        if f["properties"].get("hypothesis_id") == hypothesis_id
    )
    assert props["verification_status"] == "derived"
    assert props["corroborated"] is False
    assert "corroborated" not in props["facets"]
    assert props.get("independent_source_count", 0) < 2
    assert "independence_groups" not in props
