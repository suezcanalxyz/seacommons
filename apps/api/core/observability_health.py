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
live source, or expose an HTTP route. ``gather_data_health_summary()``
below (docs/fixes.md M14.5) is that caller: it gathers the three inputs
from core.intel.source_registry, core.intel.backfill_drift_maintenance.
run(apply=False), and the LIVE_EDGE_HEARTBEAT_OK gauge in
core.observability, and is what the real ``GET /health/data`` FastAPI
route (core.api.main) calls.

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


_REGISTRY_STATUS_TO_SNAPSHOT_STATUS = {
    "active": "healthy",
    "degraded": "degraded",
    "offline": "down",
    "pending": "unknown",
}


def gather_data_health_summary() -> DataHealthSummary:
    """The real, live-wired caller docs/fixes.md M14.5 asks for: gathers
    the three inputs build_data_health_summary() needs from wherever this
    codebase already tracks them (core.intel.source_registry,
    core.intel.backfill_drift_maintenance.run(apply=False), the
    LIVE_EDGE_HEARTBEAT_OK gauge) and returns the pure computation over
    them. This is the function GET /health/data calls.

    edge_heartbeat_ok reads core.observability's in-process gauge -- in a
    deployment where core.live_edge_publisher runs as its own process
    (its module docstring's documented run mode), that gauge is local to
    the publisher's process and this reads as never-updated (0.0) in the
    API process. Cross-process heartbeat sharing needs a durable store
    (a DB row, a shared metrics backend) this module doesn't have; this
    is one of the "remaining environment-only checks" docs/fixes.md
    M14.6 asks to document rather than silently paper over. Deployments
    that run the publisher embedded in the API process are unaffected.
    """
    from core.intel.backfill_drift_maintenance import run as run_drift_maintenance
    from core.intel.source_registry import source_registry
    from core.observability import (
        LIVE_EDGE_HEARTBEAT_OK,
        current_gauge_value,
        record_drift_maintenance_report,
    )

    source_snapshots = [
        SourceHealthSnapshot(
            name=str(source.get("name") or ""),
            status=_REGISTRY_STATUS_TO_SNAPSHOT_STATUS.get(
                str(source.get("status") or "pending"), "unknown",
            ),
            events_last_hour=int(source.get("events_last_hour") or 0),
        )
        for source in source_registry.get_all()
    ]

    drift_maintenance_report = run_drift_maintenance(apply=False)
    record_drift_maintenance_report(drift_maintenance_report)

    edge_heartbeat_ok = current_gauge_value(LIVE_EDGE_HEARTBEAT_OK, default=1.0) != 0.0

    return build_data_health_summary(
        source_snapshots=source_snapshots,
        drift_maintenance_report=drift_maintenance_report,
        edge_heartbeat_ok=edge_heartbeat_ok,
    )
