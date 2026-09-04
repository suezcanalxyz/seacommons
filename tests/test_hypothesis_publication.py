# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M14.4: canonical publication policy wired into the public
Maritime Intelligence projection.

Exit gate, verbatim: "Maritime Intelligence public output must require
the hypothesis publication gate."
"""
from __future__ import annotations

from dataclasses import replace

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
