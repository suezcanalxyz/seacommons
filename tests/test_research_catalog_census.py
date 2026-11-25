"""Synthetic regressions for the read-only PLAY census."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "research_catalog_census", Path(__file__).resolve().parents[1] / "scripts/research_catalog_census.py"
)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def record(ident="private-id", **fields):
    return {"incident_id": ident, "domain": "maritime", "main_category": "maritime",
            "corroborated": False, "has_satellite": None, "title": "private-title",
            "geometry": {"coordinates": [1, 2]}, **fields}


def page(items, offset=0, total=None, next_offset=None):
    return {"incidents": items, "offset": offset,
            "total_count": len(items) if total is None else total, "next_offset": next_offset}


def test_complete_aggregate_redacted():
    data = [record(), record("other", main_category="humanitarian", corroborated=True)]
    result = mod.census(lambda _: page(data), pause=0)
    assert result["total"] == 2
    assert result["flags"]["domain_category_disagreement"] == 1
    assert result["flags"]["has_satellite:unknown"] == 2
    assert result["flags"]["corroborated:true"] == 1
    assert "private-id" not in str(result)
    assert "private-title" not in str(result)
    assert "coordinates" not in str(result)


def test_duplicate_rejected():
    with pytest.raises(ValueError, match="repeated"):
        mod.scan(lambda _: page([record(), record()]), pause=0)


def test_incomplete_rejected():
    with pytest.raises(ValueError, match="incomplete"):
        mod.scan(lambda _: page([record()], total=2), pause=0)


def test_paginated():
    pages = {0: page([record()], total=2, next_offset=1),
             1: page([record("other")], offset=1, total=2)}
    assert mod.census(pages.__getitem__, pause=0)["total"] == 2


def test_change_same_total_rejected():
    pages = iter([page([record()]), page([record("changed")])])
    with pytest.raises(ValueError, match="changed"):
        mod.census(lambda _: next(pages), pause=0)


def test_change_same_id_rejected():
    pages = iter([page([record()]), page([record(corroborated=True)])])
    with pytest.raises(ValueError, match="changed"):
        mod.census(lambda _: next(pages), pause=0)


def test_changing_total_rejected():
    pages = {0: page([record()], total=2, next_offset=1),
             1: page([record("other")], offset=1, total=3)}
    with pytest.raises(ValueError, match="changed"):
        mod.scan(pages.__getitem__, pause=0)


def test_geoai_quality_aggregate():
    data = [
        record("one", episode_family="gap_episode", geometry={"type": "Point", "coordinates": [12, 35]},
               reason_codes=["STRONG_RECEPTION_EXPECTATION", "LOCAL_AIS_COVERAGE_HEALTHY"],
               incident_status="open"),
        record("two", episode_family="gap_episode", geometry={"type": "Point", "coordinates": [0, 0]},
               reason_codes=["OPEN_GAP_COVERAGE_NOT_TRACK_CONTINUOUS", "TRACK_CORRIDOR_COVERAGE_PRESENT"],
               gap_duration_s=300, counter_indicators=["synthetic"], incident_status="resolved"),
        record("three", geometry=None),
    ]
    result = mod.census(lambda _: page(data), pause=0)
    assert result["gap_quality"]["total"] == 2
    assert result["gap_quality"]["strong_and_healthy_codes"] == 1
    assert result["gap_quality"]["both_continuous_and_noncontinuous_codes"] == 1
    assert result["gap_quality"]["duration_field_present"] == 1
    assert result["gap_quality"]["counter_indicators_present"] == 1
    assert result["geometry_quality"] == {"valid_range_point": 1, "zero_zero_review": 1, "missing": 1}
    assert result["gap_status"] == {"open": 1, "resolved": 1}
    assert "coordinates" not in str(result)


def test_geometry_quality_rejects_bad_values():
    for coords in ([181, 0], [0, -91]):
        assert mod.geometry_quality({"type": "Point", "coordinates": coords}) == "out_of_range"
    for coords in ([True, 1], [float("nan"), 0], [None, 0], [1]):
        assert mod.geometry_quality({"type": "Point", "coordinates": coords}) == "invalid_point"
    assert mod.geometry_quality({"type": "Polygon"}) == "other_geometry_unvalidated"


def test_census_rejects_changed_gap_quality():
    pages = iter([
        page([record(episode_family="gap_episode")]),
        page([record(episode_family="gap_episode", counter_indicators=["synthetic"])]),
    ])
    with pytest.raises(ValueError, match="changed"):
        mod.census(lambda _: next(pages), pause=0)
