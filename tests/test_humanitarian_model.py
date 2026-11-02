# SPDX-License-Identifier: AGPL-3.0-or-later
from core.intel.humanitarian import humanitarian_case_metadata


def test_alarm_phone_case_preserves_approximate_people_count() -> None:
    case = humanitarian_case_metadata(
        "🆘 from ~30 people in distress in the Aegean",
        incident_id="2093662092645548206",
        source="alarm_phone",
        distress=True,
    )
    assert case["humanitarian_case_id"] == "HUM-X-2093662092645548206"
    assert case["humanitarian_case_type"] == "distress"
    assert case["humanitarian_status"] == "ongoing"
    assert case["people_reported"] == 30
    assert case["people_precision"] == "approximate"
    assert case["verification_level"] == "direct_humanitarian_source"


def test_humanitarian_resolution_is_an_outcome_not_a_new_distress() -> None:
    case = humanitarian_case_metadata(
        "Rescued to Lampedusa. All 47 people arrived safely.",
        incident_id="reply-1",
        source="alarm_phone",
        distress=False,
        resolved=True,
    )
    assert case["humanitarian_case_type"] == "resolution"
    assert case["humanitarian_status"] == "resolved"
    assert case["people_reported"] == 47
    assert case["people_precision"] == "exact"


def test_alarm_phone_hope_for_safety_is_not_a_resolution() -> None:
    case = humanitarian_case_metadata(
        "🆘 9 people in distress in the #WesternMed. We were alerted by worried relatives. "
        "Since then, there are no news from them. We hope they will be found and brought to safety!",
        incident_id="westernmed-9",
        source="alarm_phone",
        distress=True,
    )
    assert case["humanitarian_case_type"] == "distress"
    assert case["humanitarian_status"] == "ongoing"


def test_named_evros_border_towns_are_land_humanitarian() -> None:
    for text in (
        "🆘 3 people at the police station in #NeaVyssa, #Greece.",
        "🆘 8 people including children near #NeoCheimonio, #Greece.",
    ):
        case = humanitarian_case_metadata(
            text,
            incident_id="land-case",
            source="alarm_phone",
            distress=True,
        )
        assert case["humanitarian_case_type"] == "land_humanitarian"


# Canonical backfills must share the same explicit-boolean contract as
# IntelEvent.tier(), Live, OpenDrift and satellite selection.
import pytest


@pytest.mark.parametrize(
    ("flag", "expected_case_type"),
    [
        ("false", "unknown_humanitarian"),
        ("FALSE", "unknown_humanitarian"),
        ("0", "unknown_humanitarian"),
        (False, "unknown_humanitarian"),
        ("unknown", "unknown_humanitarian"),
        ("true", "distress"),
        ("yes", "distress"),
        (True, "distress"),
    ],
)
def test_canonical_classification_does_not_promote_false_string_distress(
    flag, expected_case_type,
) -> None:
    from core.intel.humanitarian import canonical_classification
    from core.intel.store import IntelEvent

    event = IntelEvent(
        id="canonical-flag", type="twitter", source="Alarm Phone",
        title="Update about a group near Crete",
        text="Update about a group near Crete",
        timestamp_utc="2026-11-02T07:00:00+00:00",
        metadata={"is_distress": flag},
    )
    classification = canonical_classification(event)
    assert classification["humanitarian_case_type"] == expected_case_type


def test_canonical_classification_preserves_text_detection_without_flag() -> None:
    from core.intel.humanitarian import canonical_classification
    from core.intel.store import IntelEvent

    event = IntelEvent(
        id="canonical-text", type="twitter", source="Alarm Phone",
        title="SOS: 30 people in distress off Libya need rescue now",
        text="SOS: 30 people in distress off Libya need rescue now",
        timestamp_utc="2026-11-02T07:00:00+00:00",
        metadata={},
    )
    assert canonical_classification(event)["humanitarian_case_type"] == "distress"


@pytest.mark.parametrize(
    "source",
    ["Alarm Phone", "alarm_phone", "@alarm_phone", "alarmphone", "@AlarmPhone"],
)
def test_humanitarian_case_direct_source_aliases(source: str) -> None:
    case = humanitarian_case_metadata(
        "Update about a group near Crete",
        incident_id="source-alias", source=source, distress=False,
    )
    assert case["verification_level"] == "direct_humanitarian_source"


def test_humanitarian_case_unrelated_ngo_not_mistaken_for_alarm_phone() -> None:
    case = humanitarian_case_metadata(
        "Update about a group near Crete",
        incident_id="unrelated-source", source="Independent NGO", distress=False,
    )
    assert case["verification_level"] == "single_public_source"
