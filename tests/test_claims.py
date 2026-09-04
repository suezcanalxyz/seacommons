# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P0.4: Claim + assessment model.

Exit gate (v0-bounded, documented in the module itself): conflicting
people-count claims from different observations coexist as separate
rows; the assessment layer selects a value transparently (method_version
named "v0_latest_claim_wins") rather than silently overwriting.
"""
from __future__ import annotations

import time

import pytest

from core.intel.claims import (
    assessment_id,
    claim_id,
    get_assessment,
    record_claims_for_incident,
    sync_assessments_for_incident,
)
from core.intel.humanitarian_recognition import assess
from core.intel.store import IntelEvent


@pytest.fixture(autouse=True)
def _fresh_tables():
    from core.db.models import AssessmentDB, ClaimDB
    from core.db.session import engine, session_scope

    ClaimDB.__table__.create(bind=engine(), checkfirst=True)
    AssessmentDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(ClaimDB).delete()
        db.query(AssessmentDB).delete()
    yield


def _event(event_id, text, timestamp):
    return IntelEvent(id=event_id, type="distress", text=text, title=text[:80],
                       source="Alarm Phone", timestamp_utc=timestamp,
                       metadata={"is_distress": True})


def test_record_claims_only_for_non_none_people_fields():
    event = _event("c1", "50 aboard, 20 rescued, 3 missing", "2026-09-04T10:00:00Z")
    assessment = assess(event.text)
    recorded = record_claims_for_incident("c1", event, assessment)

    from core.db.models import ClaimDB
    from core.db.session import session_scope

    with session_scope() as db:
        rows = db.query(ClaimDB).filter(ClaimDB.claim_id.in_(recorded)).all()
        types = {r.claim_type: r.value for r in rows}
    assert types == {
        "people_aboard": {"count": 50},
        "people_rescued": {"count": 20},
        "people_missing": {"count": 3},
    }
    # not mentioned -- no dead/injured/intercepted/returned claim at all
    assert "people_dead" not in types


def test_re_recording_the_same_observation_does_not_duplicate():
    event = _event("c2", "30 people aboard", "2026-09-04T10:00:00Z")
    assessment = assess(event.text)
    first = record_claims_for_incident("c2", event, assessment)
    second = record_claims_for_incident("c2", event, assessment)
    assert first == second

    from core.db.models import ClaimDB
    from core.db.session import session_scope

    with session_scope() as db:
        count = db.query(ClaimDB).filter(ClaimDB.incident_id == "c2").count()
    assert count == 1


def test_conflicting_claims_from_different_observations_coexist():
    """docs/updates.md P0.4 exit gate: conflicting people/location/outcome
    claims can coexist -- a corrected count does not erase the earlier
    report, it adds a new claim."""
    e1 = _event("c3-a", "30 people aboard", "2026-09-04T10:00:00Z")
    e2 = _event("c3-b", "actually 35 people aboard, recount", "2026-09-04T11:00:00Z")
    record_claims_for_incident("c3", e1, assess(e1.text))
    record_claims_for_incident("c3", e2, assess(e2.text))

    from core.db.models import ClaimDB
    from core.db.session import session_scope

    with session_scope() as db:
        rows = db.query(ClaimDB).filter(
            ClaimDB.incident_id == "c3", ClaimDB.claim_type == "people_aboard",
        ).all()
        values = sorted(r.value["count"] for r in rows)
    assert values == [30, 35]


def test_sync_assessment_selects_the_most_recently_claimed_value():
    e1 = _event("c4-a", "30 people aboard", "2026-09-04T10:00:00Z")
    e2 = _event("c4-b", "update: 35 people aboard", "2026-09-04T11:00:00Z")
    record_claims_for_incident("c4", e1, assess(e1.text))
    record_claims_for_incident("c4", e2, assess(e2.text))
    sync_assessments_for_incident("c4")

    result = get_assessment("c4", "people_aboard")
    assert result is not None
    assert result["value"] == {"count": 35}
    assert set(result["supporting_claim_ids"]) == {
        claim_id("c4", "people_aboard", "c4-a"), claim_id("c4", "people_aboard", "c4-b"),
    }
    assert result["contradicting_claim_ids"] == []
    assert result["method_version"] == "v0_latest_claim_wins"


def test_sync_assessment_is_idempotent_and_reuses_the_same_row():
    event = _event("c5", "20 rescued", "2026-09-04T10:00:00Z")
    record_claims_for_incident("c5", event, assess(event.text))
    first_ids = sync_assessments_for_incident("c5")
    second_ids = sync_assessments_for_incident("c5")
    assert first_ids == second_ids
    assert first_ids == [assessment_id("c5", "people_rescued")]


def test_get_assessment_returns_none_for_unknown_incident():
    assert get_assessment("does-not-exist", "people_aboard") is None


def test_assessment_never_invents_a_value_for_a_claim_type_with_no_claims():
    event = _event("c6", "no numbers mentioned here", "2026-09-04T10:00:00Z")
    record_claims_for_incident("c6", event, assess(event.text))
    sync_assessments_for_incident("c6")
    assert get_assessment("c6", "people_aboard") is None


# ── subscriber wiring ────────────────────────────────────────────────────


def test_on_intel_event_records_claims_and_assessment_end_to_end():
    from core.intel.humanitarian_incident import _on_intel_event

    event = _event("c7", "MAYDAY 40 people aboard, 5 rescued so far", "2026-09-04T10:00:00Z")
    _on_intel_event(event)

    result = get_assessment("c7", "people_aboard")
    assert result is not None
    assert result["value"] == {"count": 40}
    assert get_assessment("c7", "people_rescued")["value"] == {"count": 5}
