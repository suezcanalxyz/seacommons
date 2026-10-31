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
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from core.intel.store import IntelEvent

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

    # PostgreSQL TIMESTAMP WITHOUT TIME ZONE commonly returns naive UTC
    # datetimes for DriftResultDB.created_at. Comparing one with the aware
    # UTC audit clock raises TypeError and aborts the entire truth table.
    # Interpret naive persisted timestamps as UTC, never as host-local time.
    audit_now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    # An older completed drift is not evidence that the *latest* completed
    # estimate is stale. Multiple completed rows are separately flagged as
    # MULTIPLE_CURRENT_DRIFTS until supersession ownership is available.
    # Require every completed estimate to be old before marking STALE_DRIFT.
    if lifecycle == "active" and completed and all(
        d.created_at is not None
        and (
            audit_now - (
                d.created_at.replace(tzinfo=timezone.utc)
                if d.created_at.tzinfo is None
                else d.created_at.astimezone(timezone.utc)
            )
        ).total_seconds() > stale_drift_after_hours * 3600
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



def index_drift_summaries(
    case_ids: list[str], drift_rows: list[Any],
) -> dict[str, list[DriftSummary]]:
    """Associate one batch of persisted drift rows with audited event IDs.

    Historical DriftResultDB.event_id may use the raw ID or 'intel:' alias.
    A collision between aliases must not silently omit either audit case.
    """
    indexed: dict[str, list[DriftSummary]] = {case_id: [] for case_id in case_ids}
    alias_to_cases: dict[str, set[str]] = {}
    for case_id in case_ids:
        for alias in (case_id, f"intel:{case_id}"):
            alias_to_cases.setdefault(alias, set()).add(case_id)
    for drift in drift_rows:
        summary = DriftSummary(
            drift_id=drift.drift_id,
            status=drift.status or "unknown",
            created_at=drift.created_at,
        )
        for case_id in alias_to_cases.get(drift.event_id, ()):
            indexed[case_id].append(summary)
    return indexed


def _audit_followup_event(row: Any) -> "IntelEvent":
    """Keep the persisted source identity when passing follow-ups to lifecycle.

    has_resolution_signal deliberately rejects a follow-up whose source does
    not match the original case. Dropping IntelEventDB.source during the audit
    projection silently disables all cross-post resolution checks.
    """
    from core.intel.store import IntelEvent

    return IntelEvent(
        id=row.id,
        source=row.source,
        timestamp_utc=row.timestamp_utc,
        text=row.text or "",
        title=row.title or "",
        metadata=dict(row.meta or {}),
    )


def index_recent_same_source_followups(
    case_rows: list[Any], source_rows: list[Any], *,
    lookback_days: int = 14, max_per_case: int = 50,
) -> dict[str, list[Any]]:
    """Find the newest eligible same-source posts for each audited case.

    Callers need only the newest (max_per_case + 1) rows per source:
    removing the case itself still leaves up to max_per_case follow-ups.
    This bounds memory and avoids a PostgreSQL round trip for every case.
    Matching here is only a *candidate* for the shared lifecycle resolver,
    not evidence of the same maritime incident.
    """
    from datetime import timedelta

    by_source: dict[str, list[Any]] = {}
    for other in source_rows:
        by_source.setdefault(other.source, []).append(other)
    for source_rows_for_one in by_source.values():
        source_rows_for_one.sort(
            key=lambda other: (other.created_at, str(other.id)), reverse=True,
        )

    indexed: dict[str, list[Any]] = {}
    for row in case_rows:
        cutoff = row.created_at - timedelta(days=lookback_days)
        indexed[row.id] = [
            other for other in by_source.get(row.source, [])
            if other.id != row.id and other.created_at >= cutoff
        ][:max_per_case]
    return indexed


def source_followup_fetch_limit(case_count: int, *, max_per_case: int = 50) -> int:
    """Bound the per-source fetch while allowing for multiple audited cases.

    A flat 51-row limit per source can starve older cases when the same NGO
    publishes many updates. The extra row detects when coverage is truncated.
    """
    return min(5000, max(0, case_count) * (max_per_case + 1))


def summarize_visible_case_coverage(
    visible_feature_ids: set[str], audited_case_ids: list[str],
) -> dict[str, int]:
    """Count visible Humanitarian features not represented by audit rows.

    This is a coverage diagnostic, not an incident-resolution or data-loss
    verdict: Live can include in-memory features absent from IntelEventDB,
    and the audit deliberately bounds its scan. Never expose case IDs here.
    """
    def canonical_id(raw: str) -> str:
        value = str(raw or "").strip()
        return value.removeprefix("intel:")

    visible = {
        case_id for raw in visible_feature_ids
        if (case_id := canonical_id(raw))
    }
    audited = {
        case_id for raw in audited_case_ids
        if (case_id := canonical_id(raw))
    }
    return {
        "live_visible_feature_count": len(visible),
        "live_visible_features_with_audit_row_count": len(visible & audited),
        "live_visible_features_without_audit_row_count": len(visible - audited),
    }


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
    from core.intel.lifecycle import distress_lifecycle, is_within_live_retention_window
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

    # The first N database rows are not necessarily Humanitarian: AIS/news
    # traffic can displace every distress from a flat limit(N) audit scan.
    # Overscan at most 5,000 rows and disclose incomplete coverage rather
    # than silently reporting zero cases. This is a read-only diagnostic.
    scan_limit = min(5000, max(1, limit) * 10)
    with session_scope() as db:
        db_rows = (
            db.query(IntelEventDB)
            .order_by(IntelEventDB.created_at.desc())
            .limit(scan_limit + 1)
            .all()
        )
        audit_scan_truncated = len(db_rows) > scan_limit
        candidates = []
        for row in db_rows[:scan_limit]:
            event = IntelEvent(
                id=row.id, type=row.type, severity=row.severity, lat=row.lat, lon=row.lon,
                title=row.title, text=row.text or "", source=row.source,
                linked_mmsi=row.linked_mmsi or "", timestamp_utc=row.timestamp_utc,
                metadata=dict(row.meta or {}),
            )
            classification = classify_service(event)
            if classification.service != "humanitarian":
                continue
            # Audit all recent cases, including resolved ones: a resolved
            # incident with a lingering drift is precisely an anomaly that
            # the truth table must be able to detect. The stricter active-only
            # window would silently discard it before DRIFT_AFTER_RESOLUTION.
            if not is_within_live_retention_window(event, now=now):
                continue
            candidates.append((row, event, classification))

        if len(candidates) > max(1, limit):
            audit_scan_truncated = True
            candidates = candidates[:max(1, limit)]

        # One bounded query replaces a separate DriftResultDB query per
        # humanitarian case, reducing DB round trips under Oracle CPU pressure.
        case_ids = [row.id for row, _, _ in candidates]
        aliases = list(dict.fromkeys(
            alias for case_id in case_ids for alias in (case_id, f"intel:{case_id}")
        ))
        drift_rows = (
            db.query(DriftResultDB)
            .filter(DriftResultDB.event_id.in_(aliases))
            .all()
        ) if aliases else []
        drifts_by_case = index_drift_summaries(case_ids, drift_rows)

        # Group by source, not case, preserving a bounded number of rows
        # for *each* audited case. The former fixed 51-row source cap could
        # silently omit follow-ups for older cases when several cases shared
        # a high-volume NGO source. A sentinel row reports incomplete scans.
        # This remains one query per source, not one per case.
        source_groups: dict[str, list[Any]] = {}
        for row, _, _ in candidates:
            source_groups.setdefault(row.source, []).append(row)
        recent_source_rows: list[Any] = []
        followup_incomplete_sources = 0
        max_followups_per_case = 50
        for source, group in source_groups.items():
            oldest_cutoff = min(row.created_at for row in group) - timedelta(days=14)
            fetch_limit = source_followup_fetch_limit(
                len(group), max_per_case=max_followups_per_case,
            )
            source_batch = (
                db.query(IntelEventDB)
                .filter(
                    IntelEventDB.source == source,
                    IntelEventDB.created_at >= oldest_cutoff,
                )
                .order_by(IntelEventDB.created_at.desc(), IntelEventDB.id.desc())
                .limit(fetch_limit + 1)
                .all()
            )
            if len(source_batch) > fetch_limit:
                followup_incomplete_sources += 1
            recent_source_rows.extend(source_batch[:fetch_limit])
        # The lifecycle resolver considers at most 50 same-source posts per
        # case. Probe one additional candidate before slicing: otherwise a
        # busy NGO can hide an older decisive rescue update without any
        # case-level warning. This reports uncertainty, not corroboration.
        probed_followups_by_case = index_recent_same_source_followups(
            [row for row, _, _ in candidates], recent_source_rows,
            max_per_case=max_followups_per_case + 1,
        )
        followup_candidate_window_truncated_case_count = sum(
            len(posts) > max_followups_per_case
            for posts in probed_followups_by_case.values()
        )
        followups_by_case = {
            case_id: posts[:max_followups_per_case]
            for case_id, posts in probed_followups_by_case.items()
        }

        for row, event, classification in candidates:
            same_source = [
                _audit_followup_event(other)
                for other in followups_by_case[row.id]
            ]
            lifecycle = distress_lifecycle(event, now=now, same_source=same_source)

            drifts = drifts_by_case[row.id]

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
    live_coverage = summarize_visible_case_coverage(
        visible_signal_ids, [row.candidate_incident_id for row in rows],
    )
    return {
        "generated_at": now.isoformat(),
        "case_count": len(rows),
        "flagged_case_count": len(flagged),
        # Counts are aggregate-only; a gap does not prove a lost incident.
        **live_coverage,
        "audit_scan_truncated": audit_scan_truncated,
        "audited_source_rows_count": min(len(db_rows), scan_limit),
        # Nonzero means the bounded source scan cannot certify that every
        # same-source follow-up was considered; do not imply complete audit.
        "followup_coverage_incomplete_source_count": followup_incomplete_sources,
        # Even a fully fetched source may have >50 eligible posts for one
        # case; the resolver cannot certify outcomes beyond that window.
        "followup_candidate_window_truncated_case_count": (
            followup_candidate_window_truncated_case_count
        ),
        "rows": rows,
        "not_yet_computable_flags": dict(NOT_YET_COMPUTABLE),
    }
