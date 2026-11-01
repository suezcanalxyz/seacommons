# SPDX-License-Identifier: AGPL-3.0-or-later
"""Missing-person reports are evidence until linked to an operational case."""

from __future__ import annotations

import pytest

from core.intel.store import IntelEvent
from core.live.projection import _public_intel_feature


def _missing_report(**overrides: object) -> IntelEvent:
    metadata: dict[str, object] = {
        "source_policy": "official_api",
        "maritime_domain": "sar",
        "humanitarian_case_type": "missing",
    }
    metadata.update(overrides)
    return IntelEvent(
        id="missing-only-social-report",
        type="twitter",
        severity="high",
        lat=35.4,
        lon=14.1,
        title="Missing people reported at sea",
        source="alarm_phone",
        metadata=metadata,
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"publication_status": "published"},
        {"verification_status": "multi_source_corroborated"},
        {"is_distress": False},
    ],
)
def test_missing_only_social_report_is_supporting_evidence_not_live_case(
    metadata: dict[str, object],
) -> None:
    # Publication, severity and review status cannot establish active distress.
    assert _public_intel_feature(_missing_report(**metadata)) is None


@pytest.mark.parametrize(
    "metadata",
    [
        {"is_distress": True},
        {"humanitarian_case_id": "humanitarian-case-123"},
    ],
)
def test_missing_report_with_explicit_operational_evidence_remains_eligible(
    metadata: dict[str, object],
) -> None:
    # Do not suppress a missing-vessel alert when the producer has asserted
    # current distress or linked the report to a canonical incident.
    feature = _public_intel_feature(_missing_report(**metadata))
    assert feature is not None
    assert feature["properties"]["humanitarian_case_type"] == "missing"


def test_explicit_distress_case_type_still_eligible() -> None:
    event = _missing_report(humanitarian_case_type="distress")
    assert _public_intel_feature(event) is not None
