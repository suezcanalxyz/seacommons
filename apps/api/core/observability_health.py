# SPDX-License-Identifier: AGPL-3.0-or-later
"""Analyst data-health summary (docs/fixes.md M11).

**Goal: know when the pipeline is wrong before the UI becomes wrong.**
M11 wants "a lightweight internal /health/data or equivalent analyst
health endpoint summarizing freshness and stuck-work conditions without
leaking private content," with an exit gate naming three concrete
scenarios: "controlled source outage, stuck Drift job and edge failure
are all observable without inspecting the database manually."

``build_data_health_summary()`` is that summary's pure computation --
given already-gathered signals (a source-health snapshot, an M8 drift-
maintenance dry-run report, and the edge heartbeat flag), it returns a
structured dict with an explicit boolean per exit-gate scenario plus an
overall ``healthy`` flag. It does not itself query a database, call any
live source, or expose an HTTP route -- a caller (the actual
``/health/data`` FastAPI route, a later PR) gathers those three inputs
from wherever it already gets them (core.intel.source_registry,
core.intel.backfill_drift_maintenance.run(apply=False), the existing
LIVE_EDGE_HEARTBEAT_OK gauge in core.observability) and passes them in.

"No raw sensitive Humanitarian text in metrics/log labels" (M11): this
summary's shape carries only counts, booleans, and source *names* --
never event text, coordinates, or any field that could contain a
private report's content.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class SourceHealthSnapshot:
    name: str
    status: str  # "healthy" | "degraded" | "down" | "unknown"
    events_last_hour: int = 0
    last_success_unixtime: Optional[float] = None


@dataclass(frozen=True)
class DataHealthSummary:
    healthy: bool
    source_outage_detected: bool
    stuck_drift_detected: bool
    edge_failure_detected: bool
    degraded_sources: tuple[str, ...] = field(default_factory=tuple)
    stuck_drift_count: int = 0
    invalid_drift_count: int = 0
    details: dict[str, Any] = field(default_factory=dict)


def build_data_health_summary(
    *,
    source_snapshots: list[SourceHealthSnapshot],
    drift_maintenance_report: dict[str, int],
    edge_heartbeat_ok: bool,
) -> DataHealthSummary:
    """Pure aggregation -- never raises on malformed input beyond what
    Python's own type coercion already guards; a caller assembling these
    three inputs owns validating them.
    """
    degraded = tuple(
        s.name for s in source_snapshots if s.status in ("degraded", "down", "unknown")
    )
    source_outage_detected = bool(degraded)

    stuck_count = int(drift_maintenance_report.get("stuck", 0))
    invalid_count = int(drift_maintenance_report.get("invalid", 0))
    stuck_drift_detected = stuck_count > 0 or invalid_count > 0

    edge_failure_detected = not edge_heartbeat_ok

    healthy = not (source_outage_detected or stuck_drift_detected or edge_failure_detected)

    return DataHealthSummary(
        healthy=healthy,
        source_outage_detected=source_outage_detected,
        stuck_drift_detected=stuck_drift_detected,
        edge_failure_detected=edge_failure_detected,
        degraded_sources=degraded,
        stuck_drift_count=stuck_count,
        invalid_drift_count=invalid_count,
        details={
            "source_count": len(source_snapshots),
            "degraded_source_count": len(degraded),
        },
    )
