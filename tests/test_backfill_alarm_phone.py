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


def _cand(**over):
    base = {
        "id": "e1", "tweet_id": "1", "quoted_tweet_id": "", "media_urls": [],
        "timestamp_utc": "2026-08-01T00:00:00Z", "title": "boat in distress",
        "text": "", "coordinate_source": "region_area", "lifecycle": "active",
        "persons": 12, "vessel_type": "rubber_boat",
    }
    base.update(over)
    return base


def test_run_is_dry_by_default(monkeypatch) -> None:
    monkeypatch.setattr(bf, "find_candidates", lambda limit: [
        _cand(id="e1"),
        _cand(id="e2", title="boat2"),
    ])
    monkeypatch.setattr(bf, "resolve_position", lambda c: (35.5, 14.1, "text") if c["id"] == "e1" else None)
    monkeypatch.setattr(bf, "in_operational_region", lambda *a: True, raising=False)
    monkeypatch.setattr("core.intel.landmask.in_operational_region", lambda *a: True)
    applied: list = []
    monkeypatch.setattr(bf, "apply_position", lambda *a: applied.append(a) or "x")

    report = bf.run(apply=False, limit=10, with_drift=False)
    assert report["scanned"] == 2
    assert report["dry_run"] is True
    assert report["newly_positioned_approximate"] == 1
    assert report["region_only"] == 1
    assert applied == []  # dry run never writes


def test_run_apply_freezes_drift_for_unverified_backfill(monkeypatch) -> None:
    """docs/fixes.md F-05: a backfilled unverified position is written back but
    must not seed a drift (only events passing is_auto_drift_eligible do)."""
    monkeypatch.setattr(bf, "find_candidates", lambda limit: [_cand()])
    monkeypatch.setattr(bf, "resolve_position", lambda c: (35.5, 14.1, "pin_landmark"))
    monkeypatch.setattr(bf, "apply_position", lambda *a: "newly_positioned_approximate")
    drift_calls: list = []
    import core.intel.drift_service as ds
    monkeypatch.setattr(ds, "schedule_intel_drift", lambda *a, **k: (drift_calls.append((a, k)), True)[1])

    report = bf.run(apply=True, limit=10, with_drift=True)
    assert report["newly_positioned_approximate"] == 1
    assert report["drift_eligible"] == 0 and report["drift_rejected"] == 1
    assert drift_calls == []


def test_report_has_every_phase5_bucket(monkeypatch) -> None:
    monkeypatch.setattr(bf, "find_candidates", lambda limit: [])
    report = bf.run(apply=False, limit=1, with_drift=False)
    for key in bf._REPORT_KEYS:
        assert key in report


def test_land_humanitarian_candidate_gets_no_maritime_position(monkeypatch) -> None:
    monkeypatch.setattr(bf, "find_candidates", lambda limit: [
        _cand(title="Group found near Evros and taken to a reception centre"),
    ])
    calls: list = []
    monkeypatch.setattr(bf, "resolve_position", lambda c: calls.append(c) or (35.5, 14.1, "text"))
    report = bf.run(apply=True, limit=10, with_drift=True)
    assert report["land_humanitarian"] == 1
    assert calls == []  # never even tries to geolocate a land case


def test_apply_position_never_downgrades_and_is_idempotent(monkeypatch) -> None:
    from types import SimpleNamespace

    row = SimpleNamespace(
        id="e1", lat=34.0, lon=12.0,
        meta={"coordinate_source": "post_text", "coordinate_review_status": "not_required"},
        coordinate_review_status=None, location_uncertainty_m=None,
    )

    class _Session:
        def query(self, *_a):
            return self

        def filter(self, *_a):
            return self

        def first(self):
            return row

        def flush(self):
            pass

    import contextlib

    @contextlib.contextmanager
    def _scope():
        yield _Session()

    monkeypatch.setattr("core.db.session.session_scope", _scope)
    monkeypatch.setattr("core.intel.landmask.in_operational_region", lambda *a: True)
    monkeypatch.setattr("core.intel.landmask.nearest_sea_point", lambda a, b: (a, b))

    # A pin-landmark read must not replace a stored verified text coordinate.
    outcome = bf.apply_position("e1", 35.0, 13.0, "pin_landmark")
    assert outcome == "already_good"
    assert row.lat == 34.0 and row.lon == 12.0
