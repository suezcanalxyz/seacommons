# SPDX-License-Identifier: AGPL-3.0-or-later
"""IncidentWatch v0: bounded follow-up without mutating incident truth."""
from __future__ import annotations

from sqlalchemy import UniqueConstraint


def test_incident_watch_model_has_unique_incident_and_due_index():
    from core.db.models import IncidentWatchDB

    table = IncidentWatchDB.__table__
    assert table.name == "incident_watches"
    assert {column.name for column in table.columns} >= {
        "watch_id", "incident_id", "status", "priority", "lifecycle_snapshot",
        "profile_json", "profile_version", "next_run_at", "last_run_at",
        "last_success_at", "last_error_at", "last_error_class", "consecutive_errors",
        "run_count", "query_fingerprint", "lease_owner", "lease_until",
        "created_at", "updated_at", "expires_at",
    }
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("incident_id",) in unique_columns
    index_columns = {
        tuple(column.name for column in index.columns)
        for index in table.indexes
    }
    assert ("status", "next_run_at", "priority") in index_columns
