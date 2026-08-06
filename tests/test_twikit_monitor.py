# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import asyncio
import json

import pytest

from core.intel.store import IntelStore
from core.intel.twikit_monitor import TwikitMonitor


@pytest.fixture(autouse=True)
def _no_auto_drift_network(monkeypatch):
    # New distress episodes schedule an auto-drift over HTTP (request_auto_drift);
    # keep tests hermetic — never make a real network call to the API.
    monkeypatch.setattr("core.intel.twikit_monitor.request_auto_drift", lambda *args, **kwargs: True)


class _FakeUser:
    screen_name = "alarm_phone"
    id = "2980429169"


class _FakeMedia:
    """Mimics twikit's Media object: the image URL is exposed via the
    ``media_url``/``source_url`` properties, not a ``media_url_https`` attr."""

    def __init__(self, url: str, legacy_attrs: bool = False) -> None:
        self.media_url = url
        self.source_url = f"{url}?name=orig"
        self.url = "https://t.co/short"
        if legacy_attrs:
            self.media_url_https = url


class _FakeTweet:
    def __init__(
        self,
        tweet_id: str,
        text: str,
        original: object = None,
        media: list = None,
        extended_entities: dict = None,
        user: object = None,
        replies: list = None,
    ) -> None:
        self.id = tweet_id
        self.text = text
        self.user = user or _FakeUser()
        self.created_at_datetime = "2026-08-03T10:00:00+00:00"
        self.retweeted_tweet = original
        self.media = media or []
        self.replies = replies or []
        if extended_entities is not None:
            self.extended_entities = extended_entities


def _write_cookies(tmp_path, payload) -> str:
    path = tmp_path / "cookies.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_disabled_by_default_even_with_cookies_file(tmp_path):
    m = TwikitMonitor(enabled=False, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "b"}))
    assert m.configured is False


def test_requires_existing_cookies_file():
    assert TwikitMonitor(enabled=True, cookies_file="").configured is False
    assert TwikitMonitor(enabled=True, cookies_file="D:/does/not/exist.json").configured is False


def test_configured_when_enabled_and_file_exists(tmp_path):
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "b"}))
    assert m.configured is True


def test_accounts_default_to_ngo_registry_when_unset():
    from core.intel.ngo_registry import NGO_TWITTER_HANDLES

    m = TwikitMonitor(enabled=True)
    assert m.tracked_accounts == list(NGO_TWITTER_HANDLES)


def test_accounts_parsed_from_csv_without_at_prefix():
    m = TwikitMonitor(enabled=True, accounts="alarm_phone, @MSF_Sea, openarms_fund")
    assert m.tracked_accounts == ["alarm_phone", "MSF_Sea", "openarms_fund"]


def test_load_cookies_accepts_browser_export_array(tmp_path):
    payload = [
        {"name": "auth_token", "value": "tok123"},
        {"name": "ct0", "value": "ct0abc"},
        {"name": "guest_id", "value": "g"},
    ]
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, payload))
    assert m._load_cookies() == {"auth_token": "tok123", "ct0": "ct0abc", "guest_id": "g"}


def test_load_cookies_accepts_plain_dict(tmp_path):
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "tok123", "ct0": "ct0abc"}))
    assert m._load_cookies() == {"auth_token": "tok123", "ct0": "ct0abc"}


def test_build_client_rejects_missing_auth_cookies(tmp_path):
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"guest_id": "g"}))

    async def run() -> bool:
        try:
            await m._build_client()
            return False
        except RuntimeError:
            return True

    assert asyncio.run(run())


def test_build_client_accepts_auth_token_and_ct0(tmp_path):
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))

    async def run() -> bool:
        try:
            client = await m._build_client()
            return client is not None
        except RuntimeError:
            return False

    assert asyncio.run(run())


