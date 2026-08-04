import pytest

from core.intel.news_monitor import NewsMonitor
from core.intel.store import IntelStore


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
        "pub_date": "Fri, 17 Jul 2026 09:00:00 +0000",
    }
    assert m._ingest_rss_item(item, "SOS Méditerranée") is True
    evt = fresh_store.events()[0]
    assert evt.metadata["is_distress"] is False
    assert evt.type == "news"
    assert evt.metadata["publication_status"] == "private"


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
        "pub_date": "Fri, 17 Jul 2026 09:00:00 +0000",
    }
    assert m._ingest_rss_item(item, "SOS Méditerranée") is True
    evt = fresh_store.events()[0]
    assert evt.metadata["is_distress"] is True
    assert evt.metadata["publication_status"] == "private"
