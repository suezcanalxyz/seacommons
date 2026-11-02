# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M14.4: canonical publication policy wired into the public
Maritime Intelligence projection.

Exit gate, verbatim: "Maritime Intelligence public output must require
the hypothesis publication gate."
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from core.intel.hypothesis import new_hypothesis, transition
from core.intel.hypothesis_publication import public_hypothesis_collection
from core.intel.hypothesis_store import save_hypothesis
from core.intel.store import IntelEvent, intel_store


def _fresh():
    from core.db.models import InvestigationHypothesisDB
    from core.db.session import engine, session_scope

    InvestigationHypothesisDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(InvestigationHypothesisDB).delete()
    with intel_store._lock:
        intel_store._events.clear()
        intel_store._seen.clear()


def _add_event(event_id, mmsi="211879870"):
    intel_store.add(IntelEvent(
        id=event_id, type="ais_anomaly", severity="medium", lat=35.5, lon=14.1,
        title=f"AIS gap {event_id}", linked_mmsi=mmsi, source="mda",
        metadata={"anomaly_type": "gap"},
    ), dedup_key=event_id)


def test_unpublished_hypothesis_never_appears():
    _fresh()
    h = new_hypothesis("hyp:test:unpub", "dark_transit", ("subj:mmsi:211879870",))
    h = transition(h, "collecting", actor="test")
    save_hypothesis(h)

    result = public_hypothesis_collection()
    assert result["features"] == []


def test_published_hypothesis_appears_shaped_via_publication_policy():
    _fresh()
    _add_event("gapA")
    _add_event("gapB")

    h = new_hypothesis("hyp:test:pub", "dark_transit", ("subj:mmsi:211879870",))
    h = replace(
        h, reason_codes=("gap",), evidence_links=("gapA", "gapB"),
        evidence_stage="corroborated",
    )
    h = transition(h, "collecting", actor="test")
    h = transition(h, "review_ready", actor="test")
    h = transition(h, "assessed", actor="test")
    h = transition(h, "published", actor="test")
    save_hypothesis(h)

    result = public_hypothesis_collection()
    assert len(result["features"]) == 1
    feature = result["features"][0]
    assert feature["properties"]["hypothesis_type"] == "dark_transit"
    assert feature["properties"]["reason_codes"] == ("gap",)
    for field in ("linked_mmsi", "mmsi", "imo", "vessel_name"):
        assert field not in feature["properties"]


def test_a_hypothesis_forced_published_without_evidence_is_still_excluded():
    """A row with state='published' but no reason_codes/evidence_links
    (as if state had been written directly, bypassing transition()'s own
    gate) must still not appear -- project_public_maritime_assessed()
    re-verifies can_publish() itself rather than trusting the persisted
    state column alone."""
    _fresh()
    from core.db.models import InvestigationHypothesisDB
    from core.db.session import session_scope

    with session_scope() as db:
        db.add(InvestigationHypothesisDB(
            hypothesis_id="hyp:test:forced", hypothesis_type="dark_transit",
            subject_ids=["subj:mmsi:211879870"], state="published",
            reason_codes=[], evidence_links=[], evidence_stage="observed",
        ))

    result = public_hypothesis_collection()
    assert result["features"] == []


def test_published_hypothesis_with_excluded_subject_is_withheld_before_identity_is_redacted(monkeypatch):
    from core.intel.hypothesis_publication import _record_for_hypothesis
    from core.vessels import registry as registry_module

    monkeypatch.setitem(registry_module.registry._cache, "211879870", {"ship_type": 60})
    h = new_hypothesis("hyp:test:passenger", "dark_transit", ("subj:mmsi:211879870",))
    assert _record_for_hypothesis(h) is None
    monkeypatch.setitem(registry_module.registry._cache, "211879870", {"ship_type": 37})
    assert _record_for_hypothesis(h) is None
    monkeypatch.setitem(registry_module.registry._cache, "211879870", {"ship_type": 70})
    assert _record_for_hypothesis(h) is not None


