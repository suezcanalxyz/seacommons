# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 1 of the maritime-domain compartment layer.

Covers only the additive pieces that ship without changing public-feed
behaviour: the ``maritime_domain`` tag + its inference, the public-domain
allow-list, and the projection carrying the tag through. The public-feed
widening (feed.py / edge gate) is a later phase and is tested there.
"""

from __future__ import annotations

import pytest

from core.domain.live_contracts import DEFAULT_PUBLIC_MARITIME_DOMAINS, MaritimeDomain
from core.intel.public_policy import is_public_domain, public_maritime_domains
from core.intel.store import IntelEvent


def _event(**kw) -> IntelEvent:
    kw.setdefault("severity", "medium")
    return IntelEvent(**kw)


# ── inference ────────────────────────────────────────────────────────────────

def test_legacy_event_without_metadata_resolves_to_sar() -> None:
    assert _event(type="distress").maritime_domain() == MaritimeDomain.SAR.value
    assert _event(type="twitter").maritime_domain() == MaritimeDomain.SAR.value
    assert _event(type="iom_incident").maritime_domain() == MaritimeDomain.SAR.value


def test_explicit_metadata_domain_wins() -> None:
    event = _event(type="twitter", metadata={"maritime_domain": "smuggling"})
    assert event.maritime_domain() == "smuggling"


@pytest.mark.parametrize(
    "anomaly_type,expected",
    [
        ("dark_zone_entry", MaritimeDomain.GREY_ZONE.value),
        ("zone_incursion", MaritimeDomain.GREY_ZONE.value),
        ("cable_proximity", MaritimeDomain.GREY_ZONE.value),
        ("sdn_match", MaritimeDomain.SANCTIONS.value),
        ("sanctioned_vessel", MaritimeDomain.SANCTIONS.value),
        ("ais_rendezvous", MaritimeDomain.GREY_ZONE.value),
        ("impossible_speed", MaritimeDomain.GREY_ZONE.value),
        ("gap", MaritimeDomain.GREY_ZONE.value),
        ("something_new", MaritimeDomain.GREY_ZONE.value),
    ],
)
def test_ais_anomaly_subtype_maps_to_compartment(anomaly_type, expected) -> None:
    event = _event(type="ais_anomaly", metadata={"anomaly_type": anomaly_type})
    assert event.maritime_domain() == expected


def test_type_level_domain_mapping() -> None:
    assert _event(type="piracy_incident").maritime_domain() == MaritimeDomain.PIRACY.value
    assert _event(type="gfw_event").maritime_domain() == MaritimeDomain.SANCTIONS.value
    assert _event(type="vessel_incident").maritime_domain() == MaritimeDomain.SAFETY.value


def test_geojson_feature_carries_the_tag() -> None:
    feature = _event(type="ais_anomaly", metadata={"anomaly_type": "sdn_match"}).to_geojson_feature()
    assert feature["properties"]["maritime_domain"] == MaritimeDomain.SANCTIONS.value


# ── public-domain allow-list ─────────────────────────────────────────────────

def test_default_public_domains_are_sar_and_piracy() -> None:
    assert public_maritime_domains() == DEFAULT_PUBLIC_MARITIME_DOMAINS
    assert is_public_domain("sar") is True
    assert is_public_domain("piracy") is True
    assert is_public_domain("sanctions") is False
    assert is_public_domain("grey_zone") is False
    assert is_public_domain(None) is True  # unset -> sar


def test_env_override_widens_but_always_keeps_sar(monkeypatch) -> None:
    monkeypatch.setenv("PUBLIC_MARITIME_DOMAINS", "grey_zone, environmental")
    domains = public_maritime_domains()
    assert domains == frozenset({"sar", "grey_zone", "environmental"})
    assert is_public_domain("sar") is True
    assert is_public_domain("grey_zone") is True
    assert is_public_domain("piracy") is False  # dropped when explicitly overridden
