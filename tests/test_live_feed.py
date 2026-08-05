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
from core.intel.x_media_utils import consensus_ocr_coordinate
from core.intel.geoextract import (
    extract_numeric_coords,
    extract_relative_coords,
    is_direct_distress_call,
    is_resolved_distress,
)
from core.intel import lifecycle
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


def test_public_projection_exposes_repost_thread_including_its_own_note() -> None:
    # Unlike the event's own `text` (may originate from a private caller who
    # never consented to publication), a thread_reposts note only ever comes
    # from the tracked account's own public reply/quote to its own tweet —
    # already readable by anyone on X — so it is NOT stripped here.
    event = IntelEvent(
        id="public02",
        type="distress",
        severity="high",
        lat=35.5,
        lon=14.1,
        title="Reported maritime distress",
        source="alarm_phone",
        url="https://x.com/i/web/status/1",
        metadata={
            "is_distress": True,
            "source_policy": "official_api",
            "repost_count": 2,
            "last_repost_at": "2026-08-04T12:00:00+00:00",
            "thread_reposts": [
                {"tweet_id": "2", "posted_at": "2026-08-04T11:00:00+00:00",
                 "url": "https://x.com/i/web/status/2", "kind": "repost"},
                {"tweet_id": "3", "posted_at": "2026-08-04T12:00:00+00:00",
                 "url": "https://x.com/i/web/status/3", "kind": "quote",
                 "note": "Rescued to #Lampedusa! Everyone arrived safely."},
            ],
        },
    )
    feature = _public_intel_feature(event)
    assert feature is not None
    props = feature["properties"]
    assert props["repost_count"] == 2
    assert props["last_repost_at"] == "2026-08-04T12:00:00+00:00"
    assert len(props["thread_reposts"]) == 2
    assert props["thread_reposts"][0].get("note") is None
    assert props["thread_reposts"][1]["kind"] == "quote"
    assert props["thread_reposts"][1]["url"] == "https://x.com/i/web/status/3"
    assert props["thread_reposts"][1]["note"] == "Rescued to #Lampedusa! Everyone arrived safely."


def test_public_projection_shows_an_area_polygon_when_no_precise_point_exists() -> None:
    polygon = {"type": "Polygon", "coordinates": [[[14.0, 35.0], [14.1, 35.0], [14.1, 35.1], [14.0, 35.0]]]}
    event = IntelEvent(
        id="public03",
        type="twitter",
        severity="high",
        lat=35.05,
        lon=14.05,
        title="Reported maritime distress",
        source="alarm_phone",
        url="https://x.com/i/web/status/1",
        metadata={
            "is_distress": True,
            "source_policy": "official_api",
            "coordinate_source": "region_area",
            "area_geojson": polygon,
            "area_confidence": "area_low_confidence",
        },
    )
    feature = _public_intel_feature(event)
    assert feature is not None
    assert feature["geometry"] == polygon
    assert feature["properties"]["location_precision"] == "area_low_confidence"


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


def test_resolved_distress_ignores_a_rescue_mention_inside_an_ongoing_pushback() -> None:
    # Real Alarm Phone report (2026-07-29): a rescue is only one step in a
    # still-active rights violation (forced-return risk, refused
    # disembarkation) — the bare word "rescued" must not short-circuit this
    # to "resolved". This is the exact text that showed as a wrongly-green
    # "resolved" marker on the live map before the fix.
    assert not is_resolved_distress(
        "🚨People at risk of being forced back to #Egypt. This group was over "
        "night rescued by Merchant Vessel Safi Lion. Even though #Crete is "
        "clearly the closest port, @HCoastGuard refuses to disembark the "
        "people in #Greece! This is outrageous!"
    )


def test_resolved_distress_still_recognizes_a_clean_rescue() -> None:
    assert is_resolved_distress(
        "Rescued!! Thank you #OceanViking for rescuing the 14 people who "
        "called us when in distress on a small boat in international waters."
    )
    assert is_resolved_distress("The group was rescued and everyone is now safe.")


def test_lifecycle_recomputes_from_text_instead_of_trusting_stale_incident_status() -> None:
    # A stored incident_status="resolved" — the exact value the OLD,
    # over-broad is_resolved_distress() would have baked in at ingestion for
    # the pushback report above — must no longer short-circuit the lifecycle
    # colour. Only the live-recomputed text classification governs it now,
    # so a classifier fix or a same-tweet duplicate from a source that never
    # set the field (twikit does not) can never disagree with it.
    now = datetime.fromisoformat("2026-07-29T12:00:00+00:00")
    event = IntelEvent(
        id="pushback01",
        type="twitter",
        severity="high",
        title="Alarm Phone",
        text=(
            "🚨People at risk of being forced back to #Egypt. This group was "
            "over night rescued by Merchant Vessel Safi Lion. Even though "
            "#Crete is clearly the closest port, @HCoastGuard refuses to "
            "disembark the people in #Greece! This is outrageous!"
        ),
        source="Alarm Phone",
        timestamp_utc="2026-07-29T05:58:12+00:00",
        metadata={"incident_status": "resolved"},
    )
    assert lifecycle.distress_lifecycle(event, now=now, same_source=[]) == "active"


