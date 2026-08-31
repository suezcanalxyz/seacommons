# SPDX-License-Identifier: AGPL-3.0-or-later
"""Civil NGO vs state authority classification (ngo_registry.py).

docs/deep-research-report.md #28 and docs/deep-research-report (2).md's
"Civil SAR Registry" section both independently flag the same real bug:
NGO_VESSELS mixes civil NGO vessels with state coastguard/military ones,
and every coastguard entry was rendered on the public/operator NGO fleet
panel tagged exactly like a civil NGO asset (vessel_class="ngo").
"""
from __future__ import annotations

from core.intel.ngo_registry import (
    NGO_VESSELS,
    is_civil_ngo,
    is_ngo,
    ngo_vessel_geojson,
)

_COASTGUARD_MMSI = "247330700"  # Diciotti, Guardia Costiera ITA
_CIVIL_NGO_MMSI = "258479000"  # Ocean Viking, SOS Méditerranée


def test_every_registry_entry_has_an_operator_type():
    for mmsi, info in NGO_VESSELS.items():
        assert info.get("operator_type") in {"civil_ngo", "state_authority"}, mmsi


def test_coastguard_entries_are_state_authority_not_civil_ngo():
    for mmsi, info in NGO_VESSELS.items():
        if info.get("role") == "coastguard":
            assert info["operator_type"] == "state_authority", mmsi


def test_is_ngo_stays_broad_known_responder_membership():
    # Existing detector callers (rescue-cluster grouping, NGO search-pattern
    # rule, distress-response intercept scoring) rely on is_ngo() including
    # coastguard -- narrowing it would silently regress them.
    assert is_ngo(_COASTGUARD_MMSI) is True
    assert is_ngo(_CIVIL_NGO_MMSI) is True
    assert is_ngo("000000000") is False


def test_is_civil_ngo_excludes_coastguard():
    assert is_civil_ngo(_COASTGUARD_MMSI) is False
    assert is_civil_ngo(_CIVIL_NGO_MMSI) is True
    assert is_civil_ngo("000000000") is False


def test_ngo_vessel_geojson_never_tags_coastguard_as_ngo_vessel_class(monkeypatch):
    """Real production case both audits found: a Guardia Costiera/AFM vessel
    on the NGO fleet panel with vessel_class="ngo"."""
    from core.vessels import registry as vessel_registry_module

    fake_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [12.5, 37.0]},
                "properties": {"mmsi": _COASTGUARD_MMSI},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [12.6, 37.1]},
                "properties": {"mmsi": _CIVIL_NGO_MMSI},
            },
        ],
    }
    monkeypatch.setattr(
        vessel_registry_module.registry, "get_geojson", lambda: fake_geojson
    )

    result = ngo_vessel_geojson()
    by_mmsi = {f["properties"]["mmsi"]: f["properties"] for f in result["features"]}

    assert by_mmsi[_COASTGUARD_MMSI]["vessel_class"] == "coastguard"
    assert by_mmsi[_COASTGUARD_MMSI]["operator_type"] == "state_authority"
    assert by_mmsi[_CIVIL_NGO_MMSI]["vessel_class"] == "ngo"
    assert by_mmsi[_CIVIL_NGO_MMSI]["operator_type"] == "civil_ngo"
    assert result["meta"]["civil_ngo_registered"] + result["meta"]["state_authority_registered"] == (
        result["meta"]["total_registered"]
    )
