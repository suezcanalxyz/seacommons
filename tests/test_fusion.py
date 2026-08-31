# SPDX-License-Identifier: AGPL-3.0-or-later
"""OSINT cross-source fusion engine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.intel import fusion
from core.intel.store import IntelEvent, intel_store


@pytest.fixture(autouse=True)
def _clean_store():
    with intel_store._lock:
        intel_store._events.clear()
        intel_store._seen.clear()
        intel_store._subscribers.clear()
    fusion._REGISTERED = False
    fusion._CORRELATION_ENGINE = None
    yield
    with intel_store._lock:
        intel_store._events.clear()
        intel_store._seen.clear()
        intel_store._subscribers.clear()


def _add(**kw) -> IntelEvent:
    kw.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
    ev = IntelEvent(**kw)
    intel_store.add(ev)
    return ev


def _alerts() -> list[IntelEvent]:
    return [e for e in intel_store.events(limit=100) if e.type == fusion.ALERT_TYPE]


def test_dark_fleet_spoofing_pair_opens_alert_and_case() -> None:
    now = datetime.now(timezone.utc)
    _add(
        type="ais_anomaly", severity="high", lat=34.5, lon=13.2,
        title="dark zone entry", source="AISStream",
        linked_mmsi="209999000",
        timestamp_utc=(now - timedelta(hours=2)).isoformat(),
        metadata={"anomaly_type": "dark_zone_entry", "mmsi": "209999000"},
    )
    second = _add(
        type="ais_anomaly", severity="high", lat=34.6, lon=13.3,
        title="impossible speed", source="AISStream",
        linked_mmsi="209999000",
        metadata={"anomaly_type": "impossible_speed", "mmsi": "209999000"},
    )

    fusion.evaluate(second)

    alerts = _alerts()
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.metadata["alert_type"] == "spoofing"
    assert alert.metadata["maritime_domain"] == "grey_zone"
    assert len(alert.metadata["contributing"]) == 2
    assert second.id in alert.metadata["contributing"]

    from core.db.models import CaseDB, CaseIntelEventDB
    from core.db.session import session_scope

    with session_scope() as db:
        cases = db.query(CaseDB).all()
        assert len(cases) == 1
        assert cases[0].case_type == "monitoring"
        links = db.query(CaseIntelEventDB).filter(CaseIntelEventDB.case_id == cases[0].case_id).all()
        assert {link.event_id for link in links} >= {second.id}


def test_spoofing_dedup_no_second_case_for_same_cluster() -> None:
    now = datetime.now(timezone.utc)
    _add(
        type="ais_anomaly", severity="high", lat=34.5, lon=13.2,
        title="gap", source="AISStream", linked_mmsi="211111000",
        timestamp_utc=(now - timedelta(hours=1)).isoformat(),
        metadata={"anomaly_type": "long_gap", "mmsi": "211111000"},
    )
    second = _add(
        type="ais_anomaly", severity="high", lat=34.55, lon=13.25,
        title="jump", source="AISStream", linked_mmsi="211111000",
        metadata={"anomaly_type": "position_jump", "mmsi": "211111000"},
    )
    fusion.evaluate(second)
    fusion.evaluate(second)  # a re-fire must not create a second alert/case

    assert len(_alerts()) == 1
    from core.db.models import CaseDB
    from core.db.session import session_scope

    with session_scope() as db:
        assert db.query(CaseDB).count() == 1


def test_single_anomaly_does_not_alert() -> None:
    ev = _add(
        type="ais_anomaly", severity="medium", lat=34.5, lon=13.2,
        title="lone gap", source="AISStream", linked_mmsi="212222000",
        metadata={"anomaly_type": "long_gap", "mmsi": "212222000"},
    )
    fusion.evaluate(ev)
    assert _alerts() == []


def test_not_under_command_and_gap_become_one_mobility_alert() -> None:
    now = datetime.now(timezone.utc)
    _add(
        type="ais_anomaly", severity="medium", lat=41.33, lon=29.14,
        title="AIS gap — ST. OLGA", source="ais", linked_mmsi="352001914",
        timestamp_utc=(now - timedelta(hours=1)).isoformat(),
        metadata={"anomaly_type": "gap", "maritime_domain": "grey_zone"},
    )
    incident = _add(
        type="vessel_incident", severity="medium", lat=41.34, lon=29.15,
        title="Vessel unable to manoeuvre — ST. OLGA", source="ais",
        linked_mmsi="352001914",
        metadata={"ais_nav_status_kind": "not_under_command", "maritime_domain": "grey_zone"},
    )

    fusion.evaluate(incident)

    assert len(_alerts()) == 1
    alert = _alerts()[0]
    assert alert.metadata["alert_type"] == "vessel_mobility_anomaly"
    assert alert.metadata["maritime_domain"] == "grey_zone"
    assert set(alert.metadata["contributing"]) == {
        next(e.id for e in intel_store.events(limit=20) if e.title == "AIS gap — ST. OLGA"),
        incident.id,
    }


def test_grey_zone_proximity_to_platform_alerts() -> None:
    # "Bouri" platform is at lon 13.2833, lat 32.8833 (core.api.routes.zones).
    ev = _add(
        type="ais_anomaly", severity="medium", lat=32.90, lon=13.30,
        title="loiter near platform", source="AISStream", linked_mmsi="213333000",
        metadata={"anomaly_type": "loiter", "mmsi": "213333000"},
    )
    fusion.evaluate(ev)
    alerts = _alerts()
    assert len(alerts) == 1
    assert alerts[0].metadata["alert_type"] == "infra_proximity"
    assert alerts[0].metadata["maritime_domain"] == "grey_zone"


def test_vessel_incident_single_source_opens_safety_case() -> None:
    ev = _add(
        type="vessel_incident", severity="high", lat=35.4, lon=13.0,
        title="Cargo aground off Lampedusa", source="AIS incidents",
        metadata={"subtype": "aground"},
    )
    fusion.evaluate(ev)
    alerts = _alerts()
    assert len(alerts) == 1
    assert alerts[0].metadata["alert_type"] == "vessel_casualty"

    from core.db.models import CaseDB
    from core.db.session import session_scope

    with session_scope() as db:
        cases = db.query(CaseDB).all()
        assert len(cases) == 1
        assert cases[0].case_type == "vessel_incident"


def test_gdacs_high_severity_alerts_without_case() -> None:
    ev = _add(
        type="gdacs", severity="high", lat=36.0, lon=15.0,
        title="Tropical storm — central Med", source="GDACS",
        metadata={},
    )
    fusion.evaluate(ev)
    assert len(_alerts()) == 1
    from core.db.models import CaseDB
    from core.db.session import session_scope

    with session_scope() as db:
        assert db.query(CaseDB).count() == 0


def test_dark_sts_rendezvous_opens_sanctions_case() -> None:
    ev = _add(
        type="ais_rendezvous", severity="high", lat=36.5, lon=22.7,
        title="Tanker STS rendezvous — A / B", source="mda", linked_mmsi="209111000",
        metadata={"anomaly_type": "ais_rendezvous", "maritime_domain": "sanctions",
                  "tanker": True, "dark": True, "sts_zone": "Laconian Gulf",
                  "vessels": [{"mmsi": "209111000"}, {"mmsi": "636222000"}]},
    )
    fusion.evaluate(ev)
    alerts = _alerts()
    assert len(alerts) == 1
    assert alerts[0].metadata["alert_type"] == "dark_sts"
    from core.db.models import CaseDB
    from core.db.session import session_scope
    with session_scope() as db:
        cases = db.query(CaseDB).all()
        assert len(cases) == 1 and cases[0].case_type == "dark_rendezvous"


def test_recurring_cluster_upserts_one_db_row_after_dedup_window_rolls() -> None:
    """Regression: a correlated_alert used to get a random id, so once the
    bounded in-memory dedup (intel_store._seen, capped at DEDUP_WINDOW; and
    _already_alerted's 300-event lookback) rolled past a cluster's earlier
    alert -- which high event volume does routinely in production -- the
    *same* recurring cluster (e.g. one STS pair) was re-inserted as a brand
    new row instead of updating in place. Observed in production: one STS
    pair alone produced 94k+ correlated_alert rows in two days."""
    ev = _add(
        type="ais_rendezvous", severity="high", lat=36.5, lon=22.7,
        title="Tanker STS rendezvous — A / B", source="mda", linked_mmsi="209111000",
        metadata={"anomaly_type": "ais_rendezvous", "maritime_domain": "sanctions",
                  "tanker": True, "sts_zone": "Laconian Gulf",
                  "vessels": [{"mmsi": "209111000"}, {"mmsi": "636222000"}]},
    )
    fusion.evaluate(ev)
    first_id = _alerts()[0].id

    # Simulate the bounded dedup windows having rolled past this cluster --
    # the actual production trigger is high event volume between recurrences,
    # not a restart, but the effect on these two structures is the same.
    with intel_store._lock:
        intel_store._seen.clear()
        intel_store._events.clear()

    fusion.evaluate(ev)  # the same underlying rendezvous, re-evaluated

    from core.db.models import IntelEventDB
    from core.db.session import session_scope
    with session_scope() as db:
        rows = db.query(IntelEventDB).filter(IntelEventDB.type == fusion.ALERT_TYPE).all()
        assert len(rows) == 1
        assert rows[0].id == first_id


def test_sanctioned_vessel_sighting_opens_case() -> None:
    ev = _add(
        type="vessel_identity", severity="high", lat=34.0, lon=18.0,
        title="Sanctioned vessel: SHADOW STAR", source="mda", linked_mmsi="273999000",
        metadata={"anomaly_type": "sdn_match", "maritime_domain": "sanctions"},
    )
    fusion.evaluate(ev)
    assert len(_alerts()) == 1
    assert _alerts()[0].metadata["alert_type"] == "sdn_match"


def test_register_is_idempotent() -> None:
    fusion.register()
    fusion.register()
    assert intel_store._subscribers.count(fusion.evaluate) == 1
