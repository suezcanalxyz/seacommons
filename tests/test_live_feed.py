from __future__ import annotations

import os
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///./core/data/test_live_feed.db")
os.environ.setdefault("RUNTIME_PROFILE", "operational")

from fastapi.testclient import TestClient

from core.api.main import app
from core.api.routes.live import (
    _approximate_public_point,
    _current_trajectory_estimate,
    _public_intel_feature,
    public_signal_collection,
)
from core.config import config
from core.ingestion.signal import DistressSignal
from core.intel.alarm_phone_monitor import (
    consensus_ocr_coordinate,
    parse_official_timeline,
    x_id_timestamp,
)
from core.intel.geoextract import (
    extract_numeric_coords,
    extract_relative_coords,
    is_direct_distress_call,
)
from core.intel.news_monitor import RSS_FEEDS
from core.intel.store import IntelEvent, IntelStore
from core.intel.twitter_monitor import TwitterMonitor


client = TestClient(app)


def test_public_projection_excludes_sensitive_content() -> None:
    event = IntelEvent(
        id="public01",
        type="distress",
        severity="high",
        lat=35.5,
        lon=14.1,
        title="Reported maritime distress",
        text="Private phone and free-form message",
        author="@private_handle",
        source="Public source",
        url="https://example.org/report",
        metadata={
            "is_distress": True,
            "private_note": "must not leak",
            "source_policy": "official_api",
        },
    )
    feature = _public_intel_feature(event)
    assert feature is not None
    assert feature["properties"]["text"] == ""
    assert "author" not in feature["properties"]
    assert "private_note" not in feature["properties"]
    assert feature["properties"]["publication_status"] == "published"


def test_manual_event_requires_explicit_publication() -> None:
    private = IntelEvent(
        id="manual01",
        type="manual",
        severity="high",
        lat=35.5,
        lon=14.1,
        title="Operator note",
        source="operator",
    )
    assert _public_intel_feature(private) is None
    private.metadata["publication_status"] = "published"
    assert _public_intel_feature(private) is not None


def test_computed_sar_products_never_enter_received_signal_feed() -> None:
    derived = IntelEvent(
        id="sar-model-01",
        type="sar_model",
        severity="medium",
        lat=35.578,
        lon=13.772,
        title="Computed SAR drift product",
        source="SeaCommons engine",
        metadata={"publication_status": "published"},
    )
    assert _public_intel_feature(derived) is None


def test_unofficial_scraper_records_never_enter_live() -> None:
    for metadata in (
        {"source_policy": "unofficial"},
        {"via": "nitter"},
        {"scrape_source": "alarmphone.org"},
    ):
        event = IntelEvent(
            id=f"blocked-{len(metadata)}",
            type="distress",
            severity="high",
            lat=35.5,
            lon=14.1,
            title="Persisted scraper report",
            source="legacy collector",
            metadata=metadata,
        )
        assert _public_intel_feature(event) is None


def test_only_official_social_transport_is_available() -> None:
    monitor = TwitterMonitor()
    assert monitor.configured is False
    assert all("nitter" not in feed["url"].lower() for feed in RSS_FEEDS)
    assert {feed["label"] for feed in RSS_FEEDS} == {
        "Alarm Phone",
        "Sea Watch",
        "SOS Méditerranée",
    }


def test_alarm_phone_first_party_timeline_parser() -> None:
    document = """
    <div class="ctf-item ctf-author-alarm_phone" id="2081334685649526892">
      <div class="ctf-tweet-content">
        <p class="ctf-tweet-text">
          SOS from 42 people at 35.50N 12.60E &amp; taking water.
        </p>
      </div>
    </div>
    """
    posts = parse_official_timeline(document)
    assert posts == [
        {
            "id": "2081334685649526892",
            "text": "SOS from 42 people at 35.50N 12.60E & taking water.",
            "created_at": x_id_timestamp("2081334685649526892"),
            "url": "https://x.com/alarm_phone/status/2081334685649526892",
        }
    ]
    assert posts[0]["created_at"].startswith("2026-07-26T")


