# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md Phase 2.1 -- one canonical live/humanitarian vocabulary.

No ingestion path may invent an alternative value.
"""
from __future__ import annotations

from core.domain.live_contracts import (
    CoordinateReviewStatus,
    HumanitarianCaseType,
    IncidentLifecycle,
    LocationStatus,
    MaritimeDomain,
    OperationalTier,
)
from core.intel.humanitarian import _case_type

_CANONICAL_CASE_TYPES = {c.value for c in HumanitarianCaseType}

_SAMPLES = [
    ("30 people in distress, taking on water", True, False, "distress"),
    ("Boat capsized off Libya, feared shipwreck", False, False, "distress"),
    ("We lost contact with the boat hours ago, where are they?", False, False, "missing"),
    ("The people were intercepted by the Libyan Coast Guard", False, False, "interception"),
    ("Another illegal pushback in the Aegean", False, False, "pushback"),
    ("Ocean Viking proceeding toward the case, rescue underway", False, False, "rescue_update"),
    ("All 47 people rescued and arrived safely in Lampedusa", False, True, "resolution"),
    ("The group was found near Evros and taken to a reception centre", False, False, "land_humanitarian"),
    ("We remember the victims of this shipwreck, one year on", False, False, "advocacy"),
    ("An update from the region", False, False, "unknown_humanitarian"),
]


def test_case_type_only_returns_canonical_values():
    for text, distress, resolved, _expected in _SAMPLES:
        result = _case_type(text, distress=distress, resolved=resolved)
        assert result in _CANONICAL_CASE_TYPES, (text, result)


def test_case_type_classification_samples():
    for text, distress, resolved, expected in _SAMPLES:
        assert _case_type(text, distress=distress, resolved=resolved) == expected, text


def test_operational_tier_is_the_intel_tier_vocabulary():
    assert {t.value for t in OperationalTier} == {"operational", "news", "signal"}


def test_enum_value_sets_are_stable():
    assert {d.value for d in MaritimeDomain} >= {"sar", "piracy", "sanctions", "grey_zone"}
    assert {s.value for s in IncidentLifecycle} == {
        "active", "resolved", "needs_review", "archived",
    }
    assert CoordinateReviewStatus.MACHINE_OCR_DISPUTED_NEEDS_REVIEW.value == (
        "machine_ocr_disputed_needs_review"
    )
    assert LocationStatus.WITHHELD_FROM_MARITIME_MAP.value == "withheld_from_maritime_map"


def test_ais_taxonomy_group_splits_the_flat_ais_bucket():
    """docs/prompt.md PHASE 6 / audit TX-1: vessel status, behavioural cue and
    signal anomaly are separate; 'spike' is never a group name."""
    from core.domain.live_contracts import AisTaxonomyGroup, ais_taxonomy_group

    assert ais_taxonomy_group("vessel_incident") == AisTaxonomyGroup.VESSEL_STATUS
    assert ais_taxonomy_group("ais_spike") == AisTaxonomyGroup.BEHAVIOURAL_CUE
    assert ais_taxonomy_group("ais_anomaly") == AisTaxonomyGroup.SIGNAL_ANOMALY
    assert ais_taxonomy_group("correlated_alert") == AisTaxonomyGroup.FUSED_ALERT
    assert ais_taxonomy_group("twitter") is None
    assert all("spike" not in g.value for g in AisTaxonomyGroup)


def test_sudden_stop_maps_to_a_visual_category():
    from core.domain.visual_category import classify_visual_category

    cat = classify_visual_category(event_type="ais_spike", metadata={"anomaly_type": "sudden_stop"})
    assert cat == "loitering"
