# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M14.3: InvestigationHypothesis live wiring.

Exit gate, verbatim: "a single AIS observation must never create a
published allegation" and "official sanctions match alone remains an
official-list fact, not sanctions-evasion behaviour."
"""
from __future__ import annotations

import os
import time

os.environ["SEACOMMONS_TRACK_STORE_SYNC"] = "1"

from datetime import datetime, timedelta, timezone

import pytest

from core.intel.hypothesis import can_publish
from core.intel.hypothesis_engine import evaluate_episode
from core.intel.hypothesis_store import get_hypothesis
from core.intel.store import IntelEvent, intel_store


@pytest.fixture(autouse=True)
def _clean():
    from core.db.models import InvestigationHypothesisDB
    from core.db.session import engine, session_scope

    InvestigationHypothesisDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(InvestigationHypothesisDB).delete()
    with intel_store._lock:
        intel_store._events.clear()
        intel_store._seen.clear()
        intel_store._subscribers.clear()
    yield


def _add_event(event_id, *, mmsi="211879870", anomaly_type="gap", **metadata):
    # title carries event_id so IntelEvent.content_hash() (source:title:text)
    # never collides between two distinct synthetic events in one test --
    # add() would otherwise silently drop the second as a content duplicate.
    intel_store.add(IntelEvent(
        id=event_id, type="ais_anomaly", severity="medium",
        lat=35.5, lon=14.1, title=f"test:{event_id}", linked_mmsi=mmsi,
        source="mda", metadata={"anomaly_type": anomaly_type, **metadata},
    ), dedup_key=event_id)


def _episode(family, *, subject="subj:mmsi:211879870", signal_ids, episode_id="hyp-ep:test"):
    return {"properties": {
        "episode_id": episode_id, "episode_family": family,
        "subject_ids": [subject], "related_signal_ids": list(signal_ids),
    }}


def test_dark_transit_hypothesis_created_for_isolated_gap():
    _add_event("gap1", gap_reason={"hypothesis": "vessel_gap", "confidence": 0.6})
    _add_event("gap2", gap_reason={"hypothesis": "vessel_gap", "confidence": 0.55})

    hyp = evaluate_episode(_episode("gap_episode", signal_ids=["gap1", "gap2"]))

    assert hyp is not None
    assert hyp.hypothesis_type == "dark_transit"
    assert hyp.state == "collecting"
    assert set(hyp.evidence_links) == {"gap1", "gap2"}
    assert get_hypothesis(hyp.hypothesis_id) == hyp


def test_coverage_gap_does_not_create_a_dark_transit_hypothesis():
    """docs/fixes.md M14.1/M14.3: a common/port-wide outage's coverage_gap
    classification must not seed an intentional-dark hypothesis either."""
    _add_event("gap3", gap_reason={"hypothesis": "coverage_gap", "confidence": 0.05})

    hyp = evaluate_episode(_episode("gap_episode", signal_ids=["gap3"]))

    assert hyp is None


def test_exit_gate_a_single_observation_never_exceeds_candidate():
    _add_event("gap4", gap_reason={"hypothesis": "vessel_gap", "confidence": 0.6})

    hyp = evaluate_episode(_episode("gap_episode", signal_ids=["gap4"]))

    assert hyp is not None
    assert hyp.state == "candidate"
    ok, _reason = can_publish(hyp)
    assert ok is False


def test_exit_gate_sanctions_match_alone_never_creates_a_hypothesis():
    """docs/fixes.md M14.3: an identity_integrity_episode (sdn_match,
    mmsi_duplicate, ...) has no wired gate at all -- a bare official-list
    match can never become a hypothesis through this engine, by
    construction, regardless of how much evidence accumulates."""
    _add_event("sdn1", mmsi="273999000", anomaly_type="sdn_match", sanctions_matched=True)
    _add_event("sdn2", mmsi="273999000", anomaly_type="sdn_match", sanctions_matched=True)

    hyp = evaluate_episode(_episode(
        "identity_integrity_episode", subject="subj:mmsi:273999000",
        signal_ids=["sdn1", "sdn2"],
    ))

    assert hyp is None


def test_covert_rendezvous_requires_an_independent_irregularity():
    _add_event("rdv1", mmsi="111000001", anomaly_type="ais_rendezvous", dark=False)

    assert evaluate_episode(_episode(
        "rendezvous_episode", subject="subj:mmsi:111000001", signal_ids=["rdv1"],
    )) is None

    _add_event("rdv2", mmsi="111000001", anomaly_type="ais_rendezvous", dark=True)

    hyp = evaluate_episode(_episode(
        "rendezvous_episode", subject="subj:mmsi:111000001",
        signal_ids=["rdv1", "rdv2"], episode_id="hyp-ep:rdv",
    ))
    assert hyp is not None
    assert hyp.hypothesis_type == "covert_rendezvous"


def test_position_spoofing_wires_ais_integrity_classification():
    _add_event(
        "spoof1", mmsi="111000002", anomaly_type="position_jump",
        ais_integrity_classification={"label": "position_anomaly", "confidence": 0.6},
    )
    _add_event(
        "spoof2", mmsi="111000002", anomaly_type="position_jump",
        ais_integrity_classification={"label": "position_anomaly", "confidence": 0.6},
    )

    hyp = evaluate_episode(_episode(
        "spoofing_episode", subject="subj:mmsi:111000002",
        signal_ids=["spoof1", "spoof2"], episode_id="hyp-ep:spoof",
    ))
    assert hyp is not None
    assert hyp.hypothesis_type == "position_spoofing"


def test_infrastructure_pattern_requires_more_than_bare_proximity():
    _add_event(
        "infra1", mmsi="111000003", anomaly_type="loiter", loiter_minutes=90.0,
    )
    assert evaluate_episode(_episode(
        "infrastructure_proximity_episode", subject="subj:mmsi:111000003",
        signal_ids=["infra1"],
    )) is None

    _add_event(
        "infra2", mmsi="111000003", anomaly_type="loiter", loiter_minutes=95.0,
        sanctions_matched=True,
    )
    hyp = evaluate_episode(_episode(
        "infrastructure_proximity_episode", subject="subj:mmsi:111000003",
        signal_ids=["infra1", "infra2"], episode_id="hyp-ep:infra",
    ))
    assert hyp is not None
    assert hyp.hypothesis_type == "infrastructure_pattern"


def test_end_to_end_scan_gaps_then_scan_hypotheses_creates_a_persisted_hypothesis():
    """docs/fixes.md M14.3: real observations flowing through the actual
    live detector (core.mda.watch.scan_gaps(), M14.1) and episode builder
    (core.live.vessel_episodes, M14.2) create a persisted hypothesis --
    not just a synthetic evaluate_episode() call."""
    from core.mda.watch import MdaWatch
    from core.vessels.track_store import track_store

    with track_store._buf_lock:
        track_store._buffer.clear()
    track_store._last.clear()
    track_store._last_write_epoch.clear()
    from core.db.models import VesselTrackDB
    from core.db.session import session_scope
    with session_scope() as db:
        db.query(VesselTrackDB).delete()

    def _witness(mmsi, lat, lon, minutes_ago):
        track_store.on_position(
            mmsi, mmsi, lat, lon, sog=8.0, nav_status=0,
            received_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        )
        track_store._last_write_epoch[mmsi] = 0.0

    target = "211879870"
    track_store.on_position(target, target, 37.00, 18.00, sog=8.0, nav_status=0,
                             received_at=datetime.now(timezone.utc))
    track_store._last_write_epoch[target] = 0.0
    track_store._last[target].ts = time.time() - 5400  # 90 min silent -- isolated gap

    for k in range(3):
        w_mmsi = f"11100009{k}"
        _witness(w_mmsi, 37.01, 18.01, minutes_ago=100)
        _witness(w_mmsi, 37.01, 18.01, minutes_ago=40)

    w = MdaWatch()
    assert w.scan_gaps() == 1
    assert w.scan_hypotheses() == 1

    from core.intel.hypothesis_store import list_hypotheses
    hyps = list_hypotheses(hypothesis_type="dark_transit")
    assert len(hyps) == 1
    assert hyps[0].subject_ids == (f"subj:mmsi:{target}",)
    assert hyps[0].state == "candidate"  # one gap signal so far -- exit gate
