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


def test_not_under_command_never_fuses_with_a_nearby_gap_into_a_security_alert() -> None:
    """docs/fixes.md M-04: `_rule_vessel_mobility_episode` (removed) used to
    fuse a self-reported nav status with an unrelated AIS movement anomaly
    on the same MMSI into a single grey_zone `vessel_mobility_anomaly`
    alert -- single-signal promotion to intelligence from a benign
    self-report, exactly what fixes.md prohibits. NUC still opens its own
    single-source case (an operator legitimately wants to review a
    sustained NUC report) but now correctly tagged Maritime Safety, and a
    nearby unrelated AIS gap must not be able to escalate it."""
    now = datetime.now(timezone.utc)
    _add(
        type="ais_anomaly", severity="medium", lat=35.41, lon=13.01,
        title="AIS gap — TANKER B", source="ais", linked_mmsi="352001914",
        timestamp_utc=(now - timedelta(hours=1)).isoformat(),
        metadata={"anomaly_type": "gap", "maritime_domain": "grey_zone"},
    )
    incident = _add(
        type="vessel_incident", severity="medium", lat=35.40, lon=13.00,
        title="Vessel unable to manoeuvre — TANKER B", source="ais",
        linked_mmsi="352001914",
        metadata={"ais_nav_status_kind": "not_under_command"},
    )

    fusion.evaluate(incident)

    alerts = _alerts()
    assert len(alerts) == 1  # not two, and not a fused mobility alert
    alert = alerts[0]
    assert alert.metadata["alert_type"] == "vessel_casualty"
    assert alert.metadata["maritime_domain"] == "safety"
    assert alert.metadata["contributing"] == [incident.id]

    from core.db.models import CaseDB
    from core.db.session import session_scope

    with session_scope() as db:
        cases = db.query(CaseDB).all()
        assert len(cases) == 1
        assert cases[0].case_type == "vessel_incident"


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
        metadata={"anomaly_type": "ais_rendezvous", "maritime_domain": "grey_zone",
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


def test_neutral_rendezvous_cannot_create_a_sanctions_allegation_by_itself() -> None:
    """docs/fixes.md M0.3 exit gate: a plain STS pair -- not a tanker, not a
    dark party, not in a known STS zone, no corroborating sanctions/identity
    signal -- must stay a neutral, internal observation. It still gets a
    low-severity alert (two vessels co-located is worth recording), but
    never a sanctions-shaped domain and never an auto-opened case."""
    ev = _add(
        type="ais_rendezvous", severity="medium", lat=40.1, lon=25.3,
        title="STS rendezvous — C / D", source="mda", linked_mmsi="273000001",
        metadata={"anomaly_type": "ais_rendezvous", "maritime_domain": "grey_zone",
                  "service": "maritime", "lane": "intelligence",
                  "observation_type": "rendezvous", "publication_status": "internal",
                  "tanker": False, "dark": False, "sts_zone": None,
                  "vessels": [{"mmsi": "273000001"}, {"mmsi": "273000002"}]},
    )
    fusion.evaluate(ev)
    alerts = _alerts()
    assert len(alerts) == 1
    assert alerts[0].metadata["alert_type"] == "sts_transfer"
    assert alerts[0].metadata["maritime_domain"] != "sanctions"
    from core.db.models import CaseDB
    from core.db.session import session_scope
    with session_scope() as db:
        assert db.query(CaseDB).count() == 0

    from core.intel.service_taxonomy import classify_service

    result = classify_service(ev)
    assert result.service == "maritime"
    assert result.lane == "intelligence"
    assert result.publishable is False


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


def test_relink_existing_case_by_mmsi_for_new_cluster_days_later() -> None:
    """A follow-up pair of AIS anomalies for the same vessel, days after the
    first, is a *fresh* cluster (new event ids -> new cluster_id) but is the
    same underlying incident. It must update the existing open case, not
    fork a duplicate one."""
    now = datetime.now(timezone.utc)
    _add(
        type="ais_anomaly", severity="high", lat=34.5, lon=13.2,
        title="dark zone entry", source="AISStream", linked_mmsi="209888000",
        timestamp_utc=(now - timedelta(hours=2)).isoformat(),
        metadata={"anomaly_type": "dark_zone_entry", "mmsi": "209888000"},
    )
    first_second = _add(
        type="ais_anomaly", severity="high", lat=34.6, lon=13.3,
        title="impossible speed", source="AISStream", linked_mmsi="209888000",
        metadata={"anomaly_type": "impossible_speed", "mmsi": "209888000"},
    )
    fusion.evaluate(first_second)
    assert len(_alerts()) == 1

    from core.db.models import CaseDB
    from core.db.session import session_scope

    with session_scope() as db:
        original_case_id = db.query(CaseDB).one().case_id

    # Roll the bounded in-memory windows past this cluster -- same technique
    # as test_recurring_cluster_upserts_one_db_row_after_dedup_window_rolls --
    # so the next pair is evaluated as an unrelated, brand new cluster.
    with intel_store._lock:
        intel_store._seen.clear()
        intel_store._events.clear()

    _add(
        type="ais_anomaly", severity="high", lat=34.55, lon=13.25,
        title="long gap", source="AISStream", linked_mmsi="209888000",
        timestamp_utc=(now - timedelta(minutes=10)).isoformat(),
        metadata={"anomaly_type": "long_gap", "mmsi": "209888000"},
    )
    second_pair_new = _add(
        type="ais_anomaly", severity="high", lat=34.56, lon=13.26,
        title="position jump", source="AISStream", linked_mmsi="209888000",
        metadata={"anomaly_type": "position_jump", "mmsi": "209888000"},
    )
    fusion.evaluate(second_pair_new)

    # The first cluster's alert IntelEvent was pushed out of the in-memory
    # store by the reset above (like the recurring-cluster regression test),
    # but both alerts are persisted -- two distinct clusters, confirming this
    # really is a fresh cluster_id and not a dedup no-op.
    from core.db.models import CaseIntelEventDB, IntelEventDB

    with session_scope() as db:
        alert_rows = db.query(IntelEventDB).filter(IntelEventDB.type == fusion.ALERT_TYPE).all()
        assert len(alert_rows) == 2
        assert alert_rows[0].id != alert_rows[1].id

        cases = db.query(CaseDB).all()
        assert len(cases) == 1, "second cluster for the same MMSI must relink, not fork a case"
        assert cases[0].case_id == original_case_id

        linked = {
            row.event_id
            for row in db.query(CaseIntelEventDB).filter(
                CaseIntelEventDB.case_id == original_case_id
            )
        }
        assert second_pair_new.id in linked


def test_no_relink_once_case_is_older_than_the_relink_window() -> None:
    """A case opened long before FUSION_CASE_RELINK_WINDOW_DAYS must not be
    silently reused -- an old, possibly-resolved-in-practice incident should
    not keep absorbing unrelated new reports for the same vessel forever."""
    now = datetime.now(timezone.utc)
    _add(
        type="ais_anomaly", severity="high", lat=34.5, lon=13.2,
        title="dark zone entry", source="AISStream", linked_mmsi="209777000",
        timestamp_utc=(now - timedelta(hours=2)).isoformat(),
        metadata={"anomaly_type": "dark_zone_entry", "mmsi": "209777000"},
    )
    first_second = _add(
        type="ais_anomaly", severity="high", lat=34.6, lon=13.3,
        title="impossible speed", source="AISStream", linked_mmsi="209777000",
        metadata={"anomaly_type": "impossible_speed", "mmsi": "209777000"},
    )
    fusion.evaluate(first_second)

    from core.db.models import CaseDB
    from core.db.session import session_scope

    with session_scope() as db:
        old_case = db.query(CaseDB).one()
        old_case.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)

    with intel_store._lock:
        intel_store._seen.clear()
        intel_store._events.clear()

    _add(
        type="ais_anomaly", severity="high", lat=34.55, lon=13.25,
        title="long gap", source="AISStream", linked_mmsi="209777000",
        timestamp_utc=(now - timedelta(minutes=10)).isoformat(),
        metadata={"anomaly_type": "long_gap", "mmsi": "209777000"},
    )
    second_pair_new = _add(
        type="ais_anomaly", severity="high", lat=34.56, lon=13.26,
        title="position jump", source="AISStream", linked_mmsi="209777000",
        metadata={"anomaly_type": "position_jump", "mmsi": "209777000"},
    )
    fusion.evaluate(second_pair_new)

    with session_scope() as db:
        assert db.query(CaseDB).count() == 2, "a 30-day-old case is outside the relink window"


