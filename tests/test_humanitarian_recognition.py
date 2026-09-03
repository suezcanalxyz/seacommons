# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M2: structured HumanitarianAssessment."""
from __future__ import annotations

from core.intel.humanitarian_recognition import assess


def test_multiple_quantities_stay_separate_fields_not_one_persons_count():
    """The explicit M2 rule: '50 aboard, 20 rescued, 3 missing' must not
    become one persons=50 field."""
    result = assess("50 aboard, 20 rescued, 3 missing after the boat capsized off Lampedusa")
    assert result.people.aboard == 50
    assert result.people.rescued == 20
    assert result.people.missing == 3
    assert result.people.dead is None


def test_dead_and_injured_are_also_distinct_from_aboard():
    result = assess("Boat capsized: 40 aboard, 2 dead, 5 injured, rescue underway")
    assert result.people.aboard == 40
    assert result.people.dead == 2
    assert result.people.injured == 5
    assert result.people.rescued is None


def test_french_role_terms_are_recognised():
    result = assess("Naufrage: 30 personnes à bord, 12 sauvés, 3 disparus")
    assert result.people.aboard == 30
    assert result.people.rescued == 12
    assert result.people.missing == 3


def test_italian_role_terms_are_recognised():
    result = assess("Naufragio al largo della Libia: 25 a bordo, 10 salvati, 2 morti")
    assert result.people.aboard == 25
    assert result.people.rescued == 10
    assert result.people.dead == 2


def test_direct_distress_call_is_active_and_operational():
    result = assess("🆘 MAYDAY 30 people in a rubber boat taking water off Libya, urgent rescue needed")
    assert result.lifecycle == "active"
    assert result.is_operational is True
    assert result.publication_recommendation == "publish"
    assert result.case_type == "distress"
    assert "direct_distress_call" in result.rule_ids


def test_resolved_report_gets_resolved_lifecycle_and_resolution_case_type():
    result = assess("Update: all 40 people were rescued and disembarked safely at the port of Lampedusa")
    assert result.lifecycle == "resolved"
    assert result.case_type == "resolution"


def test_retrospective_commemoration_is_advocacy_and_non_operational():
    result = assess("Marking the anniversary: remembering the victims of the shipwreck off Lampedusa")
    assert result.case_type == "advocacy"
    assert result.is_operational is False
    assert result.publication_recommendation == "review"


def test_source_identity_alone_does_not_create_distress():
    """docs/fixes.md M2 rule: source identity such as 'SOS Mediterranee'
    never creates distress by name alone."""
    result = assess("SOS Mediterranee is a humanitarian organisation operating search and rescue vessels.")
    assert result.case_type == "unknown_humanitarian"
    assert result.is_operational is False
    assert result.publication_recommendation == "review"
    assert "unclassified_case_type" in result.caveats


def test_vessel_details_are_extracted_when_present():
    result = assess("Rubber boat in distress, engine failure, taking on water, 20 people aboard")
    assert result.vessel.type_reported == "rubber boat"
    assert result.vessel.engine_status == "engine failure"
    assert result.vessel.condition == "taking on water"


def test_vessel_fields_are_none_when_not_mentioned():
    result = assess("20 people rescued near Lampedusa")
    assert result.vessel.type_reported is None
    assert result.vessel.condition is None
    assert result.vessel.engine_status is None


def test_approximate_marker_produces_a_caveat():
    result = assess("~30 people rescued off the coast of Libya")
    assert result.people.rescued == 30
    assert "approximate_count_marker_present" in result.caveats


def test_empty_text_never_raises():
    result = assess("")
    assert result.case_type == "unknown_humanitarian"
    assert result.people.aboard is None


def test_confidence_and_basis_reflect_matched_signals():
    result = assess("🆘 MAYDAY 30 people aboard, urgent rescue needed off Libya")
    assert result.confidence > 0.4
    assert "direct_distress_call" in result.confidence_basis
    assert any(b.startswith("people_count:aboard") for b in result.confidence_basis)


def test_reserved_v0_fields_are_present_but_empty():
    """Structural completeness against the full M2 schema -- these fields
    are reserved for a follow-up PR, not yet populated."""
    result = assess("Some humanitarian report with no operational content")
    assert result.needs == []
    assert result.actors == []
    assert result.location_claims == []
    assert result.temporal_claims == []
    assert result.resolution_evidence == []
