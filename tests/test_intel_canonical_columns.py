# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md Phase 2.3 -- classification is dual-written to explicit columns.

A SQL query must be able to answer operational questions without decoding the
free-form ``meta`` JSON.
"""
from __future__ import annotations

import time

from sqlalchemy import select

from core.db.models import IntelEventDB
from core.db.session import session_scope
from core.intel.store import IntelEvent, IntelStore


def _wait_for_row(event_id: str, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with session_scope() as db:
            row = db.execute(
                select(IntelEventDB).where(IntelEventDB.id == event_id)
            ).scalar_one_or_none()
            if row is not None:
                db.expunge(row)
                return row
        time.sleep(0.02)
    return None


def test_canonical_columns_helper_derives_from_event():
    event = IntelEvent(
        id="canon-1",
        type="twitter",
        severity="high",
        title="Boat in distress",
        source="Alarm Phone",
        metadata={
            "is_distress": True,
            "humanitarian_case_type": "distress",
            "incident_lifecycle": "active",
            "coordinate_review_status": "machine_ocr_consensus_verified",
            "location_uncertainty_m": 400,
        },
    )
    cols = event.canonical_columns()
    assert cols["maritime_domain"] == "sar"
    assert cols["operational_tier"] == "operational"
    assert cols["humanitarian_case_type"] == "distress"
    assert cols["incident_lifecycle"] == "active"
    assert cols["coordinate_review_status"] == "machine_ocr_consensus_verified"
    assert cols["location_uncertainty_m"] == 400.0
    assert cols["schema_version"] == 1


def test_insert_dual_writes_classification_columns():
    store = IntelStore()
    event = IntelEvent(
        id="canon-persist-1",
        type="twitter",
        severity="high",
        lat=34.2,
        lon=12.0,
        title="Distress south of Lampedusa",
        source="Alarm Phone",
        metadata={
            "is_distress": True,
            "humanitarian_case_type": "distress",
            "incident_lifecycle": "active",
        },
    )
    assert store.add(event) is True
    row = _wait_for_row("canon-persist-1")
    assert row is not None
    assert row.maritime_domain == "sar"
    assert row.operational_tier == "operational"
    assert row.humanitarian_case_type == "distress"
    assert row.incident_lifecycle == "active"
    # meta still carries everything -- provenance envelope is unchanged.
    assert row.meta["humanitarian_case_type"] == "distress"


def test_can_query_active_humanitarian_distress_without_decoding_json():
    store = IntelStore()
    for idx, (case_type, lifecycle) in enumerate(
        [("distress", "active"), ("resolution", "resolved"), ("advocacy", "active")]
    ):
        store.add(IntelEvent(
            id=f"canon-q-{idx}",
            type="twitter",
            severity="high",
            title=f"row {idx}",
            source="Alarm Phone",
            metadata={
                "is_distress": case_type == "distress",
                "humanitarian_case_type": case_type,
                "incident_lifecycle": lifecycle,
            },
        ))
    _wait_for_row("canon-q-2")
    with session_scope() as db:
        rows = db.execute(
            select(IntelEventDB.id).where(
                IntelEventDB.humanitarian_case_type == "distress",
                IntelEventDB.incident_lifecycle == "active",
            )
        ).scalars().all()
    assert "canon-q-0" in rows
    assert "canon-q-1" not in rows and "canon-q-2" not in rows