def test_alarm_phone_official_site_policy_can_enter_live() -> None:
    event = IntelEvent(
        id="alarmphone01",
        type="twitter",
        severity="critical",
        title="Alarm Phone: reported distress",
        source="Alarm Phone",
        metadata={
            "source_policy": "official_site_embed",
            "is_distress": True,
        },
    )
    feature = _public_intel_feature(event)
    assert feature is not None
    assert feature["geometry"] is None
    assert feature["properties"]["verification_status"] == "unverified_public_source"


def test_direct_distress_call_classifier_is_conservative() -> None:
    assert is_direct_distress_call(
        "🆘 from 42 people in distress south of Crete. "
        "They have no fuel left and are drifting at sea."
    )
    assert is_direct_distress_call(
        "21 lives at risk. Rescue to a safe place is needed!"
    )
    assert is_direct_distress_call(
        "10 people are stuck on an islet. Two infants are in critical "
        "condition. We asked authorities for urgent medical assistance."
    )
    assert not is_direct_distress_call(
        "Where is the person stranded on Chafarinas Islands? Three days ago "
        "authorities claimed the person was transferred to the mainland."
    )
    assert not is_direct_distress_call(
        "There is no information about the whereabouts of this group. "
        "We fear another pushback."
    )
    assert not is_direct_distress_call(
        "The group was rescued and everyone is now safe."
    )


def test_intel_store_deduplicates_source_ids_and_content() -> None:
    store = IntelStore()
    event = IntelEvent(
        id="tweet01",
        type="twitter",
        severity="low",
        title="Same public report",
        text="Stable content",
        source="Alarm Phone",
        metadata={"tweet_id": "2081334685649526892"},
    )
    assert store.add(event, dedup_key="x:2081334685649526892") is True
    assert store.add(event) is False


def test_media_ocr_requires_numeric_consensus() -> None:
    passes = [
        "GPS position N 35°30' E 012°36'",
        "Position: N 35° 30' / E 012° 36'",
        "unrelated map labels Malta",
    ]
    assert consensus_ocr_coordinate(passes) == (35.5, 12.6)
    assert consensus_ocr_coordinate([passes[0], "unrelated map labels Malta"]) is None
    assert extract_numeric_coords("Malta") is None
    assert extract_numeric_coords("N 28° 06' / W 015° 24'") == (28.1, -15.4)


def test_relative_alarm_phone_location_is_geolocated_with_declared_offset() -> None:
    lat, lon = extract_relative_coords(
        "🆘 47 people were 50 km south of #Crete, Greece when they last spoke."
    )
    assert 34.78 < lat < 34.80
    assert 24.80 < lon < 24.82


def test_alarm_phone_screenshot_dmm_and_noisy_dms_are_parsed() -> None:
    assert extract_numeric_coords(
        "35 people in distress N 34° 37.377′, E 012° 35.525′"
    ) == (34.62295, 12.592083)
    assert extract_numeric_coords(
        '26 people N 34° 39° 36.887", E 012° 38° 36.341"'
    ) == (34.660246, 12.643428)
    assert extract_numeric_coords(
        '49 people N 35° Q4\' 17.6", E @11° 12\' 08"'
    ) == (35.071556, 11.202222)


def test_relative_location_can_reference_an_island_named_earlier() -> None:
    lat, lon = extract_relative_coords(
        "47 people south of #Crete. The group was 50 km south of the island when last contacted."
    )
    assert 34.78 < lat < 34.80
    assert 24.80 < lon < 24.82