def test_published_hypothesis_with_excluded_evidence_is_withheld(monkeypatch):
    from core.intel.hypothesis_publication import _record_for_hypothesis
    from core.intel import hypothesis_publication

    h = new_hypothesis("hyp:test:evidence", "dark_transit", ("subj:imo:9999999",))
    h = replace(h, evidence_links=("e1",))
    e = IntelEvent(id="e1", linked_mmsi="000000000", metadata={"ship_type": 66})
    monkeypatch.setattr(hypothesis_publication.intel_store, "get_durable", lambda _: e)
    assert _record_for_hypothesis(h) is None
    e.metadata = {"ship_type": 80}
    assert _record_for_hypothesis(h) is not None


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (35.5, 14.1, True),
        (0, 0, True),
        (90, 180, True),
        (91, 14.1, False),
        (-91, 14.1, False),
        (35.5, 181, False),
        (float("nan"), 14.1, False),
        (35.5, float("inf"), False),
        ("35.5", 14.1, False),
        (True, 14.1, False),
    ],
)
def test_public_hypothesis_wgs84_coordinates_are_finite_and_bounded(lat, lon, expected):
    from core.intel.hypothesis_publication import _has_valid_public_point

    assert _has_valid_public_point(lat, lon) is expected


@pytest.mark.parametrize(
    ("lat", "lon", "expected_count"),
    [(35.5, 14.1, 1), (91.0, 14.1, 0), (35.5, float("nan"), 0)],
)
def test_public_hypothesis_endpoint_drops_invalid_geojson_points(
    monkeypatch, lat, lon, expected_count,
):
    """The direct /live/hypotheses projection must not emit invalid GeoJSON."""
    from core.intel import hypothesis_publication as publication

    hypothesis = SimpleNamespace(
        hypothesis_id="hyp:test:wgs84",
        episode_id=None,
        live_expires_at=None,
    )
    monkeypatch.setattr(
        publication, "list_hypotheses",
        lambda state, limit: [hypothesis],
    )
    monkeypatch.setattr(
        publication, "_independent_episode_source_counts",
        lambda episode_ids: {},
    )
    monkeypatch.setattr(
        publication, "_record_for_hypothesis",
        lambda hypothesis: {"id": hypothesis.hypothesis_id, "lat": lat, "lon": lon},
    )
    monkeypatch.setattr(
        publication, "project_public_maritime_assessed",
        lambda record, hypothesis: dict(record),
    )

    result = publication.public_hypothesis_collection(limit=10)
    assert len(result["features"]) == expected_count
    assert result["meta"]["count"] == expected_count
    if expected_count:
        assert result["features"][0]["geometry"]["coordinates"] == [lon, lat]


@pytest.mark.parametrize(
    ("groups", "verification", "expected"),
    [
        (["ais_sensor_lineage", "gfw_sar"], "multi_source_corroborated", 2),
        (["ais_sensor_lineage", "ais"], "multi_source_corroborated", 0),
        ("ais,gfw_sar", "multi_source_corroborated", 0),
        ({"ais": True, "gfw_sar": True}, "multi_source_corroborated", 0),
        ([None, {"source": "gfw_sar"}], "multi_source_corroborated", 0),
        (None, "multi_source_corroborated", 0),
        (["ais", "gfw_sar"], "single_source_observed", 0),
    ],
)
def test_public_hypothesis_lineage_count_rejects_malformed_persisted_json(
    monkeypatch, groups, verification, expected,
):
    """Neither JSON object keys nor string characters are source lineages."""
    from contextlib import contextmanager

    from core.db import session as db_session
    from core.intel import hypothesis_publication as publication

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return [("episode:test", groups, verification)]

    class Session:
        def query(self, *_args):
            return Query()

    @contextmanager
    def fake_session_scope():
        yield Session()

    monkeypatch.setattr(db_session, "session_scope", fake_session_scope)
    result = publication._independent_episode_source_counts({"episode:test"})
    assert result == ({"episode:test": expected} if expected else {})
