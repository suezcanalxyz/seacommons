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
    from core.db.models import InvestigationHypothesisDB
    from core.db.session import session_scope
    with session_scope() as db:
        db.query(InvestigationHypothesisDB).delete()
    with intel_store._lock:
        intel_store._events.clear(); intel_store._seen.clear()
    yield
    with session_scope() as db:
        db.query(InvestigationHypothesisDB).delete()


def _publish_spoofing_hypothesis(*, independent_news: bool = False):
    now = datetime.now(timezone.utc).isoformat()
    for event_id, lat, lon in (("spoof-a", 35.0, 14.0), ("spoof-b", 35.1, 14.1)):
        is_news = independent_news and event_id == "spoof-b"
        intel_store.add(IntelEvent(
            id=event_id, type="news" if is_news else "ais_anomaly", severity="high",
            lat=lat, lon=lon, title="independent report" if is_news else "raw spoof detector output",
            source="Independent maritime news" if is_news else "mda",
            timestamp_utc=now, linked_mmsi="211879870",
            metadata={
                "anomaly_type": "position_jump",
                "maritime_domain": "grey_zone",
                "publication_status": "published",
                "source_policy": "operator_published",
                **({"transport": "rss"} if is_news else {}),
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
    assert feature["properties"]["verification_status"] == "single_source_multi_indicator"
    assert feature["properties"]["corroborated"] is False
    assert "corroborated" not in feature["properties"]["facets"]
    assert feature["properties"]["independent_source_count"] == 1
    assert "mmsi" not in feature["properties"]
    assert "linked_mmsi" not in feature["properties"]


def test_live_hypothesis_requires_independent_news_for_corroborated_facet():
    hypothesis_id = _publish_spoofing_hypothesis(independent_news=True)
    collection = public_signal_collection(mode="maritime", days=1, limit=50)
    feature = next(
        f for f in collection["features"]
        if f["properties"].get("hypothesis_id") == hypothesis_id
    )
    props = feature["properties"]
    assert props["verification_status"] == "multi_source_corroborated"
    assert props["corroborated"] is True
    assert "corroborated" in props["facets"]
    assert props["independent_source_count"] == 2
    assert set(props["independence_groups"]) == {
        "ais_sensor_lineage", "secondary_news_reporting",
    }
    assert "mmsi" not in props
    assert "linked_mmsi" not in props
