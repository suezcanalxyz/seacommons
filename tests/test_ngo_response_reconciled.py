# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from core.intel.ngo_response import analyze_ngo_response
from core.vessels.ais_coverage import CoverageAssessment

_NOW = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)


def _incident():
    return SimpleNamespace(
        id="alarm:1", title="Distress", lat=35.0, lon=15.0,
        source="Alarm Phone", metadata={"incident_lifecycle": "active"},
    )


def _registry(*, sources=None, upstream=None, stations=None, course=225.0):
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [15.2, 35.2]},
        "properties": {
            "mmsi": "258479000", "ship_name": "Ocean Viking",
            "speed": 12.0, "course": course, "last_seen": _NOW.isoformat(),
            "sources": sources or ["aiscast", "aisstream"],
            "upstream_sources": upstream or ["aisstream", "volunteer"],
            "stations": stations or ["mt-01"],
        },
    }]}


def test_ngo_response_uses_reconciled_fix_and_reports_provider_context(monkeypatch):
    from core.vessels import ais_coverage

    monkeypatch.setattr(
        ais_coverage.coverage_state,
        "assess",
        lambda **_kwargs: CoverageAssessment(
            status="coverage_present",
            active_upstreams=frozenset({"aisstream", "volunteer"}),
            degraded_upstreams=frozenset(), confidence=0.9,
            reason_codes=("COVERAGE_PRESENT",), gap_eligible=True,
        ),
    )
    result = analyze_ngo_response(_incident(), now=_NOW, registry_geojson=_registry())
    vessel = result["ngo_vessels"][0]
    assert vessel["track_providers"] == ["aiscast", "aisstream"]
    assert vessel["upstream_sources"] == ["aisstream", "volunteer"]
    assert vessel["coverage_status"] == "coverage_present"
    assert vessel["mission_state"] in {"approaching", "on_scene", "possible_response"}


def test_provider_degraded_caps_approach_at_possible_response(monkeypatch):
    from core.vessels import ais_coverage

    monkeypatch.setattr(
        ais_coverage.coverage_state,
        "assess",
        lambda **_kwargs: CoverageAssessment(
            status="provider_degraded", active_upstreams=frozenset({"volunteer"}),
            degraded_upstreams=frozenset({"aisstream"}), confidence=0.25,
            reason_codes=("UPSTREAM_DEGRADED",), gap_eligible=False,
        ),
    )
    vessel = analyze_ngo_response(_incident(), now=_NOW, registry_geojson=_registry())["ngo_vessels"][0]
    assert vessel["mission_state"] == "possible_response"
    assert vessel["mission_state"] != "rescue_confirmed"
