import pytest

from core.intel.macro_drift import spatial_prior_for_event
from core.intel.store import IntelEvent


def test_region_only_alarm_phone_is_a_candidate_but_not_a_computed_drift():
    polygon = {"type": "Polygon", "coordinates": [[[12, 34], [13, 34], [12, 35], [12, 34]]]}
    e = IntelEvent(source="alarm_phone", title="Boat missing near Lampedusa", type="twitter", metadata={"is_distress": True, "coordinate_source": "region_area", "area_geojson": polygon, "area_confidence": "area_low_confidence"})
    prior = spatial_prior_for_event(e)
    assert prior["candidate"] is True
    assert prior["geometry"] == polygon
    assert prior["calibrated_probability"] is False
    assert prior["physical_drift_computed"] is False
    assert "lampedusa" in prior["mentioned_places"]


def test_no_place_is_still_candidate_without_fake_geometry():
    e = IntelEvent(source="@alarm_phone", type="twitter", title="Boat missing, no location supplied", metadata={"is_distress": True})
    prior = spatial_prior_for_event(e)
    assert prior["candidate"] is True
    assert prior["geometry"] is None


def test_other_source_does_not_masquerade_as_alarm_phone():
    e = IntelEvent(source="unknown", title="Boat near Lampedusa", metadata={"is_distress": True, "area_geojson": {"type": "Polygon", "coordinates": [[[12,34],[13,34],[12,35],[12,34]]]}})
    assert spatial_prior_for_event(e)["candidate"] is False


def test_text_clue_roles_distinguish_departure_from_notified_authority():
    from core.intel.macro_drift import location_clues
    clues = location_clues("Boat departed from Sfax. We informed the Malta coast guard.")
    assert any(c["place"] == "sfax" and c["role"] == "possible_departure" for c in clues)
    assert any(c["place"] == "malta" and c["role"] == "authority_notified" for c in clues)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (False, False),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        ("", False),
        (None, False),
        ({"value": True}, False),
        (True, True),
        ("true", True),
        ("YES", True),
        ("1", True),
        (1, True),
    ],
)
def test_alarm_phone_distress_metadata_requires_explicit_positive(value, expected):
    """A string 'false' must not publish a humanitarian macro search area."""
    polygon = {"type": "Polygon", "coordinates": [
        [[12, 34], [13, 34], [12, 35], [12, 34]],
    ]}
    event = IntelEvent(
        source="alarm_phone", type="twitter", title="Near Lampedusa",
        metadata={"is_distress": value, "area_geojson": polygon},
    )
    prior = spatial_prior_for_event(event)
    assert prior["candidate"] is expected
    assert prior["physical_drift_computed"] is False


@pytest.mark.parametrize("value", ["false", "0", "no", {"value": True}])
def test_drift_watchdog_excludes_false_or_ambiguous_distress(monkeypatch, value):
    """Read-only reconciliation must not count a serialized false distress."""
    from core.intel.drift_watchdog import reconcile
    from core.intel.store import intel_store

    event = IntelEvent(
        id="sat-assoc-test-watchdog-negative", source="alarm_phone",
        type="twitter", title="Routine update", metadata={"is_distress": value},
    )
    monkeypatch.setattr(intel_store, "persisted_events", lambda **kwargs: [event])
    report = reconcile(launch=False, limit=1)
    assert report["candidates"] == 0
    assert report["area_prior"] == 0
    assert report["launched"] == 0
