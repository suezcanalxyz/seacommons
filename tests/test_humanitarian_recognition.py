# SPDX-License-Identifier: AGPL-3.0-or-later
"""core.intel.humanitarian_recognition -- V2 EN/IT/FR extractor (docs/prompt.md PHASE 2)."""
from __future__ import annotations

from core.intel.humanitarian_recognition import recognize

from tests.fixtures.alert_recognition import load_corpus, score


def _classify(row):
    inp = row.input
    a = recognize(inp.get("text", ""), source=inp.get("source", ""))
    return {
        "classification": a.incident_type,
        "lifecycle": a.lifecycle,
        "publication": a.publication,
        "confidence": a.confidence,
    }


def test_humanitarian_corpus_is_recognised_well():
    rows = load_corpus("humanitarian")
    report = score(rows, {row.id: _classify(row) for row in rows})
    # deterministic V2 must clear a real bar on the labelled corpus
    assert report.macro_f1() >= 0.75, report.as_dict()
    assert report.publication_accuracy >= 0.8, report.as_dict()
    assert report.confidence_in_range >= 0.7, report.mismatches


def test_multiple_counts_stay_distinct():
    a = recognize("~45 people aboard, 12 rescued, 3 missing, taking water", source="alarm_phone")
    assert a.incident_type == "distress"
    assert a.people["aboard"] == 45 and a.people["rescued"] == 12 and a.people["missing"] == 3
    assert a.people["approximate"] is True
    assert "taking_water" in a.vessel


def test_rescued_is_not_resolved_when_still_missing():
    a = recognize("The people were rescued but 4 are still missing.", source="alarm_phone")
    assert a.lifecycle == "needs_review"


def test_rescued_is_not_resolved_when_disembarkation_denied():
    a = recognize("All 60 rescued, but they have been denied disembarkation for days.", source="msf_sea")
    assert a.lifecycle == "needs_review"


def test_retrospective_is_not_an_active_incident():
    a = recognize("One year ago today, 27 people drowned here. We remember them.", source="alarm_phone")
    assert a.incident_type == "retrospective_incident"
    assert a.lifecycle == "concluded"
    assert a.publication == "internal"
    assert a.temporal["retrospective"] is True


def test_advocacy_never_published():
    a = recognize("Read our 2025 annual report on the website. Donate to support our ship.", source="sos_mediterranee")
    assert a.incident_type == "advocacy"
    assert a.publication == "internal"
    assert a.confidence <= 0.25


def test_french_and_italian_incident_types():
    fr = recognize("Le canot a chaviré cette nuit au large de la Libye, plusieurs disparus.", source="alarm_phone")
    assert fr.incident_type == "shipwreck"
    it = recognize("Intercettati dalla sedicente guardia costiera libica e riportati a Tripoli.", source="alarm_phone")
    assert it.incident_type == "interception"
    assert it.actors["interception_actor"] == "libyan_coast_guard"


def test_interception_actor_and_authorities():
    a = recognize("We alerted the authorities. The Libyan coast guard pulled the boat back.", source="alarm_phone")
    assert a.actors["authorities_contacted"] is True
    assert a.actors["interception_actor"] == "libyan_coast_guard"


def test_as_metadata_shape():
    meta = recognize("40 people in distress", source="alarm_phone").as_metadata()
    assert "humanitarian_assessment" in meta
    ha = meta["humanitarian_assessment"]
    assert ha["classification_version"].startswith("humanitarian_recognition/")
    assert set(ha) >= {"incident_type", "lifecycle", "people", "vessel", "needs", "actors", "temporal", "evidence"}


def test_overlay_is_off_by_default(monkeypatch):
    from core.intel.humanitarian import humanitarian_case_metadata

    meta = humanitarian_case_metadata(
        "40 people in distress, taking water", incident_id="1", source="alarm_phone", distress=True
    )
    assert "humanitarian_recognition_shadow" not in meta
    assert "humanitarian_recognition" not in meta
    assert meta["humanitarian_case_type"] == "distress"


def test_shadow_overlay_records_the_delta_without_changing_output(monkeypatch):
    monkeypatch.setattr("core.config.config.ALERT_RECOGNITION_V2_SHADOW", True)
    monkeypatch.setattr("core.config.config.ALERT_RECOGNITION_V2", False)
    from core.intel.humanitarian import humanitarian_case_metadata

    meta = humanitarian_case_metadata(
        "A boat capsized off Libya overnight, several missing.",
        incident_id="2", source="alarm_phone", distress=False,
    )
    assert "humanitarian_recognition_shadow" in meta
    assert meta["humanitarian_recognition_shadow"]["incident_type"] == "shipwreck"
    # V1 output is unchanged (its _case_type has no 'shipwreck')
    assert meta["humanitarian_case_type"] != "shipwreck"


def test_authoritative_overlay_lets_v2_own_the_case_type(monkeypatch):
    monkeypatch.setattr("core.config.config.ALERT_RECOGNITION_V2", True)
    from core.intel.humanitarian import humanitarian_case_metadata

    meta = humanitarian_case_metadata(
        "The Libyan coast guard intercepted the boat and returned them to Tripoli.",
        incident_id="3", source="alarm_phone", distress=False,
    )
    assert meta["humanitarian_incident_type"] == "interception"
    assert meta["humanitarian_case_type"] == "interception"
    assert meta["humanitarian_case_id"] == "HUM-X-3"  # legacy keys intact
