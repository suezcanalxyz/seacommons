# SPDX-License-Identifier: AGPL-3.0-or-later
"""Warfare context feeds + maritime_strike fusion rule."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.intel import fusion
from core.intel.store import IntelEvent, intel_store
from core.mda.warfare import _extract_positions


@pytest.fixture(autouse=True)
def _clean():
    with intel_store._lock:
        intel_store._events.clear()
        intel_store._seen.clear()
        intel_store._subscribers.clear()
    yield


def test_navtext_position_parse():
    txt = "1. FIRING EXERCISES 15 JUL IN AREA BOUND BY 43-30.00N 037-00.00E, 43-50.00N 037-30.00E."
    pts = _extract_positions(txt)
    assert (43.5, 37.0) in pts
    assert len(pts) == 2


def _add(**kw):
    kw.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
    ev = IntelEvent(**kw)
    intel_store.add(ev)
    return ev


def _alerts():
    return [e for e in intel_store.events(limit=50) if e.type == fusion.ALERT_TYPE]


def test_maritime_strike_needs_two_corroborators():
    now = datetime.now(timezone.utc)
    _add(type="navwarning", severity="high", lat=44.9, lon=36.6,
         title="NAVWARN strike warning", source="NGA MSI",
         metadata={"anomaly_type": "strike_warning", "maritime_domain": "grey_zone"})
    _add(type="conflict_event", severity="high", lat=44.95, lon=36.55,
         title="ACLED: drone strike", source="ACLED",
         metadata={"anomaly_type": "conflict_event", "maritime_domain": "grey_zone"})
    incident = _add(type="vessel_incident", severity="high", lat=45.0, lon=36.6,
                    title="AIS: not under command — BULK CARRIER", source="AIS incidents",
                    metadata={"anomaly_type": "not_under_command", "maritime_domain": "safety",
                              "is_distress": True})
    fusion.evaluate(incident)
    alerts = _alerts()
    assert len(alerts) == 1
    assert alerts[0].metadata["alert_type"] == "maritime_strike"
    assert alerts[0].severity == "critical"


def test_lone_incident_does_not_strike():
    incident = _add(type="vessel_incident", severity="high", lat=45.0, lon=36.6,
                    title="AIS: not under command", source="AIS incidents",
                    metadata={"anomaly_type": "not_under_command", "maritime_domain": "safety",
                              "is_distress": True})
    fusion.evaluate(incident)
    strike = [a for a in _alerts() if a.metadata.get("alert_type") == "maritime_strike"]
    assert strike == []
