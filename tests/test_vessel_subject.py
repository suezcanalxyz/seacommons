# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M5.1: stable vessel-subject identity layer."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.mda.vessel_subject import (
    resolve_subject,
    sanctions_fact_for,
    subject_id_for,
)

_VALID_IMO = "9074729"  # real check-digit-valid IMO used elsewhere in this codebase's tests


def _obs(*, mmsi="211879870", name="Sea Watch 5", flag="DEU", days_ago=0, imo=None, source="aisstream"):
    return {
        "mmsi": mmsi, "imo": imo, "name": name, "flag": flag, "source": source,
        "observed_at": datetime.now(timezone.utc) - timedelta(days=days_ago),
    }


def test_subject_id_prefers_imo_over_mmsi():
    assert subject_id_for(imo=_VALID_IMO, mmsi="211879870") == f"subj:imo:{_VALID_IMO}"


def test_subject_id_falls_back_to_mmsi_without_a_valid_imo():
    assert subject_id_for(imo=None, mmsi="211879870") == "subj:mmsi:211879870"


def test_subject_id_rejects_an_invalid_imo_check_digit():
    bad_imo = _VALID_IMO[:-1] + str((int(_VALID_IMO[-1]) + 1) % 10)
    assert subject_id_for(imo=bad_imo, mmsi="211879870") == "subj:mmsi:211879870"


def test_subject_id_is_none_with_no_usable_identifier():
    assert subject_id_for(imo=None, mmsi=None) is None
    assert subject_id_for(imo=None, mmsi="123") is None  # too short


def test_resolve_subject_is_none_for_an_empty_observation_list():
    assert resolve_subject([]) is None


def test_resolve_subject_builds_one_alias_per_observation():
    observations = [_obs(days_ago=10), _obs(days_ago=5), _obs(days_ago=0)]
    subject = resolve_subject(observations)
    assert subject is not None
    assert len(subject.aliases) == 3
    assert subject.primary_mmsi == "211879870"
    assert subject.conflicts == []


def test_a_name_change_within_days_is_an_explicit_conflict_not_an_overwrite():
    """docs/fixes.md M5.1: identity conflicts remain explicit evidence,
    not silent overwrites."""
    observations = [
        _obs(name="Sea Watch 5", days_ago=1),
        _obs(name="Ocean Runner", days_ago=0),  # same MMSI, new name <1 day later
    ]
    subject = resolve_subject(observations)
    assert len(subject.aliases) == 2  # both kept, neither silently dropped
    assert len(subject.conflicts) == 1
    conflict = subject.conflicts[0]
    assert conflict.field == "name"
    assert conflict.previous_value == "Sea Watch 5"
    assert conflict.new_value == "Ocean Runner"


def test_a_flag_change_within_days_is_also_a_conflict():
    observations = [
        _obs(flag="DEU", days_ago=1),
        _obs(flag="PAN", days_ago=0),
    ]
    subject = resolve_subject(observations)
    assert len(subject.conflicts) == 1
    assert subject.conflicts[0].field == "flag"


def test_a_name_change_far_apart_in_time_is_not_flagged_as_a_conflict():
    """A real re-naming/re-flagging (sale, paperwork) takes longer than a
    spoofed transition -- must not generate conflict noise."""
    observations = [
        _obs(name="Sea Watch 5", days_ago=400),
        _obs(name="Ocean Runner", days_ago=0),
    ]
    subject = resolve_subject(observations)
    assert subject.conflicts == []


def test_resolve_subject_uses_imo_when_any_observation_carries_one():
    observations = [
        _obs(days_ago=5, imo=None),
        _obs(days_ago=0, imo=_VALID_IMO),
    ]
    subject = resolve_subject(observations)
    assert subject.subject_id == f"subj:imo:{_VALID_IMO}"
    assert subject.primary_imo == _VALID_IMO


def test_sanctions_fact_is_a_fact_not_a_hypothesis():
    subject = resolve_subject([_obs()])
    hits = [{"list": "OFAC_SDN", "program": "IRAN"}]
    fact = sanctions_fact_for(subject, hits)
    assert fact["fact_type"] == "sanctions_list_match"
    assert fact["subject_id"] == subject.subject_id
    assert fact["matches"] == hits
    assert "hypothesis" not in fact
    assert "behaviour" not in fact
