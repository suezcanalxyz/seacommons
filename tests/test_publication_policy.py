# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M9: canonical publication policy layer."""
from __future__ import annotations

import pytest

from core.intel.hypothesis import new_hypothesis, transition
from core.intel.publication_policy import (
    edge_humanitarian,
    project,
    project_analyst,
    project_public_humanitarian,
    project_public_maritime_assessed,
    project_public_safety,
)

_RECORD = {
    "id": "evt-1",
    "title": "Boat in distress off Lampedusa",
    "public_summary": "Report of a vessel in distress.",
    "category": "distress",
    "is_alarm_phone_red": True,
    "incident_lifecycle": "active",
    "lat": 35.5, "lon": 14.1,
    "location_precision": "approximate",
    "location_uncertainty_m": 1500.0,
    "people_reported": 40,
    "people_precision": "exact",
    "source_updates": ["update 1"],
    "resolution_state": "unresolved",
    "timestamp_utc": "2026-09-04T10:00:00Z",
    "linked_mmsi": "211879870",
    "imo": "9421556",
    "tracker_dossier": {"port_calls": ["Genoa"]},
    "raw_private_text": "caller said their name is X and phone number is Y",
    "internal_note": "analyst suspects duplicate report",
    "drift_job_id": None,
    "drift_geometry": None,
}


# ── analyst tiers ────────────────────────────────────────────────────────

def test_analyst_private_returns_everything_unfiltered():
    projected = project_analyst(_RECORD, shareable=False)
    assert projected == _RECORD


def test_analyst_shareable_strips_only_analyst_only_fields():
    projected = project_analyst(_RECORD, shareable=True)
    assert "raw_private_text" not in projected
    assert "internal_note" not in projected
    # MMSI/IMO/dossier ARE still visible to a shareable analyst -- only
    # the public tiers strip vessel identity.
    assert projected["linked_mmsi"] == "211879870"
    assert projected["imo"] == "9421556"


# ── public_humanitarian / edge_humanitarian ────────────────────────────

def test_public_humanitarian_strips_vessel_identity_fields():
    projected = project_public_humanitarian(_RECORD)
    assert "linked_mmsi" not in projected
    assert "imo" not in projected
    assert "tracker_dossier" not in projected


def test_public_humanitarian_excludes_raw_private_text():
    projected = project_public_humanitarian(_RECORD)
    assert "raw_private_text" not in projected
    assert "internal_note" not in projected


def test_public_humanitarian_retains_alarm_phone_red_category():
    projected = project_public_humanitarian(_RECORD)
    assert projected["category"] == "distress"
    assert projected["is_alarm_phone_red"] is True


def test_public_humanitarian_keeps_lifecycle_and_location_precision_explicit():
    projected = project_public_humanitarian(_RECORD)
    assert projected["incident_lifecycle"] == "active"
    assert projected["location_precision"] == "approximate"
    assert projected["location_uncertainty_m"] == 1500.0


def test_public_humanitarian_excludes_drift_without_a_persisted_job_id():
    projected = project_public_humanitarian(_RECORD)
    assert "drift_job_id" not in projected or projected.get("drift_job_id") is None
    assert "drift_geometry" not in projected


def test_public_humanitarian_includes_drift_only_from_a_persisted_backend_result():
    record = dict(_RECORD, drift_job_id="job-123", drift_geometry={"type": "LineString"})
    projected = project_public_humanitarian(record)
    assert projected["drift_job_id"] == "job-123"
    assert projected["drift_geometry"] == {"type": "LineString"}


def test_edge_humanitarian_is_the_literal_same_function_as_public_humanitarian():
    """docs/fixes.md M9: 'the edge must consume the same projection/policy
    semantics, not a copied rule set' -- proven structurally, not just
    by matching output."""
    assert edge_humanitarian is project_public_humanitarian


# ── public_safety ────────────────────────────────────────────────────

def test_public_safety_needs_no_hypothesis_to_publish():
    """docs/fixes.md M9: neutral Safety can publish without allegation."""
    record = dict(_RECORD, observation_text="AIS shows nav_status=not_under_command")
    projected = project_public_safety(record)
    assert projected["observation"] == "AIS shows nav_status=not_under_command"


def test_public_safety_strips_vessel_identity_and_private_fields():
    projected = project_public_safety(_RECORD)
    assert "linked_mmsi" not in projected
    assert "raw_private_text" not in projected


def test_public_safety_separates_observation_from_interpretation():
    record = dict(
        _RECORD, observation_text="speed dropped to 0.2kn",
        interpretation_text="consistent with a mechanical stop",
    )
    projected = project_public_safety(record)
    assert projected["observation"] == "speed dropped to 0.2kn"
    assert projected["interpretation"] == "consistent with a mechanical stop"


# ── public_maritime_assessed ────────────────────────────────────────────

def _published_hypothesis():
    from dataclasses import replace

    h = new_hypothesis("hyp-1", "dark_transit", ("subj:mmsi:111000111",))
    h = transition(h, "collecting", actor="system")
    h = transition(h, "review_ready", actor="system")
    h = replace(
        h, reason_codes=("isolated_gap",), evidence_links=("obs:a", "obs:b"),
        evidence_stage="corroborated",
    )
    return transition(h, "assessed", actor="system")


def test_maritime_assessed_returns_none_when_the_hypothesis_cannot_publish():
    """docs/fixes.md M9: Intelligence hypotheses only after publication
    gate."""
    unready = new_hypothesis("hyp-2", "dark_transit", ("subj:mmsi:111000111",))
    assert project_public_maritime_assessed(_RECORD, hypothesis=unready) is None


def test_maritime_assessed_publishes_once_the_hypothesis_clears_the_gate():
    ready = _published_hypothesis()
    projected = project_public_maritime_assessed(_RECORD, hypothesis=ready)
    assert projected is not None
    assert projected["hypothesis_type"] == "dark_transit"
    assert projected["reason_codes"] == ("isolated_gap",)


def test_maritime_assessed_with_no_hypothesis_at_all_still_projects():
    """A record with no hypothesis attached (nothing to gate) still
    projects -- the gate only blocks an attached-but-not-yet-publishable
    hypothesis."""
    projected = project_public_maritime_assessed(_RECORD, hypothesis=None)
    assert projected is not None


def test_maritime_assessed_drops_a_sanctions_entry_missing_its_source_list():
    """docs/fixes.md M9: official sanctions facts cite the authoritative
    list."""
    record = dict(_RECORD, sanctions=[
        {"source_list": "OFAC_SDN", "program": "IRAN"},
        {"program": "no list cited"},
    ])
    projected = project_public_maritime_assessed(record)
    assert len(projected["sanctions"]) == 1
    assert projected["sanctions"][0]["source_list"] == "OFAC_SDN"


# ── dispatcher ───────────────────────────────────────────────────────

def test_project_dispatches_to_every_named_target():
    for target in (
        "analyst_private", "analyst_shareable", "public_humanitarian",
        "public_safety", "public_maritime_assessed", "edge_humanitarian",
    ):
        result = project(_RECORD, target=target)
        assert result is not None


def test_project_raises_for_an_unknown_target():
    with pytest.raises(ValueError):
        project(_RECORD, target="not_a_real_target")