def test_resolution_signal_ignores_a_single_shared_generic_word() -> None:
    # Real false positive: this Egypt pushback report and a totally
    # unrelated "Rescued!! Thank you OceanViking..." post from the same
    # source share only the single generic word "rescued" — that alone must
    # not mark the Egypt report resolved.
    egypt = IntelEvent(
        id="pushback02",
        type="twitter",
        severity="high",
        title="Alarm Phone",
        text=(
            "🚨People at risk of being forced back to #Egypt. This group was "
            "over night rescued by Merchant Vessel Safi Lion. Even though "
            "#Crete is clearly the closest port, @HCoastGuard refuses to "
            "disembark the people in #Greece! This is outrageous!"
        ),
        source="Alarm Phone",
        timestamp_utc="2026-07-29T05:58:12+00:00",
    )
    unrelated_rescue = IntelEvent(
        id="oceanviking01",
        type="twitter",
        severity="low",
        title="Alarm Phone",
        text=(
            "Rescued!! Thank you #OceanViking for rescuing the 14 people "
            "who called us when in distress on a small boat in "
            "international waters."
        ),
        source="Alarm Phone",
        timestamp_utc="2026-07-31T10:37:23+00:00",
    )
    assert lifecycle.has_resolution_signal(egypt, [unrelated_rescue]) is False


def test_self_reply_marks_the_incident_resolved_without_keyword_overlap() -> None:
    # A structurally-verified self-reply (twikit_monitor._check_self_replies
    # only threads a reply from the SAME author, linked via X's own
    # in_reply_to) needs no keyword-overlap check the way cross-event
    # resolution matching does — it's already proven to be about this exact
    # incident, unlike two independently-worded posts that merely share
    # vocabulary (see test_resolution_signal_ignores_a_single_shared_generic_word).
    event = IntelEvent(
        id="lampedusa01",
        type="twitter",
        severity="high",
        title="Alarm Phone",
        text="🆘 52 people in grave distress! We informed authorities in #Italy and #Malta.",
        source="Alarm Phone",
        timestamp_utc="2026-07-30T08:57:00+00:00",
        metadata={
            "thread_reposts": [
                {
                    "tweet_id": "2083234981816512957",
                    "posted_at": "2026-07-31T09:00:00+00:00",
                    "url": "https://x.com/i/web/status/2083234981816512957",
                    "kind": "reply",
                    "note": "Rescued to #Lampedusa! The 52 people have safely arrived in Italy.",
                }
            ]
        },
    )
    assert lifecycle.has_own_reply_resolution(event) is True
    now = datetime.fromisoformat("2026-07-31T12:00:00+00:00")
    assert lifecycle.distress_lifecycle(event, now=now, same_source=[]) == "resolved"


def test_thread_reposts_without_a_resolved_note_stay_active() -> None:
    event = IntelEvent(
        id="lampedusa02",
        type="twitter",
        severity="high",
        title="Alarm Phone",
        text="🆘 52 people in grave distress! We informed authorities in #Italy and #Malta.",
        source="Alarm Phone",
        timestamp_utc="2026-07-30T08:57:00+00:00",
        metadata={
            "thread_reposts": [
                {"tweet_id": "1", "posted_at": "2026-07-30T09:00:00+00:00",
                 "url": "https://x.com/i/web/status/1", "kind": "reply",
                 "note": "Any update on this??"},
            ]
        },
    )
    assert lifecycle.has_own_reply_resolution(event) is False


def test_resolution_signal_still_fires_on_genuinely_matching_follow_up() -> None:
    original = IntelEvent(
        id="boat01",
        type="twitter",
        severity="high",
        title="Alarm Phone",
        text="🆘 47 people in distress aboard the vessel Zenobia near Lampedusa.",
        source="Alarm Phone",
        timestamp_utc="2026-07-29T05:00:00+00:00",
    )
    follow_up = IntelEvent(
        id="boat01-followup",
        type="twitter",
        severity="low",
        title="Alarm Phone",
        text="Update: all 47 people aboard the Zenobia near Lampedusa were rescued and are now safe.",
        source="Alarm Phone",
        timestamp_utc="2026-07-29T09:00:00+00:00",
    )
    assert lifecycle.has_resolution_signal(original, [follow_up]) is True


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
    # Crete's gazetteer base is just off the island's south coast (not its
    # landmass centroid — see geoextract.py), so "50 km south" lands further
    # south than the old landmass-centroid-based expectation.
    assert 34.39 < lat < 34.41
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
    # Crete's gazetteer base is just off the island's south coast (not its
    # landmass centroid — see geoextract.py), so "50 km south" lands further
    # south than the old landmass-centroid-based expectation.
    assert 34.39 < lat < 34.41
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