def test_existing_event_can_be_enriched_with_media_location() -> None:
    store = IntelStore()
    event = IntelEvent(
        id="ocrplace01",
        type="twitter",
        severity="high",
        title="Public report with attached map",
        source="Alarm Phone",
    )
    assert store.add(event) is True
    metadata = {
        "coordinate_source": "media_ocr_consensus",
        "coordinate_review_status": "machine_consensus_unverified",
    }
    assert store.enrich_location(
        event.id,
        lat=35.5,
        lon=12.6,
        metadata=metadata,
    ) is True
    assert event.lat == 35.5
    assert event.lon == 12.6
    assert store.enrich_location(
        event.id,
        lat=36.0,
        lon=13.0,
        metadata=metadata,
    ) is False


def test_sensitive_public_position_is_stable_and_approximate() -> None:
    original = (35.5, 14.1)
    first = _approximate_public_point("signal-privacy-test", *original)
    second = _approximate_public_point("signal-privacy-test", *original)
    assert first == second
    assert first != original
    assert abs(first[0] - original[0]) < 0.03
    assert abs(first[1] - original[1]) < 0.03


def test_live_feed_merges_durable_alarm_phone_events_after_memory_eviction(monkeypatch) -> None:
    durable = IntelEvent(
        id="alarm-durable-01",
        timestamp_utc="2026-08-01T08:00:00+00:00",
        type="twitter",
        severity="high",
        lat=34.79,
        lon=24.81,
        title="Alarm Phone: direct distress",
        source="Alarm Phone",
        metadata={"source_policy": "official_site_embed", "is_distress": True},
    )
    monkeypatch.setattr("core.api.routes.live.intel_store.events", lambda **_kwargs: [])
    monkeypatch.setattr(
        "core.api.routes.live.intel_store.persisted_events",
        lambda **_kwargs: [durable],
    )
    collection = public_signal_collection(limit=50, days=1)
    assert [feature["properties"]["id"] for feature in collection["features"]] == [
        "intel:alarm-durable-01"
    ]
    assert collection["meta"]["durable_alarm_phone_candidates"] == 1


def test_current_position_uses_elapsed_time_on_sampled_trajectory() -> None:
    trajectory = {
        "geometry": {"type": "LineString", "coordinates": [[14.0, 35.0], [15.0, 36.0]]},
        "properties": {
            "timestamps_utc": ["2026-08-01T10:00:00Z", "2026-08-01T12:00:00Z"]
        },
    }
    estimate = _current_trajectory_estimate(
        trajectory,
        event_timestamp="2026-08-01T09:00:00Z",
        now=datetime.fromisoformat("2026-08-01T11:00:00+00:00"),
    )
    assert estimate is not None
    assert estimate["geometry"]["coordinates"] == [14.5, 35.5]
    assert estimate["properties"]["elapsed_hours"] == 2.0
    assert estimate["properties"]["trajectory_state"] == "interpolated"


def test_user_signal_is_private_by_default() -> None:
    signal = DistressSignal(
        source_channel="whatsapp",
        source_id="+390000000",
        raw_text="help",
        lat=35.5,
        lon=14.1,
    )
    assert signal.publication_status == "private"


def test_live_routes_remain_public_when_internal_reads_require_auth() -> None:
    previous = config.AUTH_ENABLED
    config.AUTH_ENABLED = True
    try:
        public_feed = client.get("/api/v1/live/signals")
        public_drifts = client.get("/api/v1/live/drifts")
        public_archives = client.get("/api/v1/live/archives")
        public_sources = client.get("/api/v1/live/sources")
        internal_feed = client.get("/api/v1/intel")
        assert public_feed.status_code == 200
        assert public_feed.json()["meta"]["schema"] == "org.seacommons.live-feed/v1"
        assert public_drifts.status_code == 200
        assert public_drifts.json()["meta"]["schema"] == "org.seacommons.live-drift/v1"
        assert public_archives.status_code == 200
        source_payload = public_sources.json()
        assert source_payload["collector"]["browser_independent"] is True
        assert all(source["type"] != "ais" for source in source_payload["sources"])
        assert internal_feed.status_code == 401
    finally:
        config.AUTH_ENABLED = previous
