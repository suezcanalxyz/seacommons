from __future__ import annotations

import pytest

from core.intel.store import IntelEvent


@pytest.mark.parametrize(
    ("source", "transport"),
    [
        ("Alarm Phone", "x"),
        ("alarm_phone", "email"),
        ("AlarmPhone", "webhook"),
    ],
)
def test_alarm_phone_transport_aliases_share_operational_origin_identity(source, transport):
    from core.intel.source_identity import resolve_source_identity

    policy = resolve_source_identity(source, {"transport": transport})
    assert policy.identity_id == "alarm_phone"
    assert policy.service == "humanitarian"
    assert policy.source_role == "operational_origin"
    assert policy.may_open_incident is True


@pytest.mark.parametrize("source", ["SOS Méditerranée", "SOS Mediterranee", "MSF_Sea", "MSF", "Sea Watch", "Sea-Watch"])
def test_operational_ngos_are_humanitarian_verification_sources(source):
    from core.intel.source_identity import resolve_source_identity

    policy = resolve_source_identity(source, {"transport": "rss"})
    assert policy.service == "humanitarian"
    assert policy.source_role == "verification"
    assert policy.may_open_incident is False


def test_iom_is_archive_reference_not_live_incident_authority():
    from core.intel.source_identity import resolve_source_identity

    policy = resolve_source_identity("IOM Missing Migrants", {"transport": "api"})
    assert policy.identity_id == "iom_missing_migrants"
    assert policy.service == "humanitarian"
    assert policy.source_role == "archive_reference"
    assert policy.may_open_incident is False


def test_unknown_and_ais_sources_never_gain_humanitarian_opening_authority():
    from core.intel.source_identity import may_open_humanitarian_incident, resolve_source_identity

    assert resolve_source_identity("AISStream").may_open_incident is False
    assert resolve_source_identity("Unknown NGO").may_open_incident is False

    event = IntelEvent(
        id="unknown-distress", type="distress", severity="high", source="Unknown NGO",
        metadata={"is_distress": True, "service": "humanitarian", "lane": "distress"},
    )
    assert may_open_humanitarian_incident(event) is False


def test_alarm_phone_identity_does_not_change_with_transport_metadata():
    from core.intel.source_identity import resolve_source_identity

    x = resolve_source_identity("Alarm Phone", {"transport": "x"})
    email = resolve_source_identity("Alarm Phone", {"transport": "email"})
    assert x.identity_id == email.identity_id == "alarm_phone"
    assert x.independence_group == email.independence_group
