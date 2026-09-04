# SPDX-License-Identifier: AGPL-3.0-or-later
"""core.intel.x_media.resolve_x_media -- canonical media acquisition (docs/prompt.md §2)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from core.intel import x_media
from core.intel.x_media import MediaResolution, normalize_pbs_url, resolve_x_media


class _Media:
    def __init__(self, source_url="", media_url="", media_url_https="", url=""):
        self.source_url = source_url
        self.media_url = media_url
        self.media_url_https = media_url_https
        self.url = url


def _tweet(**kw):
    return SimpleNamespace(id=kw.pop("id", "1"), media=kw.pop("media", []), **kw)


# ── normalize_pbs_url ───────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "https://pbs.twimg.com/media/ABC.jpg",
            "https://pbs.twimg.com/media/ABC.jpg?name=orig",
        ),
        (
            "https://pbs.twimg.com/media/ABC?format=jpg&name=small",
            "https://pbs.twimg.com/media/ABC?format=jpg&name=orig",
        ),
        (
            "https://pbs.twimg.com/media/ABC.jpg:large",
            "https://pbs.twimg.com/media/ABC.jpg?name=orig",
        ),
        (
            "https://pbs.twimg.com/media/ABC.jpg?name=orig",
            "https://pbs.twimg.com/media/ABC.jpg?name=orig",
        ),
        ("https://example.com/x.jpg", "https://example.com/x.jpg"),
    ],
)
def test_normalize_pbs_url(raw, expected):
    assert normalize_pbs_url(raw) == expected


# ── acquisition order + allow-list-before-cap ───────────────────────────────
def test_host_allowlist_is_applied_before_the_cap():
    # Four t.co wrappers precede the one real pbs photo -- the old urls[:4]
    # truncation dropped it. The allow-list must run first.
    tweet = _tweet(
        media=[
            _Media(url="https://t.co/a"),
            _Media(url="https://t.co/b"),
            _Media(url="https://t.co/c"),
            _Media(url="https://t.co/d"),
            _Media(source_url="https://pbs.twimg.com/media/REAL.jpg"),
        ]
    )
    resolution = resolve_x_media(tweet, "1", allow_syndication=False)
    assert resolution.urls == ["https://pbs.twimg.com/media/REAL.jpg?name=orig"]
    assert resolution.candidates[0].media_source == "media"


def test_quoted_tweet_media_is_merged_and_deduplicated():
    quoted = _tweet(id="2", media=[_Media(source_url="https://pbs.twimg.com/media/MAP.jpg")])
    tweet = _tweet(id="1", media=[_Media(media_url_https="https://pbs.twimg.com/media/MAP.jpg")])
    resolution = resolve_x_media(tweet, "1", quoted, allow_syndication=False)
    # same normalised URL from two shapes -> one candidate
    assert resolution.urls == ["https://pbs.twimg.com/media/MAP.jpg?name=orig"]


def test_extended_entities_and_card_fallbacks_are_normalised():
    tweet = SimpleNamespace(
        id="1",
        media=[],
        extended_entities={"media": [{"media_url_https": "https://pbs.twimg.com/media/EXT.png"}]},
    )
    resolution = resolve_x_media(tweet, "1", allow_syndication=False)
    assert resolution.urls == ["https://pbs.twimg.com/media/EXT.png?name=orig"]


def test_syndication_fallback_only_when_object_shapes_are_empty(monkeypatch):
    calls: list[str] = []

    def fake_fetch(tweet_id, **_kw):
        calls.append(tweet_id)
        return ["https://pbs.twimg.com/media/SYND.jpg?name=small"] if tweet_id == "999" else []

    monkeypatch.setattr(x_media, "fetch_tweet_photos", fake_fetch)

    # object shape has media -> syndication never consulted
    with_media = _tweet(id="999", media=[_Media(source_url="https://pbs.twimg.com/media/OBJ.jpg")])
    assert resolve_x_media(with_media, "999").urls == [
        "https://pbs.twimg.com/media/OBJ.jpg?name=orig"
    ]
    assert calls == []

    # nothing in the object -> syndication resolves it, normalised
    empty = SimpleNamespace(id="999", media=[])
    resolution = resolve_x_media(empty, "999")
    assert resolution.urls == ["https://pbs.twimg.com/media/SYND.jpg?name=orig"]
    assert calls == ["999"]
    assert resolution.candidates[0].media_source == "syndication"


def test_failure_reason_distinguishes_blocked_from_absent():
    blocked = _tweet(media=[_Media(url="https://cdn.evil.example/x.jpg")])
    assert resolve_x_media(blocked, "1", allow_syndication=False).failure_reason == (
        "candidates_failed_host_allowlist"
    )

    absent = SimpleNamespace(id="1", media=[])
    assert resolve_x_media(absent, "1", allow_syndication=False).failure_reason == (
        "no_media_in_any_shape"
    )


def test_diagnostics_payload_shape():
    tweet = _tweet(media=[_Media(source_url="https://pbs.twimg.com/media/A.jpg")])
    diag = resolve_x_media(tweet, "1", allow_syndication=False).as_diagnostics()
    assert diag["media_discovered"] == 1
    assert diag["media_sources"] == ["media"]
    assert any("tweet.media" in s for s in diag["media_shapes_tried"])


def test_empty_resolution_urls_and_count():
    resolution = MediaResolution()
    assert resolution.urls == []
    assert resolution.media_count == 0
