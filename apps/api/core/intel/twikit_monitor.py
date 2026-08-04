# SPDX-License-Identifier: AGPL-3.0-or-later
"""Twikit X monitor — account-focused public-tweet ingestion via a real session.

Twikit talks to X's public web/GraphQL endpoints using cookies exported from the
account's browser. Unlike the paid official API, this is free, but it *is*
account-emulation: it must be treated as the least-trusted X source.

Scope (per operator directive): track a curated list of *specific* accounts
(NGO SAR monitors such as @alarm_phone), NOT generic keyword searches.
Polling is tiered, not always-on: each sweep only fetches accounts whose poll
interval has elapsed. Priority accounts (default @alarm_phone) are polled
every ~45 s for near-real-time pickup, the rest every ~5 min. A Telegram
notification is fired when any tracked account posts.

X offers no push notification for "another account posted" (the paid official
Streaming API is enterprise-only and twikit's own streaming only covers your
own tweet engagement/DMs), so some polling is unavoidable — the X web app
itself polls roughly every 30 s. The tiered scheduler below keeps that cost
minimal.

Ingestion semantics ("strong distress parsing"): a tweet is tagged as distress
only when it is an actionable direct distress/SAR call (is_direct_distress_call
— the same strict signal the Alarm Phone monitor uses), never for resolved or
contextual posts. Non-distress posts from tracked accounts are still ingested
    but tagged `report_kind="news"` (or `"resolved"`), so the operational/distress
    feed is never polluted by commentary.

Repost semantics (operator directive): a repost (retweeted_tweet) of an alert
that already opened an incident must answer that SAME thread — it is recorded
onto the parent incident's `thread_reposts` bookkeeping and never spawns a new
marker, never bumps a version, and never re-broadcasts an update. Only if the
original was never tracked is the original content ingested (deduplicated by
tweet id), so nothing is lost.

Quote-tweet semantics: a quote tweet of an already-tracked incident is
threaded the same way as a plain repost (no new marker, no re-broadcast), but
— unlike a plain RT — the quoting account's own caption is new content (e.g.
"confirmed rescued"), so it is kept as a `note` on the thread record instead
of being discarded. When the quoted tweet is NOT already tracked, its text
and media are merged with the quoting account's caption for distress/geo
extraction: Alarm Phone and other tracked NGOs sometimes quote a source (a
witness, a partner NGO) with only a short caption of their own, and the real
distress content — including the map screenshot with GPS coordinates — lives
in the quoted tweet, not the caption. Losing that would mean losing the
signal entirely.

Session resilience: a transient failure while establishing the twikit session
(e.g. a network blip at process start) retries with the same capped backoff
used for poll errors, rather than permanently killing the monitor until the
next process restart. If every tracked account fails to poll for several
consecutive cycles — a strong signal the session itself has gone stale, not
that every account broke independently — the client is rebuilt from the same
cookies file on the next cycle.


Security posture (must be preserved):
  * Strictly opt-in: `TWIKIT_ENABLED=true` AND `TWIKIT_COOKIES_FILE` must point
    at an existing file, otherwise the monitor stays dormant.
  * Cookies live on disk (0600, owned by the service user) or in a secrets
    manager — never in the repo, never in logs. Cookie contents are never logged.
  * Read-only: only profile/timeline reads are called. No follow/like/retweet/
    DM/block calls, ever. Exponential backoff on rate limits (cap 15 min)
    protects the real account from aggressive polling.
  * Every event is labelled `source_policy="unofficial"` — EXCEPT confirmed
    distress calls from these specific tracked accounts, which the operator
    has explicitly chosen to surface on the public live map
    (`publication_status="published"`, `source_policy="operator_published"`).
    Non-distress news from the same accounts stays operator-only and never
    feeds the public map or distress triangulation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import time
from datetime import UTC, datetime
from typing import Any, Optional

from core.config import config
from core.intel.x_media_utils import _ocr_photo
from core.intel.auto_drift_client import request_auto_drift
from core.intel.geoextract import (
    classify_severity,
    extract_coords,
    extract_numeric_coords,
    extract_relative_coords,
    is_direct_distress_call,
    is_resolved_distress,
)
from core.intel.ngo_registry import NGO_TWITTER_HANDLES
from core.intel.store import IntelEvent, intel_store
from core.intel.twitter_monitor import _make_title

logger = logging.getLogger(__name__)

_SOURCE_NAME = "X / Twitter (twikit)"
_REQUIRED_COOKIES = ("auth_token", "ct0")
_MAX_BACKOFF_S = 900  # 15 min — be extremely gentle with the real account
_BASE_POLL_INTERVAL_S = 300  # non-priority accounts
_PRIORITY_POLL_INTERVAL_S = 45  # near-real-time accounts (default @alarm_phone)
_SLEEP_CAP_S = 60.0  # wake up at most this often to recompute due accounts
_SESSION_REBUILD_AFTER_FAILURES = 3  # consecutive all-accounts-failed cycles
_PRIORITY_DEFAULT = "alarm_phone"
_DEFAULT_ACCOUNTS = list(NGO_TWITTER_HANDLES)
# Alarm Phone (and the other tracked SAR NGOs) publish the actual GPS position
# as a map screenshot, not in the tweet text. Same host allow-list as the
# shared OCR path (x_media_utils._ocr_photo).
_ALLOWED_MEDIA_HOSTS = frozenset({"pbs.twimg.com"})


class TwikitMonitor:
    """Poll tracked X accounts via a twikit session; source_policy='unofficial'."""

    def __init__(
        self,
        enabled: bool = False,
        cookies_file: str = "",
        accounts: str = "",
        poll_interval_s: int = _BASE_POLL_INTERVAL_S,
        priority_accounts: str = "",
        priority_poll_interval_s: int = _PRIORITY_POLL_INTERVAL_S,
        alerts_enabled: bool = False,
    ) -> None:
        self._enabled = bool(enabled)
        self._cookies_file = (cookies_file or "").strip()
        self._accounts = self._parse_accounts(accounts)
        self._poll_interval_s = int(poll_interval_s)
        self._priority_accounts = self._parse_priority(priority_accounts)
        self._priority_poll_interval_s = int(priority_poll_interval_s)
        self._alerts_enabled = bool(alerts_enabled)
        self._since_id: dict[str, int] = {}
        self._users: dict[str, Any] = {}
        self._next_poll_ts: dict[str, float] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._backoff = 0.0

    @staticmethod
    def _parse_accounts(raw: str) -> list[str]:
        accounts = [a.strip().lstrip("@") for a in raw.split(",") if a.strip()]
        return accounts or list(_DEFAULT_ACCOUNTS)

    @staticmethod
    def _parse_priority(raw: str) -> set[str]:
        accounts = {a.strip().lstrip("@") for a in raw.split(",") if a.strip()}
        return accounts or {_PRIORITY_DEFAULT}

    def _interval_for(self, handle: str) -> int:
        return (
            self._priority_poll_interval_s
            if handle in self._priority_accounts
            else self._poll_interval_s
        )

    @property
    def priority_accounts(self) -> list[str]:
        return sorted(self._priority_accounts)

    @property
    def configured(self) -> bool:
        if not self._enabled:
            return False
        if not self._cookies_file:
            logger.info("X (twikit) disabled: TWIKIT_COOKIES_FILE is not set")
            return False
        if not os.path.isfile(self._cookies_file):
            logger.warning(
                "X (twikit) disabled: cookies file not found: %s", self._cookies_file
            )
            return False
        return True

    @property
    def tracked_accounts(self) -> list[str]:
        return list(self._accounts)

    def start(self) -> None:
        if self._running:
            return
        if not self.configured:
            return
        from core.intel.source_registry import source_registry

        source_registry.register(_SOURCE_NAME, "twitter")
        self._next_poll_ts = {handle: time.monotonic() for handle in self._accounts}
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="intel-x-twikit",
        )
        self._thread.start()
        logger.info(
            "X (twikit) monitor started; tracking %d account(s) | "
            "priority (%s) poll=%ss | base poll=%ss | alerts=%s",
            len(self._accounts),
            ", ".join(sorted(self._priority_accounts)),
            self._priority_poll_interval_s,
            self._poll_interval_s,
            "on" if self._alerts_enabled else "off",
        )

    def stop(self) -> None:
        self._running = False

    def _run_loop(self) -> None:
        try:
            asyncio.run(self._async_loop())
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("X (twikit) monitor crashed: %s", exc)

    async def _async_loop(self) -> None:
        from core.intel.source_registry import source_registry

        client = None
        consecutive_full_failures = 0
        while self._running:
            if client is None:
                try:
                    client = await self._build_client()
                except Exception as exc:
                    logger.error(
                        "X (twikit) session setup failed (%s); retrying with backoff "
                        "instead of giving up. Cookie file: %s",
                        exc,
                        self._cookies_file,
                    )
                    source_registry.record_poll(_SOURCE_NAME, error=str(exc))
                    await asyncio.sleep(self._next_delay("session setup failed"))
                    continue

            now = time.monotonic()
            due = [h for h in self._accounts if self._next_poll_ts[h] <= now]
            new_count = 0
            failed = 0
            if due:
                for handle in due:
                    try:
                        for tweet in await self._fetch_account(client, handle):
                            if self._ingest(tweet, handle):
                                new_count += 1
                        self._next_poll_ts[handle] = time.monotonic() + self._interval_for(handle)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        failed += 1
                        # Evict the cached user object: a renamed/suspended-then
                        # -reinstated account or a one-off API hiccup should not
                        # wedge this handle into the same failure forever.
                        self._users.pop(handle, None)
                        logger.warning("X (twikit) poll error for @%s: %s", handle, exc)
            error = "poll failed" if due and failed == len(due) else None
            if error:
                consecutive_full_failures += 1
                if consecutive_full_failures >= _SESSION_REBUILD_AFTER_FAILURES:
                    logger.warning(
                        "X (twikit) %d consecutive fully-failed polls; rebuilding the "
                        "session (cookies may have rotated or expired)",
                        consecutive_full_failures,
                    )
                    client = None
                    self._users.clear()
                    consecutive_full_failures = 0
            else:
                consecutive_full_failures = 0
            source_registry.record_poll(_SOURCE_NAME, events_found=new_count, error=error)
            await asyncio.sleep(self._next_delay(error))

    def _next_delay(self, error: Optional[str]) -> float:
        if error:
            self._backoff = min(self._backoff * 2 + 30, _MAX_BACKOFF_S) if self._backoff else 30.0
            return self._backoff
        self._backoff = 0.0
        now = time.monotonic()
        next_due = min(
            (self._next_poll_ts.get(h, now) for h in self._accounts),
            default=now,
        )
        return min(max(next_due - now, 1.0), _SLEEP_CAP_S)

    async def _build_client(self):
        from twikit import Client

        cookies = self._load_cookies()
        if cookies is None:
            raise RuntimeError("cookies file could not be parsed")
        missing = [k for k in _REQUIRED_COOKIES if k not in cookies]
        if missing:
            raise RuntimeError(
                f"cookies file is missing required keys: {', '.join(missing)}"
            )
        client = Client(language="en")
        client.set_cookies(cookies)
        logger.info(
            "X (twikit) session cookies loaded (%d cookies); content never logged",
            len(cookies),
        )
        return client

    def _load_cookies(self) -> Optional[dict[str, str]]:
        try:
            with open(self._cookies_file, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception as exc:
            logger.error("X (twikit) could not read cookies file: %s", exc)
            return None
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items() if v is not None}
        if isinstance(raw, list):
            out: dict[str, str] = {}
            for item in raw:
                if isinstance(item, dict) and item.get("name") and item.get("value") is not None:
                    out[str(item["name"])] = str(item["value"])
            return out
        return None

    async def _fetch_account(self, client, handle: str) -> list[Any]:
        user = self._users.get(handle)
        if user is None:
            user = await client.get_user_by_screen_name(handle)
            self._users[handle] = user
        result = await user.get_tweets("Tweets", count=20)
        since = self._since_id.get(handle, 0)
        fresh: list[Any] = []
        for tweet in result:
            try:
                tweet_id = int(str(tweet.id))
            except (TypeError, ValueError):
                continue
            if tweet_id <= since:
                continue
            fresh.append(tweet)
        if fresh:
            self._since_id[handle] = max(since, max(int(str(tweet.id)) for tweet in fresh))
        return fresh

    @staticmethod
    def _quoted_tweet(tweet: Any) -> Optional[Any]:
        """Best-effort access to a quote-tweet's quoted status.

        twikit/twifork have exposed the quoted tweet under different attribute
        names across versions/forks (``quote``, ``quoted_tweet``,
        ``quoted_status``). Try each so a library upgrade never silently drops
        the quoted content — which is often where the actual distress text
        and coordinate screenshot live, not in the quoting account's caption.
        """
        for attr in ("quote", "quoted_tweet", "quoted_status"):
            quoted = getattr(tweet, attr, None)
            if quoted is not None and getattr(quoted, "id", None) is not None:
                return quoted
        return None

    @staticmethod
    def _tweet_media_urls(tweet: Any, *, tweet_id: str = "") -> list[str]:
        """Best-effort extraction of https://pbs.twimg.com/ media from a tweet.

        Twikit (twifork) exposes each media entity as a typed object whose
        image URL lives on the ``media_url`` / ``source_url`` properties (the
        raw ``media_url_https`` key is not an attribute), while older shapes
        expose ``media_url_https`` directly or keep the raw ``extended_entities``
        dict, and some map-tool posts attach the screenshot as a link-preview
        card (``tweet.card``) rather than native media. Try every shape so an
        API change never silently disables image-based geolocation. Same host
        allow-list as the OCR path.

        Logs a diagnosable warning — listing exactly which raw shapes were
        present and empty — whenever nothing at all is found, and separately
        when candidate URLs were found but none matched the host allow-list,
        so a real extraction gap (as opposed to "this tweet has no image")
        shows up in logs instead of silently falling back to a rough
        centroid.
        """
        urls: list[str] = []
        shapes_tried: list[str] = []
        try:
            media = getattr(tweet, "media", None) or []
            shapes_tried.append(f"media[{len(media)}]")
            for item in media:
                url = str(
                    getattr(item, "source_url", "")
                    or getattr(item, "media_url", "")
                    or getattr(item, "media_url_https", "")
                    or getattr(item, "url", "")
                    or ""
                )
                if url:
                    urls.append(url)
        except Exception as exc:
            shapes_tried.append(f"media[error:{exc}]")
        if not urls:
            try:
                extended = getattr(tweet, "extended_entities", None) or {}
                extended_media = extended.get("media") or []
                shapes_tried.append(f"extended_entities[{len(extended_media)}]")
                for item in extended_media:
                    url = str(item.get("media_url_https") or item.get("url") or "")
                    if url:
                        urls.append(url)
            except Exception as exc:
                shapes_tried.append(f"extended_entities[error:{exc}]")
        if not urls:
            try:
                entities = getattr(tweet, "entities", None) or {}
                entities_media = entities.get("media") or []
                shapes_tried.append(f"entities[{len(entities_media)}]")
                for item in entities_media:
                    url = str(item.get("media_url_https") or item.get("url") or "")
                    if url:
                        urls.append(url)
            except Exception as exc:
                shapes_tried.append(f"entities[error:{exc}]")
        if not urls:
            # Map-tool posts (Alarm Phone's screenshot generator, some NGO
            # dashboards) can attach the image as a link-preview card rather
            # than native tweet media, particularly when posted through a
            # third-party scheduling tool.
            try:
                card = getattr(tweet, "card", None)
                if card is not None:
                    card_url = str(
                        getattr(card, "thumbnail_url", "")
                        or getattr(card, "image_url", "")
                        or ""
                    )
                    shapes_tried.append(f"card[{'1' if card_url else '0'}]")
                    if card_url:
                        urls.append(card_url)
                else:
                    shapes_tried.append("card[absent]")
            except Exception as exc:
                shapes_tried.append(f"card[error:{exc}]")

        allowed = []
        for url in urls[:4]:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                if parsed.scheme == "https" and parsed.hostname in _ALLOWED_MEDIA_HOSTS:
                    allowed.append(url)
            except Exception:
                continue

        if not allowed:
            if urls:
                logger.warning(
                    "X (twikit) tweet %s: %d candidate media URL(s) found but none "
                    "matched the allowed host (%s); shapes tried: %s",
                    tweet_id, len(urls), sorted(_ALLOWED_MEDIA_HOSTS), shapes_tried,
                )
            else:
                logger.debug(
                    "X (twikit) tweet %s: no media found in any known shape (%s) — "
                    "this tweet likely has no attached image",
                    tweet_id, shapes_tried,
                )
        return allowed

    def _ocr_tweet_media(
        self, tweet_id: str, urls: list[str]
    ) -> tuple[Optional[tuple[float, float]], bool, str]:
        """OCR the tweet's images until one yields a coordinate pair."""
        if not urls:
            return None, False, "none"
        for url in urls:
            try:
                candidate, attempted, method = _ocr_photo(url)
                if candidate is not None:
                    return candidate, attempted, method
            except Exception as exc:
                logger.debug("X (twikit) media OCR failed for %s (%s): %s", tweet_id, url, exc)
        return None, True, "none"

    def _apply_media_ocr(self, event_id: str, urls: list[str]) -> None:
        """Run in a background thread: OCR, upgrade the stored position, drift."""
        try:
            coords, attempted, method = self._ocr_tweet_media(event_id, urls)
            if coords is None:
                if attempted:
                    intel_store.update_metadata(event_id, metadata={"ocr_attempted": True})
                self._auto_drift_if_live(event_id, force=False)
                return
            upgraded = intel_store.enrich_location(
                event_id,
                lat=coords[0],
                lon=coords[1],
                metadata={
                    "coordinate_source": "media_ocr_text" if method == "text" else "media_pin_landmark",
                    "coordinate_review_status": "machine_ocr_unverified",
                    "verification_status": "machine_extracted_unverified",
                    "location_uncertainty_m": 1500 if method == "text" else 4000,
                    "media_transport": "x_media_ocr",
                    "ocr_attempted": True,
                    "media_count": len(urls),
                },
            )
            if not upgraded:
                # A better source (e.g. explicit text coords) is already stored;
                # do not clobber it, but still ensure a drift is requested.
                self._auto_drift_if_live(event_id, force=False)
                return
            # The event now carries the OCR'd position. If a drift was already
            # started from the weaker fallback position, unblock and recompute.
            intel_store.update_metadata(event_id, metadata={"drift_status": "superseded"})
            self._auto_drift_if_live(event_id, force=True)
        except Exception as exc:
            logger.debug("X (twikit) media OCR enrichment failed for %s: %s", event_id, exc)

    def _schedule_media_ocr(self, tweet_id: str, event_id: str, urls: list[str]) -> None:
        threading.Thread(
            target=self._apply_media_ocr,
            args=(event_id, urls),
            daemon=True,
            name=f"intel-x-ocr-{tweet_id[-8:]}",
        ).start()

    def _auto_drift_if_live(self, event_id: str, *, force: bool = False) -> None:
        """Auto-drift for a new live episode, unless one already ran (or is running).

        `force=True` is used after an OCR position upgrade: the previously
        scheduled drift (if any) used the weaker fallback coordinates, so the
        shared model slot is unblocked and the drift is recomputed.
        """
        if not config.INTEL_AUTO_DRIFT_ENABLED:
            return
        stored = intel_store.get(event_id)
        if stored is None or stored.lat is None or stored.lon is None:
            return
        if stored.metadata.get("drift_status") in {"computing", "completed"} and not force:
            return
        try:
            request_auto_drift(stored.id, stored.lat, stored.lon, vessel_type="rubber_boat")
        except Exception as exc:
            logger.debug("X (twikit) auto-drift deferred for %s: %s", event_id, exc)

    def _ingest(self, tweet: Any, handle: str) -> bool:
        original = getattr(tweet, "retweeted_tweet", None)
        if original is not None and getattr(original, "id", None) is not None:
            return self._thread_repost(tweet, handle, original, kind="repost")

        quoted = self._quoted_tweet(tweet)
        if quoted is not None:
            quoted_parent = intel_store.find_by_tweet_id(str(quoted.id))
            if quoted_parent is not None:
                # Amplifying an already-tracked incident — thread it like a
                # repost (no new marker, no re-broadcast), but keep the
                # caption: unlike a plain RT a quote often carries new
                # operational info (e.g. "confirmed rescued").
                return self._thread_repost(tweet, handle, quoted, kind="quote")

        own_text = str(getattr(tweet, "text", "") or "")
        quoted_text = str(getattr(quoted, "text", "") or "") if quoted is not None else ""
        # The real distress content (and its GPS map screenshot) often lives
        # in the quoted tweet, not the tracked account's short caption — feed
        # both to distress/geo extraction so a terse "🆘" caption quoting a
        # full report is never silently dropped or mis-classified.
        combined_text = f"{own_text}\n{quoted_text}".strip() if quoted_text else own_text
        if len(combined_text) < 10:
            return False

        distress = is_direct_distress_call(combined_text)
        resolved = is_resolved_distress(combined_text)
        severity = classify_severity(combined_text) if distress else "low"
        author = ""
        try:
            user = tweet.user
            author = str(getattr(user, "screen_name", "") or "")
        except Exception:
            pass

        # Alarm Phone (and the tracked SAR NGOs) publish the real GPS position
        # as a map screenshot. Priority: explicit text coords > OCR of attached
        # images > declared relative offset > place-name centroid.
        text_coords = extract_numeric_coords(combined_text)
        media_urls = self._tweet_media_urls(tweet, tweet_id=str(tweet.id))
        if quoted is not None:
            for url in self._tweet_media_urls(quoted, tweet_id=str(quoted.id)):
                if url not in media_urls:
                    media_urls.append(url)
        media_count = len(media_urls)
        ocr_pending = False
        if distress and not text_coords and media_count:
            if shutil.which("tesseract"):
                ocr_pending = True
            else:
                # The real GPS position is almost certainly in the images but the
                # OCR engine is not installed (e.g. Docker image built without
                # tesseract) — say so instead of silently keeping a centroid.
                logger.warning(
                    "X (twikit) distress tweet %s has %d media image(s) but tesseract "
                    "is not installed; image OCR skipped (coordinate falls back to "
                    "text/place extraction)",
                    tweet.id,
                    media_count,
                )
        media_coords: Optional[tuple[float, float]] = None
        relative_coords = extract_relative_coords(combined_text) if not text_coords else None
        place_coords = (
            extract_coords(combined_text) if not (text_coords or relative_coords) else None
        )
        coords = text_coords or media_coords or relative_coords or place_coords
        coordinate_source = (
            "post_text" if text_coords
            else "media_ocr_text" if media_coords
            else "relative_place_offset" if relative_coords
            else "place_centroid" if place_coords
            else "none"
        )
        location_uncertainty_m = (
            250 if text_coords
            else 1500 if media_coords
            else 15_000 if relative_coords
            else 25_000 if place_coords
            else None
        )

        # Prefer the tracked account's own words for the title/display text;
        # fall back to the combined text only when the caption alone is too
        # thin to summarize (e.g. a bare "🆘" quoting a full report).
        title_source = own_text if len(own_text.strip()) >= 10 else combined_text
        display_text = own_text if own_text.strip() else combined_text

        event = IntelEvent(
            type="twitter",
            severity=severity,
            lat=coords[0] if coords else None,
            lon=coords[1] if coords else None,
            title=_make_title(title_source, author or handle),
            text=display_text[:500],
            url=f"https://x.com/i/web/status/{tweet.id}",
            source=author or handle,
            author=author or handle,
            timestamp_utc=self._timestamp(tweet),
            metadata={
                "tweet_id": str(tweet.id),
                "platform": "x",
                "source_policy": "operator_published" if distress else "unofficial",
                "publication_status": "published" if distress else "private",
                "is_distress": distress,
                "report_kind": "distress" if distress else ("resolved" if resolved else "news"),
                "distress_classification": (
                    "direct_call" if distress else ("resolved" if resolved else "context")
                ),
                "coordinate_source": coordinate_source,
                "coordinate_review_status": (
                    "machine_ocr_unverified"
                    if coordinate_source == "media_ocr_text"
                    else "not_required"
                ),
                # TWIKIT_ACCOUNTS is a curated allowlist of known SAR/humanitarian
                # NGOs (Alarm Phone, MSF, Sea-Watch, ...), not an open public-tweet
                # scrape — their own testimony deserves the "partner" trust tier,
                # not the same generic bucket as anonymous public chatter.
                "verification_status": (
                    "machine_extracted_unverified"
                    if coordinate_source == "media_ocr_text"
                    else "partner_reported"
                ),
                "location_uncertainty_m": location_uncertainty_m,
                "media_count": media_count,
                "media_transport": "x_media_ocr" if ocr_pending else "none",
                "ocr_attempted": False,
                "provenance": "twikit_account_timeline",
                "tracked_account": handle,
                "quoted_tweet_id": str(quoted.id) if quoted is not None else None,
                "quoted_tweet_url": (
                    f"https://x.com/i/web/status/{quoted.id}" if quoted is not None else None
                ),
            },
        )
        added = intel_store.add(event, dedup_key=f"x:{tweet.id}")
        if added and self._alerts_enabled:
            self._notify(event)
        if ocr_pending and added:
            # The real position is almost certainly in the images — OCR in a
            # background thread, then upgrade the stored position and drift on
            # the corrected coordinates (never block the 45 s poll loop).
            self._schedule_media_ocr(str(tweet.id), event.id, media_urls)
        elif not added and coords:
            # Re-seen tweet (this or another collector) carrying a better
            # position — enrich the stored event instead of creating a dup.
            location_metadata = {
                key: value
                for key, value in event.metadata.items()
                if key not in {"first_source_seen_at", "last_source_seen_at", "source_scan_count"}
            }
            intel_store.enrich_location(
                event.id,
                lat=coords[0],
                lon=coords[1],
                metadata=location_metadata,
            )
        if (
            added
            and distress
            and config.INTEL_AUTO_DRIFT_ENABLED
            and event.lat is not None
            and event.lon is not None
            and event.metadata.get("drift_status") not in {"computing", "completed"}
            and not ocr_pending
        ):
            # With OCR pending the drift fires from the worker once the image
            # position is known, so the cone never uses a centroid fallback.
            try:
                request_auto_drift(event.id, event.lat, event.lon, vessel_type="rubber_boat")
            except Exception as exc:
                logger.debug("X (twikit) auto-drift deferred for %s: %s", event.id, exc)
        return added

    def _thread_repost(
        self, repost: Any, handle: str, original: Any, *, kind: str = "repost"
    ) -> bool:
        """A repost/quote must answer the SAME thread, never spawn a new marker.

        If the original alert is already tracked in the store, the repost is
        recorded onto that incident's thread bookkeeping without touching any
        field the live edge publishes (no version bump, no marker update). If
        the original was never seen, the original content is ingested so the
        signal is not lost.

        A quote tweet (``kind="quote"``) additionally carries the quoting
        account's own caption, which — unlike a plain RT — can be new
        operational information (e.g. "confirmed rescued"), so it is kept as
        a ``note`` on the thread record instead of being discarded.
        """
        original_id = str(getattr(original, "id", "") or "")
        repost_id = str(getattr(repost, "id", "") or "")
        if not original_id:
            return False

        parent = intel_store.find_by_tweet_id(original_id)
        if parent is None:
            return self._ingest(original, handle)

        record: dict[str, Any] = {
            "tweet_id": repost_id,
            "posted_at": self._timestamp(repost),
            "url": f"https://x.com/i/web/status/{repost_id}",
            "kind": kind,
        }
        if kind == "quote":
            note = str(getattr(repost, "text", "") or "").strip()
            if note:
                record["note"] = note[:200]
        added = intel_store.append_thread_repost(parent.id, record)
        if added:
            logger.info(
                "X (twikit) %s %s by @%s threaded onto incident %s (no new event)",
                kind,
                repost_id,
                handle,
                parent.id,
            )
        return False

    def _notify(self, event: IntelEvent) -> None:
        """Fire-and-forget Telegram notification when a tracked account posts."""
        try:
            from core.notifications import telegram
        except Exception:
            return
        kind = event.metadata.get("report_kind", "news")
        account = event.author or event.metadata.get("tracked_account", "X")
        if kind == "distress":
            header = f"🚨 DISTRESS — @{account}"
        elif kind == "resolved":
            header = f"✅ RESOLVED — @{account}"
        else:
            header = f"📰 @{account}"
        location = ""
        if event.lat is not None and event.lon is not None:
            location = f"\n🌍 {event.lat:.4f}, {event.lon:.4f}"
        body = (
            f"{header}\n"
            f"Severità: {event.severity.upper()}\n"
            f"{event.text[:220]}{'…' if len(event.text) > 220 else ''}"
            f"{location}\n"
            f"🔗 {event.url}"
        )
        threading.Thread(target=telegram, args=(body,), daemon=True, name="intel-x-twikit-alert").start()

    @staticmethod
    def _timestamp(tweet: Any) -> str:
        try:
            created = getattr(tweet, "created_at_datetime", None)
            if created:
                return created.isoformat()
        except Exception:
            pass
        try:
            created_raw = getattr(tweet, "created_at", "")
            if created_raw:
                parsed = datetime.strptime(created_raw, "%a %b %d %H:%M:%S %z %Y")
                return parsed.isoformat()
        except Exception:
            pass
        return datetime.now(UTC).isoformat()
