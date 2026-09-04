# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/updates.md P1.2: Coverage Matrix.

Exit gate (v0-bounded, per module docstring): every named region is
listed even with zero events (gaps are never omitted), single-family
dependency is flagged honestly, and the two dimensions today's schema
cannot answer (language coverage, expected-vs-actual cadence) are named
rather than silently dropped.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.db.models import IntelEventDB
from core.db.session import session_scope
from core.intel.coverage_matrix import NOT_YET_COMPUTABLE, build_coverage_matrix
from core.intel.mediterranean_regions import REGIONS


def _insert_event(*, lat, lon, source):
    now = datetime.now(timezone.utc)
    event_id = f"pytest-coverage-{uuid.uuid4()}"
    with session_scope() as db:
        db.add(IntelEventDB(
            id=event_id, timestamp_utc=now.isoformat(), type="distress", severity="high",
            lat=lat, lon=lon, title="t", text="t", source=source,
            created_at=now.replace(tzinfo=None),
        ))
    return event_id


def test_every_named_region_is_listed_even_with_zero_events():
    matrix = build_coverage_matrix(lookback_hours=1)
    region_names = {r.region for r in matrix.regions}
    assert region_names == set(REGIONS)


def test_an_event_in_lampedusa_counts_toward_central_mediterranean():
    _insert_event(lat=35.5, lon=12.6, source="GFW")
    matrix = build_coverage_matrix(lookback_hours=24)
    central = next(r for r in matrix.regions if r.region == "Central Mediterranean")
    assert central.event_count >= 1
    assert "GFW" in central.active_sources


def test_single_family_dependency_flagged_when_only_one_family_present():
    """docs/updates.md P1.2's own named risk: a region fed by exactly one
    source family is a coverage vulnerability, not a healthy region."""
    unique_source = f"pytest-single-source-{uuid.uuid4()}"
    _insert_event(lat=39.1, lon=26.3, source=unique_source)  # Aegean, uncatalogued family
    matrix = build_coverage_matrix(lookback_hours=24)
    aegean = next(r for r in matrix.regions if r.region == "Aegean")
    assert aegean.single_family_dependency is True
    assert aegean.source_family_breakdown == {"uncatalogued": aegean.event_count}


def test_unclassified_events_are_counted_not_dropped():
    _insert_event(lat=55.0, lon=-30.0, source="GFW")  # far North Atlantic, no region
    matrix = build_coverage_matrix(lookback_hours=24)
    assert matrix.unclassified_event_count >= 1


def test_not_yet_computable_dimensions_are_named():
    matrix = build_coverage_matrix(lookback_hours=1)
    assert matrix.not_yet_computable == NOT_YET_COMPUTABLE
    assert "local_language_coverage" in matrix.not_yet_computable


def test_coverage_matrix_route_exposes_the_real_matrix() -> None:
    from fastapi.testclient import TestClient

    from core.api.main import app

    response = TestClient(app).get("/api/v1/audit/coverage-matrix?lookback_hours=24")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["regions"]) == len(REGIONS)
    assert "not_yet_computable" in payload
