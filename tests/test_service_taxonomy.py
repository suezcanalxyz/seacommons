# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md Task 0.1 -- table-driven service/lane classification.

Every case is a positive decision; anything not explicitly recognised
must fail closed (service=None, publishable=False), never guess by
fallback/complement (docs/fixes.md Global Constraints).
"""
from __future__ import annotations

import pytest

from core.intel.service_taxonomy import (
    MARITIME_INTELLIGENCE_LANE,
    MARITIME_SAFETY_LANE,
    classify_service,
)

# (label, metadata, expected_service, expected_lane, expected_publishable)
CASES = [
    (
        "not_under_command is maritime safety, never intelligence",
        {"ais_nav_status_kind": "not_under_command", "maritime_domain": "grey_zone"},
        "maritime", MARITIME_SAFETY_LANE, True,
    ),
    (
        "aground is maritime safety",
        {"ais_nav_status_kind": "aground", "maritime_domain": "safety"},
        "maritime", MARITIME_SAFETY_LANE, True,
    ),
    (
        "restricted_manoeuvrability is maritime safety",
        {"ais_nav_status_kind": "restricted_manoeuvrability"},
        "maritime", MARITIME_SAFETY_LANE, True,
    ),
    (
        "disabled/adrift are the same safety observation under another name",
        {"ais_nav_status_kind": "adrift"},
        "maritime", MARITIME_SAFETY_LANE, True,
    ),
    (
        "an AIS-SART beacon distress call is humanitarian",
        {"is_distress": True, "case_type": "distress_sar"},
        "humanitarian", "distress", True,
    ),
    (
        "missing_persons case type maps to the missing lane",
        {"is_distress": True, "case_type": "missing_persons"},
        "humanitarian", "missing", True,
    ),
    (
        "pushback case type maps to the pushback lane",
        {"is_distress": True, "case_type": "pushback"},
        "humanitarian", "pushback", True,
    ),
    (
        "a distress-shaped event with an unrecognised case type still lands distress",
        {"is_distress": True, "case_type": "unspecified"},
        "humanitarian", "distress", True,
    ),
    (
        "a grey_zone rendezvous with no reviewed hypothesis is intelligence, not publishable",
        {"maritime_domain": "grey_zone"},
        "maritime", MARITIME_INTELLIGENCE_LANE, False,
    ),
    (
        "a sanctions-tagged event is intelligence, not publishable",
        {"maritime_domain": "sanctions"},
        "maritime", MARITIME_INTELLIGENCE_LANE, False,
    ),
    (
        "an environmental tag is maritime/environmental, not yet publishable",
        {"maritime_domain": "environmental"},
        "maritime", "environmental", False,
    ),
    (
        "an explicit service/lane already set by a producer is trusted as-is",
        {"service": "humanitarian", "lane": "resolution"},
        "humanitarian", "resolution", True,
    ),
    (
        "an explicit maritime/intelligence lane stays non-publishable",
        {"service": "maritime", "lane": MARITIME_INTELLIGENCE_LANE},
        "maritime", MARITIME_INTELLIGENCE_LANE, False,
    ),
]


@pytest.mark.parametrize("label,metadata,service,lane,publishable", CASES, ids=[c[0] for c in CASES])
def test_classify_service_table(label, metadata, service, lane, publishable):
    result = classify_service(metadata)
    assert result.service == service, label
    assert result.lane == lane, label
    assert result.publishable is publishable, label
    assert result.reason  # always machine-readable, never blank


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"maritime_domain": "sar"},  # bare "sar" with no is_distress flag: not yet handled
        {"maritime_domain": "unknown_future_domain"},
        {"service": "humanitarian", "lane": "not_a_real_lane"},
        {"service": "maritime", "lane": "not_a_real_lane"},
        {"is_distress": True, "ais_nav_status_kind": "aground"},  # safety wins even if is_distress got set upstream
    ],
    ids=["empty", "bare_sar_no_distress_flag", "unknown_domain", "bad_humanitarian_lane", "bad_maritime_lane", "distress_flag_does_not_override_safety"],
)
def test_classify_service_fails_closed(metadata):
    result = classify_service(metadata)
    if metadata.get("ais_nav_status_kind") == "aground":
        assert result.service == "maritime" and result.lane == MARITIME_SAFETY_LANE
        return
    assert result.service is None
    assert result.lane is None
    assert result.publishable is False
    assert result.reason


def test_classify_service_accepts_an_event_object_not_just_a_dict():
    from core.intel.store import IntelEvent

    event = IntelEvent(
        type="vessel_incident",
        metadata={"ais_nav_status_kind": "not_under_command"},
    )
    result = classify_service(event)
    assert result.service == "maritime"
    assert result.lane == MARITIME_SAFETY_LANE
