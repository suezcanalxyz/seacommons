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


def test_rss_ingest_records_a_source_observation_independent_of_classification(fresh_store):
    """docs/fixes.md M1.2: every RSS item gets a durable SourceObservation,
    regardless of how it's later classified -- before distress/severity is
    computed. Idempotent by (source, guid): a replayed ingest of the same
    item across a fresh monitor instance still yields one observation row."""
    from core.db.models import SourceObservationDB
    from core.db.session import session_scope
    from core.intel.source_observation import observation_id

    item = {
        "title": "Conference in Palermo about migration policy",
        "description": "Representatives will meet on land in Palermo next week.",
        "link": "https://example.org/palermo-conference",
        "guid": "palermo-conference-obs",
        "pub_date": _RECENT_RSS_DATE,
    }
    NewsMonitor()._ingest_rss_item(item, "Sea Watch")
    NewsMonitor()._ingest_rss_item(item, "Sea Watch")  # fresh instance, same item -- replay

    obs_id = observation_id("Sea Watch", "palermo-conference-obs")
    with session_scope() as db:
        rows = db.query(SourceObservationDB).filter(
            SourceObservationDB.source_name == "Sea Watch",
            SourceObservationDB.source_id == "palermo-conference-obs",
        ).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.observation_id == obs_id
        assert row.service == "humanitarian"
        assert row.lane == "review"
        assert row.observation_type == "source_post"
        assert row.source_policy == "official_rss"
        assert row.source_url == "https://example.org/palermo-conference"


def test_rss_ingest_still_classifies_normally_if_source_observation_write_fails(fresh_store, monkeypatch):
    """The observation write is best-effort and must never block real
    ingestion -- a broken DB session must not stop the item from being
    classified and stored as an IntelEvent."""
    def _boom(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr("core.db.session.session_scope", _boom)
    item = {
        "title": "Policy update requiring no coordinates",
        "description": "A contextual article, nothing operational.",
        "link": "https://example.org/write-failure",
        "guid": "write-failure-guid",
        "pub_date": _RECENT_RSS_DATE,
    }
    assert NewsMonitor()._ingest_rss_item(item, "Sea Watch") is True
    assert len(fresh_store.events()) == 1


def test_iom_source_observation_carries_the_expected_fields(fresh_store):
    """docs/fixes.md M1.2: the IOM archive path uses the same
    _record_source_observation helper as the RSS path, with its own
    service/lane (humanitarian/missing -- IOM's Missing Migrants project).
    Exercises the helper directly rather than mocking the IOM HTTP call --
    _poll_iom uses this exact same method for every incident it receives.
    """
    from core.db.models import SourceObservationDB
    from core.db.session import session_scope

    NewsMonitor._record_source_observation(
        service="humanitarian",
        lane="missing",
        source_name="IOM Missing Migrants",
        source_policy="archive",
        source_id="iom-incident-42",
        observed_at="2026-09-03T00:00:00+00:00",
        raw_payload='{"id": "iom-incident-42", "dead": 3, "missing": 5}',
        source_url="https://missingmigrants.iom.int/",
        lat=35.1,
        lon=14.2,
    )

    with session_scope() as db:
        row = db.query(SourceObservationDB).filter(
            SourceObservationDB.source_name == "IOM Missing Migrants",
            SourceObservationDB.source_id == "iom-incident-42",
        ).one()
        assert row.service == "humanitarian"
        assert row.lane == "missing"
        assert row.source_policy == "archive"
        assert row.lat == 35.1
        assert row.lon == 14.2
