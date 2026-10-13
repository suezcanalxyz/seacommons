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
