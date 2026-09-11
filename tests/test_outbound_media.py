# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import ClassVar

import pytest
from core.intel import vision, x_media_utils
from core.net.policy import OutboundError


class _LegacyAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, *_args, **_kwargs):
        return SimpleNamespace(
            headers={"content-type": "image/png"},
            content=b"legacy-private-image",
            raise_for_status=lambda: None,
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/private",
        "https://10.0.0.5/private",
        "https://169.254.169.254/latest/meta-data",
    ],
)
def test_untrusted_image_fetch_blocks_private_targets_before_legacy_fetch(
    monkeypatch, url: str
) -> None:
    monkeypatch.setattr(vision, "_exif_gps", lambda _payload: {"lat": 1.0, "lon": 2.0})
    if hasattr(vision, "httpx"):
        monkeypatch.setattr(vision.httpx, "AsyncClient", _LegacyAsyncClient)

    result = asyncio.run(vision.extract_from_url(url))

    assert result is None


def test_untrusted_image_fetch_redacts_query_tokens_from_logs(monkeypatch, caplog) -> None:
    secret = "top-secret-query-token"
    if hasattr(vision, "httpx"):
        class _FailingClient(_LegacyAsyncClient):
            async def get(self, *_args, **_kwargs):
                raise TimeoutError("network failed")

        monkeypatch.setattr(vision.httpx, "AsyncClient", _FailingClient)
    with caplog.at_level(logging.WARNING, logger=vision.__name__):
        result = asyncio.run(
            vision.extract_from_url(f"https://10.0.0.5/image.png?token={secret}")
        )
    assert result is None
    assert secret not in caplog.text


def test_vision_treats_redirect_policy_failure_as_safe_empty(monkeypatch) -> None:
    calls = []

    async def fake_request(*args, **kwargs):
        calls.append((args, kwargs))
        raise OutboundError("redirect_blocked")

    monkeypatch.setattr(vision, "async_request", fake_request, raising=False)
    if hasattr(vision, "httpx"):
        monkeypatch.setattr(vision.httpx, "AsyncClient", _LegacyAsyncClient)
    assert asyncio.run(vision.extract_from_url("https://public.example/image.png")) is None
    assert len(calls) == 1


class _FixedResponse:
    def __init__(self, body: bytes, *, payload=None):
        self.body = body
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _FixedClient:
    calls: ClassVar[list[tuple]] = []

    def __init__(self, origins, **kwargs):
        self.origins = tuple(origins)
        self.kwargs = kwargs

    def request(self, url, **kwargs):
        self.calls.append((self.origins, url, kwargs))
        if "tweet-result" in url:
            return _FixedResponse(
                b"{}",
                payload={
                    "photos": [{"url": "https://pbs.twimg.com/media/SAFE.jpg"}]
                },
            )
        return _FixedResponse(b"image-bytes")


def test_twitter_syndication_uses_fixed_origin_client(monkeypatch) -> None:
    _FixedClient.calls = []
    monkeypatch.setattr(x_media_utils, "FixedOriginClient", _FixedClient, raising=False)
    if hasattr(x_media_utils, "urllib"):
        monkeypatch.setattr(
            x_media_utils.urllib.request,
            "urlopen",
            lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("legacy urlopen used")),
        )
    assert x_media_utils.fetch_tweet_photos("1519480761749016577") == [
        "https://pbs.twimg.com/media/SAFE.jpg"
    ]


def test_twitter_image_download_uses_fixed_origin_client(monkeypatch) -> None:
    _FixedClient.calls = []
    monkeypatch.setattr(x_media_utils, "FixedOriginClient", _FixedClient, raising=False)
    if hasattr(x_media_utils, "urllib"):
        monkeypatch.setattr(
            x_media_utils.urllib.request,
            "urlopen",
            lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("legacy urlopen used")),
        )
    assert (
        x_media_utils._download_bounded_image(
            "https://pbs.twimg.com/media/SAFE.jpg?name=orig"
        )
        == b"image-bytes"
    )


def test_twitter_helpers_preserve_empty_result_on_outbound_failure(monkeypatch) -> None:
    class _FailingFixedClient(_FixedClient):
        def request(self, *_args, **_kwargs):
            raise OutboundError("redirect_blocked")

    monkeypatch.setattr(
        x_media_utils, "FixedOriginClient", _FailingFixedClient, raising=False
    )
    assert x_media_utils.fetch_tweet_photos("1519480761749016577") == []
    assert (
        x_media_utils._download_bounded_image("https://pbs.twimg.com/media/SAFE.jpg")
        is None
    )
