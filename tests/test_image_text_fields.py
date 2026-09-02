# SPDX-License-Identifier: AGPL-3.0-or-later
"""core.intel.image_text_fields -- structured OCR-text candidates (docs/prompt.md §9)."""
from __future__ import annotations

from core.intel.image_text_fields import (
    extract_needs,
    extract_people,
    extract_vessel_conditions,
)


def test_multiple_people_counts_stay_distinct():
    people = {p.kind: p for p in extract_people("45 people aboard, 12 rescued, 3 missing")}
    assert people["aboard"].count == 45
    assert people["rescued"].count == 12
    assert people["missing"].count == 3
    # each keeps the raw span that produced it
    assert "45" in people["aboard"].raw and "aboard" in people["aboard"].raw.lower()


def test_people_approximate_flag():
    (span,) = extract_people("about 30 people on board")
    assert span.kind == "aboard"
    assert span.count == 30
    assert span.approx is True


def test_people_children_and_women():
    kinds = {p.kind for p in extract_people("50 migrants including 6 children and 4 women")}
    assert {"children", "women"} <= kinds


def test_people_french_and_italian():
    fr = {p.kind: p.count for p in extract_people("60 personnes à bord, 3 disparus, 2 morts")}
    assert fr == {"aboard": 60, "missing": 3, "dead": 2}
    it = {p.kind: p.count for p in extract_people("70 persone a bordo, 5 dispersi")}
    assert it == {"aboard": 70, "missing": 5}


def test_vessel_conditions_multilingual():
    en = {f.kind for f in extract_vessel_conditions("the engine has stopped and the boat is taking water")}
    assert {"engine_failure", "taking_water"} <= en
    fr = {f.kind for f in extract_vessel_conditions("moteur en panne, embarque de l'eau, à la dérive")}
    assert {"engine_failure", "taking_water", "adrift"} <= fr
    it = {f.kind for f in extract_vessel_conditions("motore in avaria, gommone sovraccarico")}
    assert {"engine_failure", "overcrowded", "rubber_boat"} <= it


def test_needs_extraction():
    fields = {f.kind for f in extract_needs("they need immediate rescue, have no water and no fuel")}
    assert {"rescue", "food_water", "fuel"} <= fields
    fr = {f.kind for f in extract_needs("besoin de secours, urgence médicale, port sûr")}
    assert {"rescue", "medical", "disembarkation"} <= fr


def test_nothing_extracted_from_unrelated_text():
    assert extract_people("a lovely day at the harbour") == []
    assert extract_vessel_conditions("the ferry arrived on schedule") == []
    assert extract_needs("press conference at noon") == []
