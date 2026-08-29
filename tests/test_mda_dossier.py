# SPDX-License-Identifier: AGPL-3.0-or-later
"""Case evidence dossier."""
from __future__ import annotations

import os

os.environ["SEACOMMONS_TRACK_STORE_SYNC"] = "1"

from datetime import datetime, timezone

from core.intel import fusion
from core.intel.store import IntelEvent, intel_store


def _clean_store():
    with intel_store._lock:
        intel_store._events.clear()
        intel_store._seen.clear()
        intel_store._subscribers.clear()


def test_dossier_built_from_a_fusion_case():
    _clean_store()
    ev = IntelEvent(
        type="ais_rendezvous", severity="high", lat=36.5, lon=22.7,
        title="Tanker STS rendezvous — A / B", source="mda", linked_mmsi="209111000",
        metadata={"anomaly_type": "ais_rendezvous", "maritime_domain": "sanctions",
                  "tanker": True, "dark": True, "sts_zone": "Laconian Gulf",
                  "vessels": [{"mmsi": "209111000"}, {"mmsi": "636222000"}]},
    )
    intel_store.add(ev)
    fusion.evaluate(ev)

    from core.db.models import CaseDB
    from core.db.session import session_scope
    with session_scope() as db:
        case = db.query(CaseDB).first()
        assert case is not None
        case_id = case.case_id

    from core.cases.dossier import build_dossier
    d = build_dossier(case_id)
    assert d is not None
    assert d["incident"]["position"] == [22.7, 36.5]
    assert len(d["contributing_events"]) >= 1
    assert d["geographic_context"]["sts_zone"] == "Laconian Gulf / Kalamata anchorage"
    assert d["map"]["type"] == "FeatureCollection"
    assert any(f["properties"]["role"] == "incident" for f in d["map"]["features"])
