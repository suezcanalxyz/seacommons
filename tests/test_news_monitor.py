from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
from core.intel.news_monitor import NewsMonitor, _clean_rss_text
from core.intel.store import IntelStore

_RECENT_RSS_DATE = format_datetime(
    datetime.now(timezone.utc) - timedelta(hours=1),
    usegmt=True,
)


@pytest.fixture
def fresh_store(monkeypatch):
    store = IntelStore()
    monkeypatch.setattr("core.intel.news_monitor.intel_store", store)
    return store


def test_rss_policy_statement_is_not_distress(fresh_store):
    m = NewsMonitor()
    item = {
        "title": "31 organisations call on the EU to urgently end abusive migration cooperation",
        "description": (
            "Open letter urging the EU to stop cooperation that pushes "
            "migrants into the desert."
        ),
        "link": "https://www.sosmediterranee.org/open-letter/",
        "guid": "https://www.sosmediterranee.org/open-letter/",
        "pub_date": _RECENT_RSS_DATE,
    }
    assert m._ingest_rss_item(item, "SOS Méditerranée") is True
    evt = fresh_store.events()[0]
    assert evt.metadata["is_distress"] is False
    assert evt.type == "news"
    assert evt.metadata["publication_status"] == "private"
    assert evt.lat is None and evt.lon is None
    assert evt.metadata["coordinate_source"] == "none"
    assert evt.metadata["location_suppressed_reason"] == "non_operational_context"


def test_rss_active_distress_call_is_distress(fresh_store):
    m = NewsMonitor()
    item = {
        "title": "URGENT: 40 people in distress in the Central Mediterranean",
        "description": (
            "MAYDAY a boat with 40 people on board is sinking south of "
            "Lampedusa, rescue requested."
        ),
        "link": "https://www.sosmediterranee.org/urgent/",
        "guid": "https://www.sosmediterranee.org/urgent/",
        "pub_date": _RECENT_RSS_DATE,
    }
    assert m._ingest_rss_item(item, "SOS Méditerranée") is True
    evt = fresh_store.events()[0]
    assert evt.metadata["is_distress"] is True
    assert evt.metadata["publication_status"] == "private"
    assert evt.lat is not None and evt.lon is not None


def test_wordpress_sos_brand_footer_is_not_an_emergency(fresh_store):
    m = NewsMonitor()
    item = {
        "title": "Catania Court Acquits Crew Member",
        "description": (
            "The post Catania Court Acquits Crew Member appeared first on "
            "SOS MEDITERRANEE."
        ),
        "link": "https://www.sosmediterranee.org/court/",
        "guid": "https://www.sosmediterranee.org/court/",
        "pub_date": _RECENT_RSS_DATE,
    }

    assert _clean_rss_text(item) == "Catania Court Acquits Crew Member"
    assert m._ingest_rss_item(item, "SOS Méditerranée") is True
    evt = fresh_store.events()[0]
    assert evt.type == "news"
    assert evt.metadata["is_distress"] is False
    assert evt.lat is None and evt.lon is None


def test_news_place_name_never_becomes_incident_geometry(fresh_store):
    m = NewsMonitor()
    item = {
        "title": "Conference in Palermo about migration policy",
        "description": "Representatives will meet on land in Palermo next week.",
        "link": "https://example.org/palermo-conference",
        "guid": "palermo-conference",
        "pub_date": _RECENT_RSS_DATE,
    }

    assert m._ingest_rss_item(item, "Sea Watch") is True
    evt = fresh_store.events()[0]
    assert evt.type == "news"
    assert evt.lat is None and evt.lon is None


def test_rss_event_id_is_stable_across_monitor_restarts(fresh_store):
    item = {
        "title": "Policy update",
        "description": "A contextual article.",
        "link": "https://example.org/stable-item",
        "guid": "https://example.org/stable-item",
        "pub_date": _RECENT_RSS_DATE,
    }

    first = NewsMonitor()
    assert first._ingest_rss_item(item, "Sea Watch") is True
    event_id = fresh_store.events()[0].id
    assert event_id.startswith("rss") and len(event_id) == 16

    second = NewsMonitor()
    assert second._ingest_rss_item(item, "Sea Watch") is False
    assert fresh_store.events()[0].id == event_id


@pytest.mark.parametrize(
    ("title", "description"),
    [
        (
            "Was this negligent manslaughter? 11 dead after shipwreck off Malta",
            "Der Beitrag Was this negligent manslaughter erschien zuerst auf Sea-Watch e.V.",
        ),
        (
            "The far right turns saving lives into a smear campaign",
            "On May 11, the crew rescued a boat in distress and brought everyone to safety.",
        ),
        (
            "Over a thousand people missing in the Strait of Sicily",
            "Organisations call for procedures to identify the deceased.",
        ),
    ],
)
def test_retrospective_rss_articles_remain_unlocated_news(
    fresh_store, title, description,
):
    item = {
        "title": title,
        "description": description,
        "link": f"https://example.org/{abs(hash(title))}",
        "guid": f"guid:{title}",
        "pub_date": _RECENT_RSS_DATE,
    }

    assert NewsMonitor()._ingest_rss_item(item, "Sea Watch") is True
    evt = fresh_store.events()[0]
    assert evt.type == "news"
    assert evt.metadata["is_distress"] is False
    assert evt.lat is None and evt.lon is None