def test_relink_existing_case_by_proximity_when_alert_has_no_mmsi() -> None:
    """Most humanitarian SAR reports (a migrant dinghy) carry no MMSI at
    all -- the exact scenario reported live: a second post about a boat
    already tracked under an open case, days later, must update that case
    instead of opening a duplicate one for the same incident."""
    ev1 = _add(
        type="vessel_incident", severity="high", lat=35.40, lon=13.00,
        title="Cargo aground off Lampedusa", source="AIS incidents",
        metadata={"subtype": "aground"},
    )
    fusion.evaluate(ev1)
    assert len(_alerts()) == 1

    from core.db.models import CaseDB
    from core.db.session import session_scope

    with session_scope() as db:
        original_case_id = db.query(CaseDB).one().case_id

    # A day-later follow-up report, close by but not identical, no MMSI --
    # a fresh event id / cluster_id, same real-world incident.
    ev2 = _add(
        type="vessel_incident", severity="high", lat=35.41, lon=13.01,
        title="Same vessel still aground off Lampedusa, day 2",
        source="AIS incidents",
        metadata={"subtype": "grounding"},
    )
    fusion.evaluate(ev2)

    alerts = _alerts()
    assert len(alerts) == 2

    with session_scope() as db:
        cases = db.query(CaseDB).all()
        assert len(cases) == 1, "nearby follow-up report with no MMSI must relink by proximity"
        assert cases[0].case_id == original_case_id


def test_no_relink_by_proximity_beyond_relink_radius() -> None:
    """A same-type incident far enough away is a different boat, not an
    update -- it must still get its own case."""
    ev1 = _add(
        type="vessel_incident", severity="high", lat=35.40, lon=13.00,
        title="Cargo aground off Lampedusa", source="AIS incidents",
        metadata={"subtype": "aground"},
    )
    fusion.evaluate(ev1)

    # ~950 km away (well beyond FUSION_CASE_RELINK_RADIUS_KM's default 50 km).
    ev2 = _add(
        type="vessel_incident", severity="high", lat=36.0, lon=23.5,
        title="Cargo aground off Kythira", source="AIS incidents",
        metadata={"subtype": "aground"},
    )
    fusion.evaluate(ev2)

    from core.db.models import CaseDB
    from core.db.session import session_scope

    with session_scope() as db:
        assert db.query(CaseDB).count() == 2
