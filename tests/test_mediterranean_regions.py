# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P1.2: region classification used by the Coverage
Matrix. One authoritative bounding-box classifier, no fabricated
region for out-of-range coordinates.
"""
from __future__ import annotations

from core.intel.mediterranean_regions import REGIONS, classify_region


def test_lampedusa_is_central_mediterranean():
    assert classify_region(35.5, 12.6) == "Central Mediterranean"


def test_alboran_sea_is_western_mediterranean():
    assert classify_region(35.9, -3.5) == "Western Mediterranean"


def test_lesbos_is_aegean():
    assert classify_region(39.1, 26.3) == "Aegean"


def test_adriatic_off_bari_is_adriatic_ionian():
    assert classify_region(41.5, 17.5) == "Adriatic / Ionian"


def test_canary_islands_is_atlantic_canary_route():
    assert classify_region(28.1, -15.4) == "Atlantic / Canary route"


def test_cyprus_area_is_eastern_mediterranean():
    assert classify_region(34.7, 33.0) == "Eastern Mediterranean"


def test_north_atlantic_far_from_any_route_is_unclassified():
    assert classify_region(55.0, -30.0) is None


def test_missing_coordinates_are_unclassified_not_fabricated():
    assert classify_region(None, None) is None
    assert classify_region(35.0, None) is None


def test_regions_tuple_matches_docs_updates_p1_2():
    assert set(REGIONS) == {
        "Western Mediterranean",
        "Central Mediterranean",
        "Eastern Mediterranean",
        "Aegean",
        "Adriatic / Ionian",
        "Atlantic / Canary route",
    }
