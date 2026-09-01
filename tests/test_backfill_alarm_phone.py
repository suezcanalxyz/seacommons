# SPDX-License-Identifier: AGPL-3.0-or-later
"""Re-processing historical Alarm Phone events with the current pipeline."""
from __future__ import annotations

import re

from core.intel import backfill_alarm_phone as bf
from core.intel.x_media_utils import _syndication_token, _x_photo_urls


def test_syndication_token_is_stripped_base36() -> None:
    token = _syndication_token("1519480761749016577")
    assert token and re.fullmatch(r"[0-9a-z]+", token)
    assert "0" not in token and "." not in token
    # deterministic
    assert token == _syndication_token("1519480761749016577")


def test_photo_urls_harvest_media_and_quoted_and_filter_host() -> None:
    payload = {
        "mediaDetails": [{"media_url_https": "https://pbs.twimg.com/media/a.jpg"}],
        "photos": [
            {"url": "https://pbs.twimg.com/media/b.jpg"},
            {"url": "https://evil.example/c.jpg"},          # dropped: wrong host
            {"url": "https://pbs.twimg.com/media/a.jpg"},    # dropped: duplicate
        ],
        "quoted_tweet": {
            "mediaDetails": [{"media_url_https": "https://pbs.twimg.com/media/quote.jpg"}],
        },
    }
    urls = _x_photo_urls(payload)
    assert urls == [
        "https://pbs.twimg.com/media/a.jpg",
        "https://pbs.twimg.com/media/b.jpg",
        "https://pbs.twimg.com/media/quote.jpg",
    ]


def test_candidate_filters() -> None:
    class _Row:
        def __init__(self, source, meta, lat=None, lon=None):
            self.source, self.meta, self.lat, self.lon = source, meta, lat, lon

    assert bf._is_alarm_phone(_Row("alarm_phone", {}))
    assert bf._is_alarm_phone(_Row("someone", {"tracked_account": "alarm_phone"}))
    assert not bf._is_alarm_phone(_Row("MSF_Sea", {}))

    assert bf._is_weak_position(_Row("alarm_phone", {}, lat=None, lon=None))
    assert bf._is_weak_position(_Row("alarm_phone", {"coordinate_source": "region_area"}, lat=35.0, lon=14.0))
    assert not bf._is_weak_position(_Row("alarm_phone", {"coordinate_source": "post_text"}, lat=35.0, lon=14.0))


def test_run_is_dry_by_default(monkeypatch) -> None:
    monkeypatch.setattr(bf, "find_candidates", lambda limit: [
        {"id": "e1", "tweet_id": "1", "quoted_tweet_id": "", "media_urls": [],
         "timestamp_utc": "2026-08-01T00:00:00Z", "title": "boat", "persons": None, "vessel_type": None},
        {"id": "e2", "tweet_id": "2", "quoted_tweet_id": "", "media_urls": [],
         "timestamp_utc": "2026-08-02T00:00:00Z", "title": "boat2", "persons": None, "vessel_type": None},
    ])
    monkeypatch.setattr(bf, "resolve_position", lambda c: (35.5, 14.1, "text") if c["id"] == "e1" else None)
    applied: list = []
    monkeypatch.setattr(bf, "apply_position", lambda *a: applied.append(a))

    summary = bf.run(apply=False, limit=10, with_drift=False)
    assert summary == {"candidates": 2, "resolved": 1, "applied": 0, "drifts_queued": 0, "dry_run": True}
    assert applied == []


def test_run_apply_writes_but_freezes_drift_for_unverified_backfill(monkeypatch) -> None:
    """docs/fixes.md F-05: a backfilled image-derived position is always
    `machine_ocr_unverified`, so it is written back but must not seed a drift
    until live ingestion and backfill share one LocationEvidence policy."""
    monkeypatch.setattr(bf, "find_candidates", lambda limit: [
        {"id": "e1", "tweet_id": "1", "quoted_tweet_id": "", "media_urls": [],
         "timestamp_utc": "2026-08-01T00:00:00Z", "title": "boat", "persons": 12,
         "vessel_type": "rubber_boat", "lifecycle": "active"},
    ])
    monkeypatch.setattr(bf, "resolve_position", lambda c: (35.5, 14.1, "pin_landmark"))
    monkeypatch.setattr(bf, "apply_position", lambda *a: True)
    drift_calls: list = []
    import core.intel.drift_service as ds
    monkeypatch.setattr(ds, "schedule_intel_drift", lambda *a, **k: (drift_calls.append((a, k)), True)[1])

    summary = bf.run(apply=True, limit=10, with_drift=True)
    assert summary["applied"] == 1 and summary["drifts_queued"] == 0
    assert drift_calls == []
