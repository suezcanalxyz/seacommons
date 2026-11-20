# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical exclusion of historical short AIS gaps from investigative counts.

Old telemetric context events are retained in the archive for provenance but
must not inflate derived investigation/corroboration totals. All dashboards
must apply exactly the same predicate and optional UTC cutoff.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func

from core.db.models import IntelEventDB


def count_legacy_ais_gap_context(db, cutoff: datetime | None = None) -> int:
    clauses = [
        IntelEventDB.type == "ais_anomaly",
        IntelEventDB.source == "ais",
        IntelEventDB.id.like("aisanom:%"),
        IntelEventDB.meta["anomaly_type"].as_string() == "gap",
    ]
    if cutoff is not None:
        clauses.insert(0, IntelEventDB.received_at >= cutoff)
    return int(db.query(func.count(IntelEventDB.id)).filter(*clauses).scalar() or 0)
