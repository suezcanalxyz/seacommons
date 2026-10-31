# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed satellite observation identity replay regressions.

The same observation_id must never merge evidence belonging to another
incident, acquisition or provider product. No external provider calls.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from core.intel.satellite_observation import (
    SatelliteObservation,
    _same_observation_identity,
    list_incident_observations,
    persist_observations,
)


def _observation(**overrides):
    fields = dict(
        observation_id="sat-identity-test:scene",
        incident_id="sat-identity-test:original",
        provider="copernicus",
        mission="sentinel1",
        product_id="S1_TEST_SCENE",
        acquisition_time="2026-10-30T12:00:00+00:00",
        discovered_at=datetime.now(timezone.utc).isoformat(),
        footprint=None,
        bbox=[14.0, 35.0, 14.5, 35.5],
        sensor_type="sar",
        temporal_relation="nearest",
        temporal_delta_s=0.0,
        asset_ref="",
        source_url="",
        provenance={"case_targets": [{"role": "origin", "lat": 35.1, "lon": 14.1}]},
        evidence_status="associated",
        association_status="strong",
        episode_id="episode:original",
    )
    fields.update(overrides)
    return SatelliteObservation(**fields)


@pytest.fixture(autouse=True)
def _clean_identity_test_rows():
    from core.db.models import SatelliteObservationDB
    from core.db.session import session_scope

    def cleanup():
        with session_scope() as db:
            db.query(SatelliteObservationDB).filter(
                SatelliteObservationDB.observation_id.like("sat-identity-test:%")
            ).delete(synchronize_session=False)

    cleanup()
    yield
    cleanup()


@pytest.mark.parametrize("field,value", [
    ("incident_id", "sat-identity-test:another-case"),
    ("provider", "gfw"),
    ("mission", "sentinel2"),
    ("product_id", "DIFFERENT_SCENE"),
    ("acquisition_time", "2026-10-31T12:00:00+00:00"),
    ("sensor_type", "optical"),
])
def test_observation_identity_is_immutable(field, value):
    original = _observation()
    incoming = replace(original, **{field: value})
    assert _same_observation_identity(original, original)
    assert not _same_observation_identity(original, incoming)


def test_cross_incident_replay_cannot_transfer_satellite_episode():
    original = _observation()
    incoming = replace(
        original,
        incident_id="sat-identity-test:other",
        episode_id="episode:other",
        provenance={"case_targets": [{"role": "other-case", "lat": 36.0}]},
    )
    assert persist_observations([original]) == 1
    assert persist_observations([incoming]) == 0

    saved = list_incident_observations(original.incident_id)
    assert len(saved) == 1
    assert saved[0].episode_id == "episode:original"
    assert saved[0].association_status == "strong"
    assert saved[0].provenance == original.provenance
    assert list_incident_observations(incoming.incident_id) == []


def test_product_collision_cannot_overwrite_verified_evidence():
    original = _observation()
    incoming = replace(
        original,
        product_id="DIFFERENT_S1_SCENE",
        episode_id="episode:unrelated",
        provenance={"case_targets": [{"role": "unrelated", "lat": 36.0}]},
    )
    assert persist_observations([original]) == 1
    assert persist_observations([incoming]) == 0
    saved = list_incident_observations(original.incident_id)
    assert len(saved) == 1
    assert saved[0].product_id == original.product_id
    assert saved[0].episode_id == original.episode_id
    assert saved[0].provenance == original.provenance


def test_same_identity_still_merges_legitimate_case_target_replay():
    original = _observation(
        evidence_status="contextual", association_status=None, episode_id=None,
    )
    incoming = replace(
        original,
        provenance={"case_targets": [{"role": "drift", "lat": 35.2, "lon": 14.2}]},
    )
    assert persist_observations([original]) == 1
    assert persist_observations([incoming]) == 0
    saved = list_incident_observations(original.incident_id)
    assert len(saved) == 1
    assert {target["role"] for target in saved[0].provenance["case_targets"]} == {
        "origin", "drift",
    }
