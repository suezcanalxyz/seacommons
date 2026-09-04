# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M14.3: InvestigationHypothesis persistence round-trip."""
from __future__ import annotations

from dataclasses import replace

from core.intel.hypothesis import new_hypothesis, transition
from core.intel.hypothesis_store import get_hypothesis, list_hypotheses, save_hypothesis


def _fresh_table():
    from core.db.models import InvestigationHypothesisDB
    from core.db.session import engine, session_scope

    InvestigationHypothesisDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(InvestigationHypothesisDB).delete()


def test_save_and_get_roundtrip():
    _fresh_table()
    h = new_hypothesis("hyp:test:1", "dark_transit", ("subj:mmsi:111000001",))
    h = transition(h, "collecting", actor="engine:test")
    h = replace(h, reason_codes=("isolated_gap",), evidence_links=("aisgap:111000001",))

    save_hypothesis(h)
    loaded = get_hypothesis("hyp:test:1")

    assert loaded is not None
    assert loaded.hypothesis_id == "hyp:test:1"
    assert loaded.hypothesis_type == "dark_transit"
    assert loaded.subject_ids == ("subj:mmsi:111000001",)
    assert loaded.state == "collecting"
    assert loaded.reason_codes == ("isolated_gap",)
    assert loaded.evidence_links == ("aisgap:111000001",)
    assert len(loaded.audit_history) == 1
    assert loaded.audit_history[0].old_state == "candidate"
    assert loaded.audit_history[0].new_state == "collecting"
    assert loaded.audit_history[0].actor == "engine:test"


def test_save_upserts_existing_row():
    _fresh_table()
    h = new_hypothesis("hyp:test:2", "position_spoofing", ("subj:mmsi:111000002",))
    save_hypothesis(h)
    assert get_hypothesis("hyp:test:2").state == "candidate"

    h2 = transition(h, "collecting", actor="engine:test")
    save_hypothesis(h2)

    loaded = get_hypothesis("hyp:test:2")
    assert loaded.state == "collecting"
    assert len(loaded.audit_history) == 1


def test_get_missing_hypothesis_returns_none():
    _fresh_table()
    assert get_hypothesis("hyp:does-not-exist") is None


def test_list_hypotheses_filters_by_type_and_state():
    _fresh_table()
    a = new_hypothesis("hyp:test:3a", "dark_transit", ("subj:mmsi:111000003",))
    b = transition(
        new_hypothesis("hyp:test:3b", "dark_transit", ("subj:mmsi:111000004",)),
        "collecting", actor="engine:test",
    )
    c = new_hypothesis("hyp:test:3c", "position_spoofing", ("subj:mmsi:111000005",))
    for h in (a, b, c):
        save_hypothesis(h)

    dark_transit = list_hypotheses(hypothesis_type="dark_transit")
    assert {h.hypothesis_id for h in dark_transit} == {"hyp:test:3a", "hyp:test:3b"}

    collecting = list_hypotheses(state="collecting")
    assert {h.hypothesis_id for h in collecting} == {"hyp:test:3b"}
