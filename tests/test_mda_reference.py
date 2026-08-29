# SPDX-License-Identifier: AGPL-3.0-or-later
"""MDA reference geometry index."""
from __future__ import annotations

from core.mda.reference import reference


def test_bundle_loads():
    gj = reference.to_geojson()
    kinds = {f["properties"]["kind"] for f in gj["features"]}
    assert {"cable", "pipeline", "platform", "sts_zone"} <= kinds
    assert len(gj["features"]) > 20


def test_nearest_infrastructure_to_a_platform():
    # Bouri platform ~ 32.8833, 13.2833
    hit = reference.nearest_infrastructure(32.90, 13.30, max_km=25)
    assert hit is not None
    assert hit.distance_km < 25
    assert hit.kind in ("platform", "pipeline", "cable")


def test_nearest_infrastructure_far_away_is_none():
    assert reference.nearest_infrastructure(15.0, 5.0, max_km=25) is None


def test_greenstream_pipeline_proximity():
    # a point right on the Mellitah->Gela corridor
    hits = reference.infrastructure_within(35.8, 14.1, km=15)
    assert any(h.kind == "pipeline" for h in hits)


def test_sts_zone_containment():
    assert reference.in_sts_zone(36.5, 22.7) == "Laconian Gulf / Kalamata anchorage"
    assert reference.in_sts_zone(40.0, 10.0) is None


def test_port_exclusion():
    assert reference.in_port_or_anchorage(37.94, 23.60) == "Piraeus"
    assert reference.in_port_or_anchorage(35.0, 18.0) is None


def test_chokepoint_lookup():
    cp = reference.chokepoint_of(41.15, 29.05)
    assert cp and cp["id"] == "bosphorus"
    assert reference.chokepoint_of(35.0, 18.0) is None
