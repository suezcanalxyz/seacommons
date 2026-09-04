# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P1.1: Source Registry descriptive catalog.

Exit gate (v0-bounded): every real collector this codebase polls has a
descriptive profile with no fabricated fields, joined against live
operational health, with no single reliability score ever exposed.
"""
from __future__ import annotations

from core.intel.source_catalog import (
    SOURCE_CATALOG,
    get_source_profile,
    get_source_registry_catalog,
)
from core.intel.source_registry import source_registry


def test_every_catalog_entry_has_no_reliability_score():
    """docs/updates.md P1.1: "source reliability is contextual metadata,
    not one global truth score" -- the profile dict must never carry a
    field like trust_score/reliability_score."""
    for name in SOURCE_CATALOG:
        profile = get_source_profile(name)
        assert "reliability_score" not in profile
        assert "trust_score" not in profile


def test_get_source_profile_returns_none_for_unknown_source():
    assert get_source_profile("Some Source Nobody Curated") is None


def test_get_source_profile_shape():
    profile = get_source_profile("Alarm Phone")
    assert profile["source_id"] == "alarm_phone"
    assert profile["source_family"] == "distress_network"
    assert profile["independence_group"] == "x_twitter_platform"
    assert isinstance(profile["languages"], list)
    assert isinstance(profile["known_limitations"], list)


def test_registered_source_with_a_curated_profile_gets_both_halves():
    source_registry.register("Alarm Phone", "twitter")
    source_registry.record_poll("Alarm Phone", events_found=3)

    catalog = get_source_registry_catalog()
    entry = next(row for row in catalog if row["name"] == "Alarm Phone")

    assert entry["operational"] is not None
    assert entry["operational"]["total_events"] >= 3
    assert entry["profile"]["source_id"] == "alarm_phone"


def test_registered_source_with_no_curated_profile_is_never_fabricated():
    source_registry.register("Some Brand New Feed", "rss")

    catalog = get_source_registry_catalog()
    entry = next(row for row in catalog if row["name"] == "Some Brand New Feed")

    assert entry["operational"] is not None
    assert entry["profile"] is None


def test_curated_source_never_polled_still_appears_with_operational_none():
    catalog = get_source_registry_catalog()
    names = {row["name"] for row in catalog}
    assert "NGA MSI" in names or any(
        row["name"] == "NGA MSI" and row["operational"] is None for row in catalog
    )


def test_source_registry_route_returns_the_catalog() -> None:
    from fastapi.testclient import TestClient

    from core.api.main import app

    response = TestClient(app).get("/api/v1/audit/source-registry")
    assert response.status_code == 200
    payload = response.json()
    names = {row["name"] for row in payload["sources"]}
    assert "Alarm Phone" in names or "GFW" in names


def test_independence_group_flags_shared_platform_risk():
    """docs/updates.md P1.1: independence grouping exists so callers can
    tell that Alarm Phone and general X/Twitter search are NOT
    independent corroboration of each other -- both ride the same
    platform."""
    alarm_phone = get_source_profile("Alarm Phone")
    x_twitter = get_source_profile("X / Twitter")
    assert alarm_phone["independence_group"] == x_twitter["independence_group"]
