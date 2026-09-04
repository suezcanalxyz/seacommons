# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical X/Twitter media acquisition (docs/prompt.md §2).

`twikit_monitor._tweet_media_urls` grew a chain of best-effort shape probes
(typed `.media`, `.extended_entities`, `.entities`, link-preview `.card`) but
still (a) truncated the candidate list *before* the host allow-list ran, so a
run of t.co / card thumbnails could push the real photo past the cap; (b)
never fell back to the public syndication CDN in the live path, even though
`fetch_tweet_photos` already exists for the backfill; (c) used fallback-shape
URLs at whatever size twikit handed back, and (d) returned a bare
`list[str]`, so a real extraction gap could only be seen in a log line.

`resolve_x_media` is the one place media acquisition happens. It collects
every candidate from every known shape (tweet and its quoted tweet), records
which shape each came from, normalises `pbs.twimg.com` photos to the original
resolution, applies the host allow-list, deduplicates on the normalised URL,
and — only when the object shapes yield nothing — falls back to the
syndication CDN. It returns a `MediaResolution` carrying the diagnostics the
event metadata and the benchmark need.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from core.intel.x_media_utils import _ALLOWED_MEDIA_HOSTS, fetch_tweet_photos

# The largest render X serves. `name=orig` returns the upload at full
# resolution; the small coordinate row on an Alarm Phone map popup is a
# handful of pixels tall at the default `name=small` (680px) size.
_ORIGINAL_SIZE_TOKEN = "orig"


@dataclass
class MediaCandidate:
    original_url: str
    resolved_url: str
    media_source: str  # media | extended_entities | entities | card | syndication | quoted_syndication


@dataclass
class MediaResolution:
    """Every usable image for a tweet, with acquisition diagnostics."""

    candidates: list[MediaCandidate] = field(default_factory=list)
    shapes_tried: list[str] = field(default_factory=list)
    failure_reason: Optional[str] = None

    @property
    def urls(self) -> list[str]:
        return [candidate.resolved_url for candidate in self.candidates]

    @property
    def media_count(self) -> int:
        return len(self.candidates)

    def as_diagnostics(self) -> dict[str, Any]:
        return {
            "media_discovered": self.media_count,
            "media_sources": [candidate.media_source for candidate in self.candidates],
            "media_shapes_tried": self.shapes_tried,
            **({"media_failure_reason": self.failure_reason} if self.failure_reason else {}),
        }


# Size tokens X serves that are smaller than the upload.
_SMALL_SIZE_TOKENS = frozenset({
    "tiny", "small", "medium", "large", "thumb",
    "900x900", "680x680", "360x360", "240x240",
})


def normalize_pbs_url(url: str) -> str:
    """Rewrite a pbs.twimg.com photo URL to its original resolution.

    Adds/overrides `name=orig` when the URL is unsized or downsized. Handles
    the older `/media/ABC.jpg:large` suffix form too. A non-pbs URL and a URL
    already at `name=orig` come back unchanged.
    """
    parsed = urlparse(url)
    if parsed.hostname not in _ALLOWED_MEDIA_HOSTS:
        return url
    path = parsed.path
    query = dict(parse_qsl(parsed.query))
    segment = path.rsplit("/", 1)[-1]
    if ":" in segment:  # ABC.jpg:large
        path, _, suffix = path.rpartition(":")
        if suffix in _SMALL_SIZE_TOKENS or "name" not in query:
            query["name"] = _ORIGINAL_SIZE_TOKEN
    if query.get("name", _ORIGINAL_SIZE_TOKEN) in _SMALL_SIZE_TOKENS or "name" not in query:
        query["name"] = _ORIGINAL_SIZE_TOKEN
    return urlunparse(parsed._replace(path=path, query=urlencode(query)))


def _is_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname in _ALLOWED_MEDIA_HOSTS


