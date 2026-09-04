# SPDX-License-Identifier: AGPL-3.0-or-later
"""Production Humanitarian truth-table audit (docs/updates.md P0.1).

**Goal:** every Humanitarian item visible in production must be traceable
from source observation through canonical incident, lifecycle, current
geometry, current Drift, timer and publication decision -- and every
visible anomaly must have a code/data-path explanation.

This is the first packet after `fixes.md` CLOSED (docs/updates.md
section 3/17). It is deliberately a *diagnostic* over what already
exists, not a rewrite: several of the 21 fields and 16 anomaly flags
docs/updates.md section "P0.1" names depend on canonical objects later
packets in the same dependency graph build (P0.2 SourceObservation/
provenance linkage, P0.3 canonical HumanitarianIncident id, P0.4 claim/
assessment model, P2.1/P2.2 correlation and circular-reporting lineage).
Where today's schema genuinely cannot answer a field/flag yet, this
module says so explicitly (``unavailable_fields`` / ``NOT_YET_COMPUTABLE``
below) rather than fabricating a value -- consistent with docs/updates.md
invariant #10 ("silence is not resolution") and #14 ("AI/automation may
not silently become canonical truth").

Reuses core.intel.lifecycle.distress_lifecycle (the one canonical
lifecycle authority both the VM feed and the edge publisher already
share) and core.intel.service_taxonomy.classify_service (the one
canonical service/lane authority) rather than re-deriving either --
docs/updates.md invariant #17: "one authoritative path per concept."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# Anomaly flags docs/updates.md P0.1 names that this module cannot yet
# compute with today's schema, and the packet (already scheduled in this
# same plan's dependency graph) that will make each computable. Never
# silently omitted from a row -- see TruthTableRow.unavailable_flags.
NOT_YET_COMPUTABLE: dict[str, str] = {
    "DRIFT_ORIGIN_OLDER_THAN_CURRENT_POSITION": "needs P0.2 position/observation history",
    "OUT_OF_ORDER_UPDATE": "needs P0.2 observation history",
    "LOCATION_CHANGED_WITHOUT_DRIFT_SUPERSESSION": "needs P0.2 position history + P0.7 Drift supersession",
    "UNLINKED_FOLLOWUP_REPORT": "needs P2.1 correlation decisions",
    "CONFLICTING_OUTCOME_WITHOUT_REVIEW": "needs P0.4 claim/assessment model",
    "CIRCULAR_CORROBORATION": "needs P2.2 circular-reporting lineage",
    "DUPLICATE_LIVE_INCIDENT": "needs P2.1 correlation decisions",
    "RESOLUTION_NOT_LINKED": "needs P0.4 claim/assessment model",
}


@dataclass(frozen=True)
class DriftSummary:
    drift_id: str
    status: str
    created_at: Optional[datetime]


@dataclass(frozen=True)
class TruthTableRow:
    """The per-case row docs/updates.md P0.1 asks for. Field names match
    that section's field list; ``candidate_incident_id`` is explicitly
    named "candidate" because no canonical HumanitarianIncident object
    exists yet (P0.3) -- this uses the IntelEvent id as its own
    placeholder identity, one event per row until P0.3 lands.
    """

    visible_feature_id: str
    candidate_incident_id: str
    source_ids: tuple[str, ...]
    reported_at: Optional[str]
    source_publication_time: Optional[str]
    retrieved_at: Optional[str]
    last_update_at: Optional[str]
    lifecycle: str
    current_drift_ids: tuple[str, ...]
    current_drift_status: Optional[str]
    marker_visible: bool
    drift_visible: bool
    publication_decision: str
    anomaly_flags: tuple[str, ...] = field(default_factory=tuple)
    unavailable_flags: tuple[str, ...] = field(default_factory=tuple)


def compute_anomaly_flags(
    *,
    lifecycle: str,
    drifts: list[DriftSummary],
    marker_visible: bool,
    drift_visible: bool,
    source_status: str,
    now: datetime,
    stale_drift_after_hours: float = 24.0,
) -> list[str]:
    """The subset of docs/updates.md P0.1's 16 flags this module can
    compute from today's schema. Never raises on malformed input beyond
    what Python's own type coercion already guards.
    """
    flags: list[str] = []
    completed = [d for d in drifts if d.status == "completed"]

    # P0.7 (Drift ownership/supersession) doesn't exist yet -- today's
    # schema has no "current" vs "superseded" distinction at all, so more
    # than one completed Drift row for the same case is already visible
    # ambiguity, not a false positive waiting on a later packet.
    if len(completed) > 1:
        flags.append("MULTIPLE_CURRENT_DRIFTS")

    if lifecycle in ("resolved", "archived") and drift_visible:
        flags.append("DRIFT_AFTER_RESOLUTION")

    if lifecycle == "active" and any(
        d.created_at is not None
        and (now - d.created_at).total_seconds() > stale_drift_after_hours * 3600
        for d in completed
    ):
        flags.append("STALE_DRIFT")

    if lifecycle == "active" and not marker_visible:
        flags.append("OPEN_CASE_DROPPED_FROM_LIVE")

    if lifecycle in ("resolved", "archived") and marker_visible:
        flags.append("RESOLVED_CASE_STILL_ACTIVE_LOOKING")

    # core.intel.lifecycle.distress_lifecycle() only ever returns
    # "archived" via its age-based silence branch (resolved/needs_review
    # both return earlier) -- so this flag fires by construction, not by
    # re-deriving the reason here (one authoritative path per concept).
    if lifecycle == "archived":
        flags.append("ARCHIVED_BY_SILENCE_ONLY")

    if source_status in ("degraded", "down", "unknown"):
        flags.append("SOURCE_STALE_OR_DOWN")

    return flags


def build_case_row(
    *,
    event_id: str,
    source: str,
    source_publication_time: Optional[str],
    retrieved_at: Optional[str],
    last_update_at: Optional[str],
    lifecycle: str,
    drifts: list[DriftSummary],
    marker_visible: bool,
    drift_visible: bool,
    publishable: bool,
    source_status: str,
    now: Optional[datetime] = None,
) -> TruthTableRow:
    now = now or datetime.now(timezone.utc)
    completed = [d for d in drifts if d.status == "completed"]
    flags = compute_anomaly_flags(
        lifecycle=lifecycle, drifts=drifts, marker_visible=marker_visible,
        drift_visible=drift_visible, source_status=source_status, now=now,
    )
    return TruthTableRow(
        visible_feature_id=f"intel:{event_id}",
        candidate_incident_id=event_id,
        source_ids=(source,),
        reported_at=source_publication_time,
        source_publication_time=source_publication_time,
        retrieved_at=retrieved_at,
        last_update_at=last_update_at,
        lifecycle=lifecycle,
        current_drift_ids=tuple(d.drift_id for d in completed),
        current_drift_status=(completed[0].status if len(completed) == 1 else None),
        marker_visible=marker_visible,
        drift_visible=drift_visible,
        publication_decision="publishable" if publishable else "withheld",
        anomaly_flags=tuple(flags),
        unavailable_flags=tuple(sorted(NOT_YET_COMPUTABLE)),
    )


def run_humanitarian_truth_table_audit(*, limit: int = 200) -> dict[str, Any]:
    """The real, live-wired entry point: queries IntelEventDB for
    Humanitarian-service events (core.intel.service_taxonomy.
    classify_service, the one canonical service authority), cross-
    references DriftResultDB, the actual public projections (core.live.
    feed.public_signal_collection/public_drift_collection), and
    core.intel.source_registry -- then builds one TruthTableRow per case.
    """
    from datetime import timedelta

    from core.db.models import DriftResultDB, IntelEventDB
    from core.db.session import session_scope
    from core.intel.lifecycle import distress_lifecycle, is_within_live_window
    from core.intel.service_taxonomy import classify_service
    from core.intel.source_registry import source_registry
    from core.intel.store import IntelEvent
    from core.live.feed import public_drift_collection, public_signal_collection

    now = datetime.now(timezone.utc)
    rows: list[TruthTableRow] = []

    signals = public_signal_collection(limit=500, days=30)
    visible_signal_ids = {
        str((f.get("properties") or {}).get("id") or "") for f in signals.get("features", [])
    }
    drift_collection = public_drift_collection(limit=200)
    visible_drift_event_ids = {
        str((f.get("properties") or {}).get("id") or "") for f in drift_collection.get("features", [])
    }

    with session_scope() as db:
        db_rows = (
            db.query(IntelEventDB)
            .order_by(IntelEventDB.created_at.desc())
            .limit(limit)
            .all()
        )
        for row in db_rows:
            event = IntelEvent(
                id=row.id, type=row.type, severity=row.severity, lat=row.lat, lon=row.lon,
                title=row.title, text=row.text or "", source=row.source,
                linked_mmsi=row.linked_mmsi or "", timestamp_utc=row.timestamp_utc,
                metadata=dict(row.meta or {}),
            )
            classification = classify_service(event)
            if classification.service != "humanitarian":
                continue
            if not is_within_live_window(event, now=now):
                continue

            same_source = [
                IntelEvent(
                    id=other.id, timestamp_utc=other.timestamp_utc,
                    text=other.text or "", title=other.title,
                    metadata=dict(other.meta or {}),
                )
                for other in db.query(IntelEventDB).filter(
                    IntelEventDB.source == row.source,
                    IntelEventDB.id != row.id,
                    IntelEventDB.created_at >= row.created_at - timedelta(days=14),
                ).limit(50).all()
            ]
            lifecycle = distress_lifecycle(event, now=now, same_source=same_source)

            drift_rows = (
                db.query(DriftResultDB)
                .filter(DriftResultDB.event_id.in_([row.id, f"intel:{row.id}"]))
                .all()
            )
            drifts = [
                DriftSummary(drift_id=d.drift_id, status=d.status or "unknown", created_at=d.created_at)
                for d in drift_rows
            ]

            source_status_entry = source_registry.get(row.source)
            source_status = source_status_entry.status if source_status_entry else "unknown"

            rows.append(build_case_row(
                event_id=row.id, source=row.source,
                source_publication_time=row.source_timestamp_utc or row.timestamp_utc,
                retrieved_at=row.received_at.isoformat() if row.received_at else None,
                last_update_at=row.timestamp_utc,
                lifecycle=lifecycle, drifts=drifts,
                marker_visible=f"intel:{row.id}" in visible_signal_ids or row.id in visible_signal_ids,
                drift_visible=f"intel:{row.id}" in visible_drift_event_ids or row.id in visible_drift_event_ids,
                publishable=classification.publishable, source_status=source_status,
                now=now,
            ))

    flagged = [r for r in rows if r.anomaly_flags]
    return {
        "generated_at": now.isoformat(),
        "case_count": len(rows),
        "flagged_case_count": len(flagged),
        "rows": rows,
        "not_yet_computable_flags": dict(NOT_YET_COMPUTABLE),
    }
