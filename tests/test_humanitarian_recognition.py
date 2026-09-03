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


def test_role_word_before_the_count_is_also_recognised():
    """Italian commonly states the role before the number ('dispersi
    almeno 12 persone' = 'missing at least 12 people'), not just
    count-first -- found while ground-truthing the M2.1 corpus."""
    result = assess("Naufragio al largo della Libia, dispersi almeno 12 persone secondo i sopravvissuti")
    assert result.people.missing == 12


def test_a_filler_verb_between_count_and_role_does_not_block_the_match():
    """'45 people believed aboard' -- 'believed' sits between the count
    and the role marker; found while ground-truthing the M2.1 corpus."""
    result = assess("Boat missing since yesterday evening, no contact with the 45 people believed aboard")
    assert result.people.aboard == 45


def test_a_missing_report_is_active_even_without_a_distress_marker():
    """A 'boat missing, no contact' report is itself an ongoing search
    situation, not merely something that needs review to classify --
    found while ground-truthing the M2.1 corpus."""
    result = assess("Boat missing since yesterday evening, no contact with the 45 people believed aboard")
    assert result.case_type == "missing"
    assert result.lifecycle == "active"


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


def test_fields_stay_empty_when_nothing_matches():
    result = assess("Some humanitarian report with no operational content")
    assert result.needs == []
    assert result.actors == []
    assert result.location_claims == []
    assert result.temporal_claims == []
    assert result.resolution_evidence == []


def test_needs_extracts_a_controlled_vocabulary_not_free_text():
    result = assess("Boat in distress, medical assistance needed, no water, no fuel")
    assert set(result.needs) == {"medical_assistance", "water", "fuel"}


def test_actors_recognises_known_ngo_vessel_names():
    result = assess("Ocean Viking is proceeding to the position, Libyan coast guard also en route")
    assert "Ocean Viking" in result.actors
    assert "libyan_coast_guard" in result.actors


def test_actors_empty_when_no_known_responder_mentioned():
    result = assess("A boat with 20 people aboard is adrift near Lampedusa")
    assert result.actors == []


def test_location_claims_capture_named_places_and_relative_position():
    result = assess("Boat 90nm south of Lampedusa, drifting toward Libya")
    assert any("lampedusa" in claim.lower() for claim in result.location_claims)
    assert any("90" in claim and "south" in claim.lower() for claim in result.location_claims)


def test_temporal_claims_capture_relative_time_phrases():
    result = assess("No contact since yesterday evening, overnight silence, last seen 12 hours ago")
    assert any("since yesterday evening" in claim for claim in result.temporal_claims)
    assert any("overnight" in claim for claim in result.temporal_claims)
    assert any("12 hours ago" in claim for claim in result.temporal_claims)


def test_resolution_evidence_is_empty_when_not_resolved():
    result = assess("🆘 MAYDAY boat in distress, urgent rescue needed")
    assert result.resolution_evidence == []


def test_resolution_evidence_captures_the_matched_resolved_phrase():
    result = assess("Update: all 40 people were rescued and disembarked safely at the port of Lampedusa")
    assert result.resolution_evidence != []
    assert any("rescued" in evidence.lower() or "disembarked" in evidence.lower() for evidence in result.resolution_evidence)
