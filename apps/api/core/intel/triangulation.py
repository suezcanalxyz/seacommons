# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-source corroboration for SAR distress signals.

Five independent channels already write into the shared `intel_store`:
Alarm Phone (first-party scrape + per-image OCR consensus), the official X
API, news, Mastodon, and AIS-derived spikes (sudden stop, rescue cluster,
NGO search pattern, loiter). None of them reference one another today —
"consensus" only ever meant agreement between OCR passes on the *same*
image. This module adds the missing layer: when two or more *independent*
channels report the same place and time window, the corresponding distress
event is upgraded from `unverified_public_source` to
`multi_source_corroborated`.

This is deliberately a separate, small module rather than an extension of
`core.anomaly.correlation.CorrelationEngine`, which fuses physical-threat
sensor channels (infrasound, seismic, ADS-B, GNSS spoofing) under a
different channel map and different classifications. The weighted,
time-windowed fusion *pattern* is shared; the channels and thresholds are
SAR-specific.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import config as _cfg
from core.intel.store import IntelEvent, intel_store

logger = logging.getLogger(__name__)

# Two events reported through the SAME channel near the same place/time are
# one witness repeating itself, not corroboration — only distinct channel
# types contribute to the confidence sum below.
CHANNEL_WEIGHTS: dict[str, float] = {
    "alarmphone_text": 0.35,
    "media_ocr_consensus": 0.30,
    "official_x_api": 0.30,
    "news": 0.20,
    "mastodon": 0.15,
    "bluesky": 0.15,
    "ais_spike": 0.40,
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return r_km * 2 * math.asin(math.sqrt(max(0.0, a)))


def _parse_timestamp(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def channel_of(event: IntelEvent) -> Optional[str]:
    """Classify an event's independent source channel.

    Returns None for events that cannot participate in triangulation
    (no coordinates, or a type this module does not recognise).

    Channel is derived from source-provenance metadata rather than
    `event.type` alone: `news_monitor` and `mastodon_monitor` both promote
    high-severity posts to `type="distress"` (the same type Alarm Phone/X
    events use), so `event.type` alone cannot tell those escalated events
    apart from an Alarm Phone/X report. Checking the provenance metadata
    each collector always sets (`transport`/`platform`) first avoids
    misattributing them to the wrong channel.
    """
    if event.lat is None or event.lon is None:
        return None
    if event.type == "ais_spike":
        return "ais_spike"
    if event.type == "news" or event.metadata.get("transport") == "rss":
        return "news"
    if event.type == "mastodon" or event.metadata.get("platform") == "mastodon":
        return "mastodon"
    if event.type == "bluesky" or event.metadata.get("platform") == "bluesky":
        return "bluesky"
    if event.type in ("twitter", "distress"):
        if event.metadata.get("coordinate_source") == "media_ocr_consensus":
            return "media_ocr_consensus"
        if event.metadata.get("source_policy") == "official_api":
            return "official_x_api"
        return "alarmphone_text"
    return None


def evaluate(new_event: IntelEvent) -> Optional[dict[str, Any]]:
    """Look for independent corroboration of `new_event` among recent events.

    Safe to call for every ingested event: a no-op when the event has no
    coordinates, or when fewer than two distinct channels agree within the
    configured radius and time window. On corroboration, merges
    `verification_status`, `corroborating_sources` and
    `corroboration_confidence` into the event's metadata in place (via
    `intel_store.update_metadata`) and returns that summary; returns None
    otherwise.
    """
    channel = channel_of(new_event)
    if channel is None:
        return None

    new_ts = _parse_timestamp(new_event.timestamp_utc) or datetime.now(timezone.utc)
    radius_km = _cfg.SAR_TRIANGULATION_RADIUS_KM
    window_s = _cfg.SAR_TRIANGULATION_WINDOW_MIN * 60
    threshold = _cfg.SAR_TRIANGULATION_THRESHOLD

    contributing: dict[str, IntelEvent] = {channel: new_event}
    linked_mmsi = new_event.linked_mmsi or ""

    for candidate in intel_store.events(limit=600):
        if candidate.id == new_event.id:
            continue
        other_channel = channel_of(candidate)
        if other_channel is None or other_channel in contributing:
            continue
        other_ts = _parse_timestamp(candidate.timestamp_utc)
        if other_ts is None or abs((new_ts - other_ts).total_seconds()) > window_s:
            continue
        if _haversine_km(new_event.lat, new_event.lon, candidate.lat, candidate.lon) > radius_km:
            continue
        contributing[other_channel] = candidate
        if not linked_mmsi and candidate.linked_mmsi:
            linked_mmsi = candidate.linked_mmsi

    if len(contributing) < 2:
        return None

    confidence = round(sum(CHANNEL_WEIGHTS.get(c, 0.0) for c in contributing), 4)
    if confidence < threshold:
        return None

    summary: dict[str, Any] = {
        "verification_status": "multi_source_corroborated",
        "corroborating_sources": sorted(contributing.keys()),
        "corroboration_confidence": confidence,
    }
    intel_store.update_metadata(
        new_event.id,
        metadata=summary,
        linked_mmsi=linked_mmsi or None,
    )
    logger.info(
        "Triangulation: event %s corroborated by %s (confidence=%.2f)",
        new_event.id,
        sorted(contributing.keys()),
        confidence,
    )
    return summary


def test_triangulation() -> None:
    """Unit test — pure in-memory, no network or DB required."""
    from core.intel.store import IntelStore

    store = IntelStore()
    original_store = intel_store
    # evaluate()/channel_of() look up `intel_store` from this module's globals
    # at call time, so swapping the binding redirects them to a scratch store.
    globals()["intel_store"] = store

    counter = {"n": 0}

    def make(event_type: str, lat: float, lon: float, ts: str, **metadata: Any) -> IntelEvent:
        counter["n"] += 1
        # distinct title so IntelEvent.content_hash() does not dedup events
        # that otherwise share every other field.
        ev = IntelEvent(type=event_type, severity="high", lat=lat, lon=lon,
                         title=f"synthetic-{counter['n']}", timestamp_utc=ts, metadata=metadata)
        added = store.add(ev)
        assert added, f"synthetic event {counter['n']} was unexpectedly deduplicated"
        return ev

    # intel_store.events() only returns events within its default 30-day
    # window, so synthetic timestamps must be recent, not a fixed past date.
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    base_ts = now.isoformat()
    plus_20min_ts = (now + timedelta(minutes=20)).isoformat()

    # Test 1: a single Alarm Phone report alone is not corroborated.
    solo = make("twitter", 35.50, 12.60, base_ts, source_policy="official_site_embed")
    assert evaluate(solo) is None
    assert solo.verification_status() == "unverified_public_source"

    # Test 2: an AIS rescue cluster near the same place/time corroborates it.
    ais = make("ais_spike", 35.505, 12.605, plus_20min_ts)
    ais.linked_mmsi = "123456789"
    result = evaluate(solo)
    assert result is not None, "expected corroboration from ais_spike + alarmphone_text"
    assert result["verification_status"] == "multi_source_corroborated"
    assert set(result["corroborating_sources"]) == {"alarmphone_text", "ais_spike"}
    assert solo.linked_mmsi == "123456789"

    # Test 3: a second event from the SAME channel does not add confidence.
    same_channel = make("twitter", 35.51, 12.61, base_ts, source_policy="official_site_embed")
    r2 = evaluate(same_channel)
    assert r2 is not None  # still corroborated by the earlier ais_spike
    assert set(r2["corroborating_sources"]) == {"alarmphone_text", "ais_spike"}

    # Test 4: far away in space does not corroborate.
    make("news", 10.0, 10.0, base_ts)
    solo_far = make("mastodon", -10.0, -10.0, base_ts)
    assert evaluate(solo_far) is None

    # Test 5: severity-escalated events (type="distress") from news/mastodon
    # must still classify by provenance metadata, not fall through to
    # alarmphone_text/official_x_api by accident.
    assert channel_of(make("distress", 20.0, 20.0, base_ts, transport="rss")) == "news"
    assert channel_of(make("distress", 21.0, 21.0, base_ts, platform="mastodon")) == "mastodon"

    globals()["intel_store"] = original_store
    print("Triangulation unit tests passed.")


if __name__ == "__main__":
    test_triangulation()