def test_ingest_tracked_account_tweets_are_ingested_regardless_of_distress(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet("111222333", "Operational update from the rescue vessel position update 35.5N 12.6E.")
    assert m._ingest(tweet, handle="alarm_phone") is True
    events = store.events()
    assert len(events) == 1
    assert events[0].metadata["source_policy"] == "unofficial"
    assert events[0].metadata["provenance"] == "twikit_account_timeline"
    assert events[0].metadata["tracked_account"] == "alarm_phone"
    assert events[0].metadata["report_kind"] == "news"
    assert events[0].metadata["is_distress"] is False
    assert events[0].author == "alarm_phone"
    assert m._ingest(tweet, handle="alarm_phone") is False


def test_ingest_marks_distress_and_geo(tmp_path, monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet("9", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E")
    assert m._ingest(tweet, handle="alarm_phone") is True
    evt = store.events()[0]
    assert evt.metadata["is_distress"] is True
    assert evt.metadata["report_kind"] == "distress"
    assert evt.metadata["distress_classification"] == "direct_call"
    assert evt.lat == 35.5 and evt.lon == 12.6
    # Credited by the specific tracked account, not a generic trust bucket.
    assert evt.metadata["verification_status"] == "alarm_phone_twitter"


def test_ingest_marks_resolved_posts_as_not_distress(tmp_path, monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet("10", "Rescued! All people are now safe thanks to #OceanViking.")
    assert m._ingest(tweet, handle="alarm_phone") is True
    evt = store.events()[0]
    assert evt.metadata["report_kind"] == "resolved"
    assert evt.metadata["is_distress"] is False


def test_ingest_concluded_mourning_report_is_news_not_distress(tmp_path, monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet(
        "11",
        "Shipwreck in the WesternMed. 8 survivors were found and hospitalised on Ibiza. "
        "4 people remain missing.",
    )
    assert m._ingest(tweet, handle="alarm_phone") is True
    evt = store.events()[0]
    assert evt.metadata["is_distress"] is False
    assert evt.metadata["report_kind"] == "news"


def test_ingest_sos_override_beats_concluded_outcome_wording(tmp_path, monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet(
        "12",
        "🆘 3 people at risk of pushback in the Evros area! They were found by the police. "
        "Since then we have no news from them.",
    )
    assert m._ingest(tweet, handle="alarm_phone") is True
    evt = store.events()[0]
    assert evt.metadata["is_distress"] is True
    assert evt.metadata["report_kind"] == "distress"


def test_ingest_retrospective_massacre_report_is_news(tmp_path, monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet(
        "15",
        "⚫️ Massacre in the #Atlantic. On July 18, a rescue operation off the coast of "
        "#Mauritania brought ashore 38 people who had left #Gambia on a boat carrying "
        "more than 150 people, after drifting at sea for 25 days.",
    )
    assert m._ingest(tweet, handle="alarm_phone") is True
    evt = store.events()[0]
    assert evt.metadata["is_distress"] is False
    assert evt.metadata["report_kind"] == "news"


def test_ingest_distress_is_published_news_is_private(tmp_path, monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    m._ingest(_FakeTweet("13", "MAYDAY 20 people boat sinking off Lampedusa"), handle="alarm_phone")
    m._ingest(_FakeTweet("14", "Operational update from the rescue vessel position update"), handle="alarm_phone")
    kinds = {e.metadata["report_kind"]: e.metadata for e in store.events()}
    assert kinds["distress"]["source_policy"] == "operator_published"
    assert kinds["distress"]["publication_status"] == "published"
    assert kinds["news"]["source_policy"] == "unofficial"
    assert kinds["news"]["publication_status"] == "private"


def test_notify_fires_telegram_on_new_post(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_telegram(text: str) -> bool:
        calls.append(text)
        return True

    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", IntelStore())
    monkeypatch.setattr("core.notifications.telegram", fake_telegram)
    m = TwikitMonitor(
        enabled=True,
        cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}),
        alerts_enabled=True,
    )
    tweet = _FakeTweet("77", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E")
    assert m._ingest(tweet, handle="alarm_phone") is True
    import time

    for _ in range(50):
        if calls:
            break
        time.sleep(0.05)
    assert calls, "telegram alert should have been sent"
    assert "DISTRESS" in calls[0]
    assert "alarm_phone" in calls[0]


def test_notify_disabled_when_alerts_off(monkeypatch, tmp_path):
    sent: list[str] = []

    def fake_telegram(text: str) -> bool:
        sent.append(text)
        return True

    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", IntelStore())
    monkeypatch.setattr("core.notifications.telegram", fake_telegram)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet("78", "MAYDAY boat sinking off Lampedusa")
    m._ingest(tweet, handle="alarm_phone")
    import time

    time.sleep(0.3)
    assert sent == []


def test_ingest_skips_very_short_tweets(tmp_path, monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    assert m._ingest(_FakeTweet("1", "hi"), handle="alarm_phone") is False
    assert len(store.events()) == 0


def test_priority_accounts_default_to_alarm_phone():
    assert TwikitMonitor().priority_accounts == ["alarm_phone"]


def test_priority_accounts_parsed_from_csv():
    m = TwikitMonitor(priority_accounts=" @MSF_Sea , alarm_phone ")
    assert m.priority_accounts == ["MSF_Sea", "alarm_phone"]


def test_interval_for_uses_priority_and_base_intervals():
    m = TwikitMonitor(
        accounts="alarm_phone,MSF_Sea",
        priority_accounts="alarm_phone",
        poll_interval_s=300,
        priority_poll_interval_s=45,
    )
    assert m._interval_for("alarm_phone") == 45
    assert m._interval_for("MSF_Sea") == 300


def test_loop_polls_only_due_accounts(monkeypatch):
    import core.intel.twikit_monitor as mod

    monkeypatch.setattr(mod, "_SLEEP_CAP_S", 0.01)
    fetched: list[str] = []
    m = TwikitMonitor(enabled=True, accounts="a,b", cookies_file="dummy.json")

    async def fake_build():
        return object()

    async def fake_fetch(client, handle):
        fetched.append(handle)
        m._running = False
        return []

    m._build_client = fake_build
    m._fetch_account = fake_fetch
    m._running = True
    m._next_poll_ts = {"a": 0.0, "b": 1e9}

    asyncio.run(m._async_loop())
    assert fetched == ["a"]
    assert m._next_poll_ts["b"] == 1e9
    assert m._next_poll_ts["a"] > 0


def test_backoff_grows_after_errors_and_resets_on_success():
    m = TwikitMonitor()
    d1 = m._next_delay(error="boom")
    d2 = m._next_delay(error="boom again")
    assert d2 > d1
    assert m._backoff > 0
    assert m._next_delay(error=None) >= 1.0
    assert m._backoff == 0.0


def test_repost_threads_onto_existing_alert_without_new_event(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("2001", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E")
    assert m._ingest(original, handle="alarm_phone") is True
    parent = store.events()[0]

    repost = _FakeTweet("2002", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E", original=original)
    assert m._ingest(repost, handle="alarm_phone") is False

    events = store.events()
    assert len(events) == 1
    assert events[0].id == parent.id
    posts = events[0].metadata.get("thread_reposts") or []
    assert len(posts) == 1
    assert posts[0]["tweet_id"] == "2002"
    assert posts[0]["url"].endswith("/2002")
    assert events[0].metadata["repost_count"] == 1
    assert events[0].metadata["last_repost_at"]


def test_repost_is_deduplicated_on_repeat(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("2010", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E")
    m._ingest(original, handle="alarm_phone")
    repost = _FakeTweet("2011", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E", original=original)
    assert m._ingest(repost, handle="alarm_phone") is False
    assert m._ingest(repost, handle="alarm_phone") is False
    assert store.events()[0].metadata["repost_count"] == 1


def test_repost_never_rebroadcasts_marker(monkeypatch, tmp_path):
    store = IntelStore()
    calls: list[str] = []
    store._fire_broadcast = lambda *a, **k: calls.append("broadcast")
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("2020", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E")
    m._ingest(original, handle="alarm_phone")
    calls.clear()
    repost = _FakeTweet("2021", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E", original=original)
    m._ingest(repost, handle="alarm_phone")
    assert calls == []


def test_repost_of_untracked_original_falls_back_to_ingest(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("2030", "MAYDAY 12 people boat in distress 34.0N 13.0E")
    repost = _FakeTweet("2031", "MAYDAY 12 people boat in distress 34.0N 13.0E", original=original)
    assert m._ingest(repost, handle="alarm_phone") is True
    events = store.events()
    assert len(events) == 1
    assert events[0].metadata["tweet_id"] == "2030"
    assert events[0].metadata["is_distress"] is True


class _FakeTimelineUser:
    """Mimics twikit's User.get_tweets("Tweets", ...) — the only call
    _check_self_replies makes, per tracked handle."""

    def __init__(self, user_id: str, tweets: list) -> None:
        self.id = user_id
        self._tweets = tweets

    async def get_tweets(self, kind: str, count: int = 20):
        assert kind == "Tweets"
        return self._tweets


class _FakeClient:
    def __init__(self, users_by_handle: dict) -> None:
        self._users = users_by_handle

    async def get_user_by_screen_name(self, handle: str):
        return self._users[handle]


def test_self_reply_threads_as_update_onto_active_incident(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("3001", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E")
    m._ingest(original, handle="alarm_phone")
    event_id = store.events()[0].id
    broadcasts: list[str] = []
    store._fire_broadcast = lambda event: broadcasts.append(event.id)

    reply = _FakeTweet("3002", "Rescued to #Lampedusa! Everyone arrived safely.", user=_FakeUser())
    refetched = _FakeTweet("3001", original.text, user=_FakeUser(), replies=[reply])
    client = _FakeClient({"alarm_phone": _FakeTimelineUser(_FakeUser.id, [refetched])})

    asyncio.run(m._check_self_replies(client))

    event = store.get(event_id)
    posts = event.metadata.get("thread_reposts") or []
    assert len(posts) == 1
    assert posts[0]["tweet_id"] == "3002"
    assert posts[0]["kind"] == "reply"
    assert "Rescued" in posts[0]["note"]
    assert broadcasts == [event_id]


def test_reply_from_a_different_account_is_not_threaded(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("3010", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E")
    m._ingest(original, handle="alarm_phone")
    event_id = store.events()[0].id

    class _OtherUser:
        screen_name = "random_account"
        id = "111111"

    stranger_reply = _FakeTweet("3011", "This happens all the time", user=_OtherUser())
    refetched = _FakeTweet("3010", original.text, user=_FakeUser(), replies=[stranger_reply])
    client = _FakeClient({"alarm_phone": _FakeTimelineUser(_FakeUser.id, [refetched])})

    asyncio.run(m._check_self_replies(client))

    assert not (store.get(event_id).metadata.get("thread_reposts") or [])


def test_self_reply_check_is_idempotent(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("3020", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E")
    m._ingest(original, handle="alarm_phone")
    event_id = store.events()[0].id

    reply = _FakeTweet("3021", "Rescued! All safe.", user=_FakeUser())
    refetched = _FakeTweet("3020", original.text, user=_FakeUser(), replies=[reply])
    client = _FakeClient({"alarm_phone": _FakeTimelineUser(_FakeUser.id, [refetched])})

    asyncio.run(m._check_self_replies(client))
    asyncio.run(m._check_self_replies(client))

    assert len(store.get(event_id).metadata.get("thread_reposts") or []) == 1


def test_self_reply_thread_with_stranger_reply_interleaved_is_still_threaded(monkeypatch, tmp_path):
    # Real production case (Alarm Phone, 38 people south of Crete): the
    # timeline's own reply-thread module mixes a stranger's reply in between
    # two of the author's own replies; only the two self-replies should be
    # threaded, regardless of their position in the list.
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("3030", "MAYDAY 38 people boat sinking off Crete 34.7N 24.8E")
    m._ingest(original, handle="alarm_phone")
    event_id = store.events()[0].id

    class _OtherUser:
        screen_name = "random_account"
        id = "111111"

    status_update = _FakeTweet("3031", "Still not resolved, 38 people still in danger", user=_FakeUser())
    stranger_reply = _FakeTweet("3032", "Please help find my family", user=_OtherUser())
    rescue_reply = _FakeTweet("3033", "Rescued by commercial vessel, all safe.", user=_FakeUser())

    refetched = _FakeTweet(
        "3030", original.text, user=_FakeUser(),
        replies=[status_update, stranger_reply, rescue_reply],
    )
    client = _FakeClient({"alarm_phone": _FakeTimelineUser(_FakeUser.id, [refetched])})

    asyncio.run(m._check_self_replies(client))

    posts = store.get(event_id).metadata.get("thread_reposts") or []
    threaded_ids = {p["tweet_id"] for p in posts}
    assert threaded_ids == {"3031", "3033"}


def _age_event(store: IntelStore, event_id: str, hours_old: float) -> None:
    from datetime import UTC, datetime, timedelta
    event = store.get(event_id)
    event.timestamp_utc = (datetime.now(UTC) - timedelta(hours=hours_old)).isoformat()


def test_stale_incident_flagged_when_tweet_vanishes_from_timeline(monkeypatch, tmp_path):
    # An old, still-unresolved incident whose tweet no longer shows up at all
    # in the account's recent timeline (deleted with no matching repost, so
    # the ingestion-side dead-link fix never had a repost to latch onto)
    # can't be auto-healed -- it must be surfaced instead of silently
    # sitting wrong on the live map.
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    sent = []
    monkeypatch.setattr("core.notifications.telegram", lambda text: sent.append(text) or True)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("3050", "MAYDAY 12 people boat sinking off Crete 34.5N 25.0E")
    m._ingest(original, handle="alarm_phone")
    event_id = store.events()[0].id
    _age_event(store, event_id, hours_old=8)

    other_tweet = _FakeTweet("3099", "Unrelated later post", user=_FakeUser())
    client = _FakeClient({"alarm_phone": _FakeTimelineUser(_FakeUser.id, [other_tweet])})

    asyncio.run(m._check_self_replies(client))
    import time as _time
    _time.sleep(0.05)  # telegram fires on a background thread

    assert event_id in m._flagged_unreachable
    assert any("3050" in t or "Crete" in t for t in sent) or sent  # alert fired


def test_recently_missing_tweet_is_not_flagged_yet(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    sent = []
    monkeypatch.setattr("core.notifications.telegram", lambda text: sent.append(text) or True)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("3060", "MAYDAY 12 people boat sinking off Crete 34.5N 25.0E")
    m._ingest(original, handle="alarm_phone")
    event_id = store.events()[0].id
    _age_event(store, event_id, hours_old=1)  # well under _UNREACHABLE_MIN_AGE_S

    other_tweet = _FakeTweet("3098", "Unrelated later post", user=_FakeUser())
    client = _FakeClient({"alarm_phone": _FakeTimelineUser(_FakeUser.id, [other_tweet])})

    asyncio.run(m._check_self_replies(client))

    assert event_id not in m._flagged_unreachable
    assert not sent


def test_stale_flag_is_not_repeated_on_second_check(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    sent = []
    monkeypatch.setattr("core.notifications.telegram", lambda text: sent.append(text) or True)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("3070", "MAYDAY 12 people boat sinking off Crete 34.5N 25.0E")
    m._ingest(original, handle="alarm_phone")
    event_id = store.events()[0].id
    _age_event(store, event_id, hours_old=10)

    other_tweet = _FakeTweet("3097", "Unrelated later post", user=_FakeUser())
    client = _FakeClient({"alarm_phone": _FakeTimelineUser(_FakeUser.id, [other_tweet])})

    asyncio.run(m._check_self_replies(client))
    asyncio.run(m._check_self_replies(client))
    import time as _time
    _time.sleep(0.05)

    assert len(sent) == 1


def test_reply_check_ignores_timeline_tweets_not_tracked_as_incidents(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("3040", "MAYDAY 12 people boat sinking off Crete 34.5N 25.0E")
    m._ingest(original, handle="alarm_phone")
    event_id = store.events()[0].id

    reply = _FakeTweet("3041", "Rescued! All safe.", user=_FakeUser())
    refetched = _FakeTweet("3040", original.text, user=_FakeUser(), replies=[reply])
    unrelated = _FakeTweet("9999", "New publication out now", user=_FakeUser())
    client = _FakeClient({"alarm_phone": _FakeTimelineUser(_FakeUser.id, [unrelated, refetched])})

    asyncio.run(m._check_self_replies(client))

    posts = store.get(event_id).metadata.get("thread_reposts") or []
    assert {p["tweet_id"] for p in posts} == {"3041"}


def test_non_repost_tweets_still_ingested_normally(tmp_path, monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    assert m._ingest(_FakeTweet("2040", "MAYDAY boat sinking off Lampedusa 35.5N 12.6E"), handle="alarm_phone") is True
    assert store.events()[0].metadata.get("repost_count") is None


def test_repost_record_carries_repost_kind_without_note(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("6001", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E")
    m._ingest(original, handle="alarm_phone")
    repost = _FakeTweet("6002", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E", original=original)
    m._ingest(repost, handle="alarm_phone")
    record = store.events()[0].metadata["thread_reposts"][0]
    assert record["kind"] == "repost"
    assert "note" not in record


def test_quote_of_untracked_original_merges_caption_and_quoted_geo(tmp_path, monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    quoted = _FakeTweet("4001", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E")
    caption = _FakeTweet("4002", "🆘")
    caption.quote = quoted
    assert m._ingest(caption, handle="alarm_phone") is True
    events = store.events()
    assert len(events) == 1
    evt = events[0]
    assert evt.metadata["is_distress"] is True
    assert evt.metadata["tweet_id"] == "4002"
    assert evt.metadata["quoted_tweet_id"] == "4001"
    assert evt.metadata["quoted_tweet_url"].endswith("/4001")
    assert evt.lat == 35.5 and evt.lon == 12.6


def test_quote_of_tracked_incident_threads_with_note_instead_of_new_marker(monkeypatch, tmp_path):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    original = _FakeTweet("5001", "MAYDAY 20 people boat sinking off Lampedusa 35.5N 12.6E")
    assert m._ingest(original, handle="alarm_phone") is True

    quote = _FakeTweet("5002", "Confirmed: all 20 people rescued safely.")
    quote.quote = original
    assert m._ingest(quote, handle="alarm_phone") is False

    events = store.events()
    assert len(events) == 1
    record = events[0].metadata["thread_reposts"][0]
    assert record["tweet_id"] == "5002"
    assert record["kind"] == "quote"
    assert record["note"] == "Confirmed: all 20 people rescued safely."


def test_quote_media_is_merged_into_ocr_candidate_urls(tmp_path, monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    monkeypatch.setattr("core.intel.twikit_monitor.shutil.which", lambda name: "/usr/bin/tesseract")
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    quoted = _FakeTweet(
        "4010",
        "🆘 38 lives at risk south of #Crete! #Greece",
        media=[_FakeMedia("https://pbs.twimg.com/media/map.jpg")],
    )
    caption = _FakeTweet("4011", "Sharing this")
    caption.quote = quoted
    assert m._tweet_media_urls(caption) == []
    assert m._tweet_media_urls(quoted) == ["https://pbs.twimg.com/media/map.jpg?name=orig"]
    assert m._ingest(caption, handle="alarm_phone") is True
    evt = store.events()[0]
    assert evt.metadata["media_count"] == 1
    assert evt.metadata["media_transport"] == "x_media_ocr"


def test_tweet_media_urls_media_attr_filtered_to_twimg(tmp_path):
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet(
        "3000",
        "🆘 38 lives at risk south of #Crete! #Greece",
        media=[_FakeMedia("https://pbs.twimg.com/media/map.jpg"), _FakeMedia("http://insecure/x.jpg")],
    )
    assert m._tweet_media_urls(tweet) == ["https://pbs.twimg.com/media/map.jpg?name=orig"]


def test_tweet_media_urls_accepts_legacy_media_url_https_attr(tmp_path):
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet(
        "3009",
        "🆘 38 lives at risk south of #Crete! #Greece",
        media=[_FakeMedia("https://pbs.twimg.com/media/map.jpg", legacy_attrs=True)],
    )
    assert m._tweet_media_urls(tweet) == ["https://pbs.twimg.com/media/map.jpg?name=orig"]


def test_tweet_media_urls_extended_entities_fallback(tmp_path):
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet(
        "3001",
        "🆘 38 lives at risk south of #Crete! #Greece",
        extended_entities={"media": [{"media_url_https": "https://pbs.twimg.com/media/map.png"}]},
    )
    assert m._tweet_media_urls(tweet) == ["https://pbs.twimg.com/media/map.png"]


def test_tweet_media_urls_entities_fallback(tmp_path):
    # A third raw shape some twikit/twifork versions expose: plain (non
    # "extended") entities.media, tried only after both typed .media and
    # .extended_entities come up empty.
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet("3002", "🆘 38 lives at risk south of #Crete! #Greece")
    tweet.entities = {"media": [{"media_url_https": "https://pbs.twimg.com/media/entities.png"}]}
    assert m._tweet_media_urls(tweet) == ["https://pbs.twimg.com/media/entities.png"]


def test_tweet_media_urls_card_fallback(tmp_path):
    # Some map-tool posts attach the screenshot as a link-preview card
    # instead of native tweet media (e.g. posted through a scheduling tool).
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet("3003", "🆘 38 lives at risk south of #Crete! #Greece")

    class _FakeCard:
        thumbnail_url = "https://pbs.twimg.com/media/card.jpg"

    tweet.card = _FakeCard()
    assert m._tweet_media_urls(tweet) == ["https://pbs.twimg.com/media/card.jpg"]


def test_tweet_media_urls_returns_empty_when_every_shape_is_absent(tmp_path, caplog):
    # No media, no extended_entities, no entities, no card — must not raise,
    # and must log at debug (not warning, since this is the ordinary case of
    # a tweet with no attached image at all).
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet("3004", "🆘 38 lives at risk south of #Crete! #Greece")
    assert m._tweet_media_urls(tweet, tweet_id="3004") == []


def test_tweet_media_urls_warns_when_candidates_fail_host_allowlist(tmp_path, caplog):
    # A real regression signature: candidate URL(s) were found but none
    # matched pbs.twimg.com — this must be a WARNING (an actual extraction
    # gap), distinct from the ordinary "no image at all" debug case.
    import logging

    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet(
        "3005",
        "🆘 38 lives at risk south of #Crete! #Greece",
        media=[_FakeMedia("https://cdn.example.com/media/map.jpg")],
    )
    with caplog.at_level(logging.WARNING, logger="core.intel.twikit_monitor"):
        assert m._tweet_media_urls(tweet, tweet_id="3005") == []
    assert any("3005" in record.message for record in caplog.records)


def _ocr_gated_monitor(tmp_path, monkeypatch, which, *, drift_calls=None, scheduled=None):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    monkeypatch.setattr("core.intel.twikit_monitor.shutil.which", which)
    if scheduled is not None:
        monkeypatch.setattr(
            TwikitMonitor,
            "_schedule_media_ocr",
            lambda self, tweet_id, event_id, urls: scheduled.append((tweet_id, event_id, list(urls))),
        )
    if drift_calls is not None:
        monkeypatch.setattr(
            "core.intel.twikit_monitor.request_auto_drift",
            lambda *args, **kwargs: drift_calls.append(args),
        )
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    return m, store


def test_distress_with_media_schedules_ocr_and_defers_inline_drift(tmp_path, monkeypatch):
    scheduled: list = []
    drift_calls: list = []
    m, store = _ocr_gated_monitor(
        tmp_path,
        monkeypatch,
        lambda name: "/usr/bin/tesseract" if name == "tesseract" else None,
        drift_calls=drift_calls,
        scheduled=scheduled,
    )
    tweet = _FakeTweet(
        "3005",
        "🆘 38 lives at risk south of #Crete! #Greece",
        media=[_FakeMedia("https://pbs.twimg.com/media/map.jpg")],
    )
    assert m._ingest(tweet, handle="alarm_phone") is True
    evt = store.events()[0]
    assert evt.metadata["is_distress"] is True
    assert evt.metadata["media_count"] == 1
    assert evt.metadata["media_transport"] == "x_media_ocr"
    assert evt.metadata["ocr_attempted"] is False
    # provisional fallback (Crete sea-area) until the worker OCRs the image
    assert evt.metadata["coordinate_source"] == "region_area"
    assert evt.lat is not None
    # OCR is deferred to the worker, so no inline drift from the fallback point
    assert drift_calls == []
    assert len(scheduled) == 1
    assert scheduled[0][0] == "3005"
    assert scheduled[0][2] == ["https://pbs.twimg.com/media/map.jpg?name=orig"]


def test_text_coords_win_over_media_no_ocr(tmp_path, monkeypatch):
    scheduled: list = []
    m, store = _ocr_gated_monitor(
        tmp_path,
        monkeypatch,
        lambda name: "/usr/bin/tesseract" if name == "tesseract" else None,
        scheduled=scheduled,
    )
    tweet = _FakeTweet(
        "3006",
        "🆘 20 people boat sinking off Lampedusa 35.5N 12.6E",
        media=[_FakeMedia("https://pbs.twimg.com/media/map.jpg")],
    )
    assert m._ingest(tweet, handle="alarm_phone") is True
    evt = store.events()[0]
    assert evt.metadata["coordinate_source"] == "post_text"
    assert evt.lat == 35.5 and evt.lon == 12.6
    assert evt.metadata["media_transport"] == "none"
    assert scheduled == []


def test_non_distress_media_never_schedules_ocr(tmp_path, monkeypatch):
    scheduled: list = []
    m, store = _ocr_gated_monitor(
        tmp_path,
        monkeypatch,
        lambda name: "/usr/bin/tesseract" if name == "tesseract" else None,
        scheduled=scheduled,
    )
    tweet = _FakeTweet(
        "3007",
        "Operational update from the rescue vessel position update 35.5N 12.6E",
        media=[_FakeMedia("https://pbs.twimg.com/media/update.jpg")],
    )
    assert m._ingest(tweet, handle="alarm_phone") is True
    assert store.events()[0].metadata["media_transport"] == "none"
    assert scheduled == []


def test_no_ocr_when_tesseract_missing(tmp_path, monkeypatch):
    scheduled: list = []
    m, store = _ocr_gated_monitor(tmp_path, monkeypatch, lambda name: None, scheduled=scheduled)
    tweet = _FakeTweet(
        "3008",
        "🆘 38 lives at risk south of #Crete! #Greece",
        media=[_FakeMedia("https://pbs.twimg.com/media/map.jpg")],
    )
    assert m._ingest(tweet, handle="alarm_phone") is True
    evt = store.events()[0]
    assert scheduled == []
    assert evt.metadata["media_transport"] == "none"
    assert evt.metadata["coordinate_source"] == "region_area"


def test_media_ocr_upgrades_position_and_drifts(tmp_path, monkeypatch):
    drift_calls: list = []
    m, store = _ocr_gated_monitor(
        tmp_path,
        monkeypatch,
        lambda name: "/usr/bin/tesseract" if name == "tesseract" else None,
        drift_calls=drift_calls,
    )
    monkeypatch.setattr("core.intel.twikit_monitor._ocr_photo", lambda url: ((35.5, 24.9), True, "text"))
    tweet = _FakeTweet(
        "3010",
        "🆘 38 lives at risk south of #Crete! #Greece",
        media=[_FakeMedia("https://pbs.twimg.com/media/map.jpg")],
    )
    m._ingest(tweet, handle="alarm_phone")
    evt = store.events()[0]
    m._apply_media_ocr(evt.id, ["https://pbs.twimg.com/media/map.jpg"])
    evt = store.get(evt.id)
    assert evt.lat == 35.5 and evt.lon == 24.9
    assert evt.metadata["coordinate_source"] == "media_ocr_text"
    assert evt.metadata["ocr_attempted"] is True
    assert evt.metadata["media_transport"] == "x_media_ocr"
    assert drift_calls, "drift must fire with the OCR position"
    assert drift_calls[-1][1] == 35.5 and drift_calls[-1][2] == 24.9


def test_media_pin_landmark_fallback_upgrades_position_with_wider_uncertainty(tmp_path, monkeypatch):
    """A map screenshot with only a pin (no printed coordinates) should still
    upgrade the event's position via map_pin_geolocate, tagged distinctly
    from a text-OCR read and with a wider uncertainty radius."""
    drift_calls: list = []
    m, store = _ocr_gated_monitor(
        tmp_path,
        monkeypatch,
        lambda name: "/usr/bin/tesseract" if name == "tesseract" else None,
        drift_calls=drift_calls,
    )
    monkeypatch.setattr(
        "core.intel.twikit_monitor._ocr_photo",
        lambda url: ((35.19, 25.72), True, "pin_landmark"),
    )
    tweet = _FakeTweet(
        "3012",
        "🆘 38 lives at risk south of #Crete! #Greece",
        media=[_FakeMedia("https://pbs.twimg.com/media/map.jpg")],
    )
    m._ingest(tweet, handle="alarm_phone")
    evt = store.events()[0]
    m._apply_media_ocr(evt.id, ["https://pbs.twimg.com/media/map.jpg"])
    evt = store.get(evt.id)
    assert evt.lat == 35.19 and evt.lon == 25.72
    assert evt.metadata["coordinate_source"] == "media_pin_landmark"
    assert evt.metadata["location_uncertainty_m"] == 4000
    assert drift_calls, "drift must fire with the pin-geolocated position"


def test_precise_place_match_uses_tighter_uncertainty_radius(tmp_path, monkeypatch):
    # Fallback path only: extract_area (a real sea-only polygon, tried
    # first) succeeding is covered separately in test_area_extract.py and
    # the *_falls_back_to_plain_centroid tests below. This exercises what
    # happens when it can't build one at all (landmask/CMEMS unavailable).
    monkeypatch.setattr("core.intel.twikit_monitor.extract_area", lambda text, **kw: None)
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet("4001", "🆘 20 people boat sinking off Lampedusa")
    assert m._ingest(tweet, handle="alarm_phone") is True
    evt = store.events()[0]
    assert evt.metadata["coordinate_source"] == "place_centroid"
    assert evt.metadata["location_uncertainty_m"] == 25_000


def test_imprecise_place_match_uses_wider_uncertainty_radius(tmp_path, monkeypatch):
    # Real production case (Alarm Phone: "informed authorities in #Italy and
    # #Malta about a boat in severe weather") that resolved to a single
    # country-scale place name. A flat 25km radius for a country/sea-scale
    # match understated how imprecise the position actually was, and drew a
    # falsely tight-looking area on the public map. Fallback path only --
    # see the module docstring above.
    monkeypatch.setattr("core.intel.twikit_monitor.extract_area", lambda text, **kw: None)
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))
    tweet = _FakeTweet("4002", "🆘 30 people in grave distress off #Libya in bad weather")
    assert m._ingest(tweet, handle="alarm_phone") is True
    evt = store.events()[0]
    assert evt.metadata["coordinate_source"] == "place_centroid"
    assert evt.metadata["location_uncertainty_m"] == 120_000


def test_area_extraction_used_when_available_for_place_matches(tmp_path, monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.twikit_monitor.intel_store", store)
    drift_calls: list = []
    monkeypatch.setattr(
        "core.intel.twikit_monitor.request_auto_drift",
        lambda *args, **kwargs: drift_calls.append(args) or True,
    )
    m = TwikitMonitor(enabled=True, cookies_file=_write_cookies(tmp_path, {"auth_token": "a", "ct0": "c"}))

    from core.intel.area_extract import AreaResult
    fake_result = AreaResult(
        polygon={"type": "Polygon", "coordinates": [[[14.0, 35.0], [14.1, 35.0], [14.1, 35.1], [14.0, 35.0]]]},
        centroid=(35.05, 14.05),
        confidence="area",
        weather_narrowed=False,
    )
    monkeypatch.setattr("core.intel.twikit_monitor.extract_area", lambda text, **kw: fake_result)

    tweet = _FakeTweet("4003", "🆘 20 people boat sinking off Lampedusa")
    assert m._ingest(tweet, handle="alarm_phone") is True
    evt = store.events()[0]
    assert evt.metadata["coordinate_source"] == "region_area"
    assert evt.metadata["area_geojson"] == fake_result.polygon
    assert evt.metadata["area_confidence"] == "area"
    assert evt.lat == 35.05 and evt.lon == 14.05
    # No single defensible starting point for a leeway simulation.
    assert drift_calls == []


def test_async_loop_retries_session_setup_instead_of_giving_up():
    m = TwikitMonitor(enabled=True, accounts="a", cookies_file="dummy.json")
    m._next_delay = lambda error: 0.0  # skip real backoff sleep in the test

    attempts = {"n": 0}

    async def flaky_build():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient network error")
        return object()

    async def fake_fetch(client, handle):
        m._running = False
        return []

    m._build_client = flaky_build
    m._fetch_account = fake_fetch
    m._running = True
    m._next_poll_ts = {"a": 0.0}

    asyncio.run(m._async_loop())
    assert attempts["n"] == 2, "a failed session setup must be retried, not fatal"


def test_async_loop_rebuilds_session_after_consecutive_full_failures(monkeypatch):
    import core.intel.twikit_monitor as mod

    monkeypatch.setattr(mod, "_SESSION_REBUILD_AFTER_FAILURES", 2)
    m = TwikitMonitor(enabled=True, accounts="a", cookies_file="dummy.json")
    m._next_delay = lambda error: 0.0

    build_calls = {"n": 0}
    fetch_calls = {"n": 0}

    async def counting_build():
        build_calls["n"] += 1
        return object()

    async def failing_fetch(client, handle):
        fetch_calls["n"] += 1
        if fetch_calls["n"] >= 3:
            m._running = False
        raise RuntimeError("poll broke")

    m._build_client = counting_build
    m._fetch_account = failing_fetch
    m._running = True
    m._next_poll_ts = {"a": 0.0}

    asyncio.run(m._async_loop())
    assert build_calls["n"] == 2, "session should be rebuilt once the failure streak hits the threshold"
    assert fetch_calls["n"] == 3


def test_fetch_failure_evicts_cached_user_for_retry():
    m = TwikitMonitor(enabled=True, accounts="a", cookies_file="dummy.json")
    m._next_delay = lambda error: 0.0
    m._users["a"] = object()  # a stale/broken cached user object

    async def build():
        return object()

    async def fetch(client, handle):
        m._running = False
        raise RuntimeError("boom")

    m._build_client = build
    m._fetch_account = fetch
    m._running = True
    m._next_poll_ts = {"a": 0.0}

    asyncio.run(m._async_loop())
    assert "a" not in m._users


def test_media_ocr_failure_keeps_fallback_and_drifts(tmp_path, monkeypatch):
    drift_calls: list = []
    m, store = _ocr_gated_monitor(
        tmp_path,
        monkeypatch,
        lambda name: "/usr/bin/tesseract" if name == "tesseract" else None,
        drift_calls=drift_calls,
    )
    monkeypatch.setattr("core.intel.twikit_monitor._ocr_photo", lambda url: (None, True, "none"))
    tweet = _FakeTweet(
        "3011",
        "🆘 38 lives at risk south of #Crete! #Greece",
        media=[_FakeMedia("https://pbs.twimg.com/media/map.jpg")],
    )
    m._ingest(tweet, handle="alarm_phone")
    evt = store.events()[0]
    m._apply_media_ocr(evt.id, ["https://pbs.twimg.com/media/map.jpg"])
    evt = store.get(evt.id)
    assert evt.metadata["ocr_attempted"] is True
    assert evt.metadata["coordinate_source"] == "region_area"
    assert evt.lat is not None
    assert drift_calls and drift_calls[-1][1] == evt.lat and drift_calls[-1][2] == evt.lon
