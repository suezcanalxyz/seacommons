# SPDX-License-Identifier: AGPL-3.0-or-later
"""Coverage Matrix (docs/updates.md P1.2).

**Goal:** "operators can answer what SeaCommons is watching, what is
down, which areas/languages have weak coverage and when coverage
changed" (P1 exit criterion) -- per region, not just globally.

v0 scope, honestly bounded: this is a real read over IntelEventDB
(lat/lon + source + timestamp, the same fields the P0.1 truth table and
every collector already write), classified into the six
docs/updates.md-named regions via core.intel.mediterranean_regions, and
joined against core.intel.source_catalog for source-family grouping and
core.intel.source_registry for live health.

Two of the P1.2-requested dimensions genuinely cannot be answered
honestly with today's schema and are named rather than silently
dropped, matching P0.1's own NOT_YET_COMPUTABLE pattern:
  - local-language coverage: no event or source carries a language
    field anywhere in this codebase today.
  - expected-vs-actual cadence / backfill status: no per-source-per-
    region expected-cadence configuration exists yet (P1.3 is where
    coverage-change/versioning is scoped).
A region with zero events in the lookback window is still listed, with
event_count 0 -- "the platform must expose its observable universe and
gaps" (P1.2), not omit the gap.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

NOT_YET_COMPUTABLE: dict[str, str] = {
    "local_language_coverage": "no event or source carries a language field in this codebase yet",
    "expected_vs_actual_cadence": "no per-source-per-region expected-cadence configuration exists yet",
    "backfill_status": "needs P1.3 coverage-change integrity (inclusion rationale + backfill tracking)",
}


@dataclass(frozen=True)
class RegionCoverage:
    region: str
    event_count: int
    active_sources: list[str]
    healthy_sources: list[str]
    source_family_breakdown: dict[str, int]
    single_family_dependency: bool
    last_successful_fetch: Optional[str]


@dataclass(frozen=True)
class CoverageMatrix:
    generated_at: str
    lookback_hours: int
    regions: list[RegionCoverage]
    unclassified_event_count: int
    not_yet_computable: dict[str, str] = field(default_factory=lambda: dict(NOT_YET_COMPUTABLE))


def _source_family(source_name: str) -> str:
    from core.intel.source_catalog import get_source_profile

    profile = get_source_profile(source_name)
    return profile["source_family"] if profile is not None else "uncatalogued"


def build_coverage_matrix(lookback_hours: int = 168) -> CoverageMatrix:
    """Real DB-querying entry point. lookback_hours defaults to 7 days."""
    from core.db.models import IntelEventDB
    from core.db.session import session_scope
    from core.intel.mediterranean_regions import REGIONS, classify_region
    from core.intel.source_registry import source_registry

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)

    healthy_names = {
        s["name"] for s in source_registry.get_all() if s.get("status") == "healthy"
    }

    by_region: dict[str, list[Any]] = {name: [] for name in REGIONS}
    unclassified_event_count = 0

    with session_scope() as db:
        rows = db.query(IntelEventDB).filter(IntelEventDB.timestamp_utc >= cutoff.isoformat()).all()
        for row in rows:
            region = classify_region(row.lat, row.lon)
            if region is None:
                unclassified_event_count += 1
                continue
            by_region[region].append(row)

        regions: list[RegionCoverage] = []
        for name in REGIONS:
            region_rows = by_region[name]
            active_sources = sorted({r.source for r in region_rows})
            family_breakdown: dict[str, int] = {}
            for r in region_rows:
                fam = _source_family(r.source)
                family_breakdown[fam] = family_breakdown.get(fam, 0) + 1
            last_fetch = max((r.timestamp_utc for r in region_rows), default=None)
            regions.append(RegionCoverage(
                region=name,
                event_count=len(region_rows),
                active_sources=active_sources,
                healthy_sources=sorted(s for s in active_sources if s in healthy_names),
                source_family_breakdown=family_breakdown,
                single_family_dependency=len(family_breakdown) == 1,
                last_successful_fetch=last_fetch,
            ))

    return CoverageMatrix(
        generated_at=now.isoformat(),
        lookback_hours=lookback_hours,
        regions=regions,
        unclassified_event_count=unclassified_event_count,
    )