def _harvest_object_shapes(tweet: Any) -> tuple[list[tuple[str, str]], list[str]]:
    """(raw_url, media_source) pairs from every known twikit object shape,
    plus the list of shapes probed. Never raises."""
    found: list[tuple[str, str]] = []
    shapes: list[str] = []

    try:
        media = getattr(tweet, "media", None) or []
        shapes.append(f"media[{len(media)}]")
        for item in media:
            url = str(
                getattr(item, "source_url", "")
                or getattr(item, "media_url", "")
                or getattr(item, "media_url_https", "")
                or getattr(item, "url", "")
                or ""
            )
            if url:
                found.append((url, "media"))
    except Exception as exc:  # noqa: BLE001 - a shape change must not break acquisition
        shapes.append(f"media[error:{exc}]")

    for attr, label in (("extended_entities", "extended_entities"), ("entities", "entities")):
        try:
            container = getattr(tweet, attr, None) or {}
            items = container.get("media") or []
            shapes.append(f"{label}[{len(items)}]")
            for item in items:
                url = str(item.get("media_url_https") or item.get("url") or "")
                if url:
                    found.append((url, label))
        except Exception as exc:  # noqa: BLE001
            shapes.append(f"{label}[error:{exc}]")

    try:
        card = getattr(tweet, "card", None)
        if card is not None:
            card_url = str(
                getattr(card, "thumbnail_url", "") or getattr(card, "image_url", "") or ""
            )
            shapes.append(f"card[{'1' if card_url else '0'}]")
            if card_url:
                found.append((card_url, "card"))
        else:
            shapes.append("card[absent]")
    except Exception as exc:  # noqa: BLE001
        shapes.append(f"card[error:{exc}]")

    return found, shapes


def resolve_x_media(
    tweet: Any,
    tweet_id: str,
    quoted_tweet: Any = None,
    *,
    max_images: int = 6,
    allow_syndication: bool = True,
) -> MediaResolution:
    """Resolve every usable image for a tweet (and its quoted tweet).

    Order: typed media → extended_entities → entities → card, for the tweet
    then the quoted tweet; then, only if nothing survived the allow-list, the
    public syndication CDN for each id. Deduplicated on the normalised URL,
    capped at ``max_images`` *after* filtering.
    """
    resolution = MediaResolution()
    seen: set[str] = set()

    raw: list[tuple[str, str]] = []
    own, own_shapes = _harvest_object_shapes(tweet)
    raw.extend(own)
    resolution.shapes_tried.extend(f"tweet.{shape}" for shape in own_shapes)
    if quoted_tweet is not None:
        quoted, quoted_shapes = _harvest_object_shapes(quoted_tweet)
        raw.extend(quoted)
        resolution.shapes_tried.extend(f"quoted.{shape}" for shape in quoted_shapes)

    allowed_raw = [pair for pair in raw if _is_allowed(pair[0])]
    for original_url, source in allowed_raw:
        resolved = normalize_pbs_url(original_url)
        if resolved in seen:
            continue
        seen.add(resolved)
        resolution.candidates.append(MediaCandidate(original_url, resolved, source))
        if len(resolution.candidates) >= max_images:
            return resolution

    if resolution.candidates:
        return resolution

    # Nothing from the object shapes. Either the tweet genuinely has no image
    # or twikit changed shape under us -- the syndication CDN resolves both.
    if allow_syndication:
        quoted_id = str(getattr(quoted_tweet, "id", "") or "") if quoted_tweet is not None else ""
        for source_id, label in ((str(tweet_id), "syndication"), (quoted_id, "quoted_syndication")):
            if not source_id or not source_id.isdigit():
                continue
            try:
                syndication_urls = fetch_tweet_photos(source_id)
            except Exception:  # noqa: BLE001 - network best effort
                syndication_urls = []
            resolution.shapes_tried.append(f"{label}[{len(syndication_urls)}]")
            for url in syndication_urls:
                resolved = normalize_pbs_url(url)
                if resolved in seen or not _is_allowed(resolved):
                    continue
                seen.add(resolved)
                resolution.candidates.append(MediaCandidate(url, resolved, label))
                if len(resolution.candidates) >= max_images:
                    return resolution

    if not resolution.candidates:
        resolution.failure_reason = (
            "candidates_failed_host_allowlist" if raw else "no_media_in_any_shape"
        )
    return resolution