def test_enrich_location_clears_stale_area_on_upgrade_to_a_real_point() -> None:
    # Real production bug: an event ingested from a bare place match gets a
    # real sea-only area_geojson polygon (core.intel.area_extract). When OCR
    # later finds the actual position and upgrades it via enrich_location,
    # the old polygon must not keep silently overriding the new point --
    # public_geometry_and_precision always prefers area_geojson when
    # present, so a leftover stale one makes an "active without drift"-
    # looking event show a huge obsolete area forever, even though the
    # underlying lat/lon (and drift) are already correct.
    store = IntelStore()
    event = IntelEvent(
        id="ocrarea01",
        type="twitter",
        severity="high",
        title="Boat off #Libya",
        source="alarm_phone",
        lat=31.5, lon=17.5,  # the area's own centroid, exactly as _ingest sets it
        metadata={
            "coordinate_source": "region_area",
            "area_geojson": {"type": "Polygon", "coordinates": [[[17.0, 31.0], [18.0, 31.0], [18.0, 32.0], [17.0, 31.0]]]},
            "area_confidence": "area_low_confidence",
        },
    )
    assert store.add(event) is True
    assert store.enrich_location(
        event.id,
        lat=32.5,
        lon=17.8,
        metadata={"coordinate_source": "media_ocr_text", "location_uncertainty_m": 1500},
    ) is True
    assert "area_geojson" not in event.metadata
    assert "area_confidence" not in event.metadata
    assert event.lat == 32.5 and event.lon == 17.8


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


def test_drift_not_shown_for_resolved_or_archived_incidents(monkeypatch) -> None:
    # Once an incident is resolved (or has gone stale/archived), the search
    # is over -- an active-looking pulsing drift cone still on the map reads
    # as "still adrift, still searching", which is exactly wrong.
    from datetime import timezone

    from core.api.routes.live import public_drift_collection

    now_iso = datetime.now(timezone.utc).isoformat()
    active_event = IntelEvent(
        id="drift-active", type="distress", severity="high",
        lat=35.0, lon=14.0, title="MAYDAY still adrift", source="alarm_phone",
        timestamp_utc=now_iso,
        metadata={"is_distress": True, "source_policy": "official_api", "drift_job_id": "job-active"},
    )
    resolved_event = IntelEvent(
        id="drift-resolved", type="distress", severity="high",
        lat=35.0, lon=14.0, title="Rescued! Everyone is safe.", source="alarm_phone",
        timestamp_utc=now_iso,
        metadata={"is_distress": True, "source_policy": "official_api", "drift_job_id": "job-resolved"},
    )
    monkeypatch.setattr("core.api.routes.live.intel_store.persisted_events", lambda **_kwargs: [])
    monkeypatch.setattr(
        "core.api.routes.live.intel_store.events",
        lambda **_kwargs: [active_event, resolved_event],
    )
    fake_drift = {
        "trajectory": {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[14.0, 35.0], [14.1, 35.1]]},
            "properties": {},
        },
        "cone_24h": None,
        "impact_point": {},
        "metadata": {"published": True},
    }
    monkeypatch.setattr("core.db.store.get_drift", lambda job_id: fake_drift)
    monkeypatch.setattr("core.db.store.list_drift_jobs_for_event", lambda event_id: [])
    monkeypatch.setattr("core.api.routes.live._is_publishable_live_drift", lambda drift: True)

    collection = public_drift_collection(limit=50)
    event_ids = {f["properties"]["intel_event_id"] for f in collection["features"]}
    assert "drift-active" in event_ids
    assert "drift-resolved" not in event_ids


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
        public_ngo = client.get("/api/v1/live/ngo-vessels")
        public_platforms = client.get("/api/v1/live/platforms")
        internal_feed = client.get("/api/v1/intel")
        internal_ngo = client.get("/api/v1/intel/ngo")
        assert public_feed.status_code == 200
        assert public_feed.json()["meta"]["schema"] == "org.seacommons.live-feed/v1"
        assert public_drifts.status_code == 200
        assert public_drifts.json()["meta"]["schema"] == "org.seacommons.live-drift/v1"
        assert public_archives.status_code == 200
        source_payload = public_sources.json()
        assert source_payload["collector"]["browser_independent"] is True
        assert all(source["type"] != "ais" for source in source_payload["sources"])
        assert public_ngo.status_code == 200
        assert public_ngo.json()["type"] == "FeatureCollection"
        assert public_platforms.status_code == 200
        assert public_platforms.json()["type"] == "FeatureCollection"
        assert internal_feed.status_code == 401
        assert internal_ngo.status_code == 401
    finally:
        config.AUTH_ENABLED = previous
