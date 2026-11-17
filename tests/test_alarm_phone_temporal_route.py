from types import SimpleNamespace

from core.intel.macro_drift import temporal_route_evidence, spatial_prior_for_event


def test_departure_is_not_current_position():
    event = SimpleNamespace(source='alarm_phone', title='Boat departed from Sfax heading to Lampedusa', text='', timestamp_utc='2026-11-03T09:00:00Z', metadata={'is_distress': True, 'departure_at': '2026-11-03T01:00:00Z'})
    result = temporal_route_evidence(event)
    assert result['departure_time'] == '2026-11-03T01:00:00Z'
    assert result['estimated_current_position'] is None
    assert result['physical_drift_computed'] is False
    prior = spatial_prior_for_event(event)
    assert prior['temporal_route_evidence']['estimated_current_position'] is None
    assert prior['calibrated_probability'] is False


def test_notified_authority_is_not_departure():
    event = SimpleNamespace(source='alarm_phone', title='We contacted the coast guard in Malta', text='', timestamp_utc='', metadata={'is_distress': True})
    result = temporal_route_evidence(event)
    assert result['departure_claims'] == []
    assert result['estimated_current_position'] is None


def test_chronology_elapsed_hours_from_verified_timestamps():
    event = SimpleNamespace(source='alarm_phone', title='Boat departed from Sfax', text='', timestamp_utc='2026-11-03T12:00:00Z', metadata={'is_distress': True, 'departure_at': '2026-11-03T01:00:00Z', 'last_contact_at': '2026-11-03T07:30:00Z'})
    result = temporal_route_evidence(event)
    assert result['chronology_status'] == 'consistent'
    assert result['elapsed_departure_to_contact_hours'] == 6.5
    assert result['estimated_current_position'] is None


def test_inconsistent_chronology_does_not_produce_elapsed():
    event = SimpleNamespace(source='alarm_phone', title='Boat near Sfax', text='', timestamp_utc='2026-11-03T06:00:00Z', metadata={'is_distress': True, 'departure_at': '2026-11-03T07:00:00Z', 'last_contact_at': '2026-11-03T08:00:00Z'})
    result = temporal_route_evidence(event)
    assert result['chronology_status'] == 'insufficient_or_inconsistent'
    assert result['elapsed_departure_to_contact_hours'] is None


def test_naive_timestamp_rejected():
    event = SimpleNamespace(source='alarm_phone', title='Boat near Sfax', text='', timestamp_utc='2026-11-03T12:00:00Z', metadata={'is_distress': True, 'departure_at': '2026-11-03T01:00:00', 'last_contact_at': '2026-11-03T07:00:00Z'})
    assert temporal_route_evidence(event)['elapsed_departure_to_contact_hours'] is None


def test_location_clues_preserve_narrative_route_order():
    from core.intel.macro_drift import location_clues
    clues = location_clues("Boat departed from Sfax, last seen south of Kerkennah, heading to Lampedusa")
    route_places = [c["place"].casefold() for c in clues if c["role"] != "authority_notified"]
    assert route_places.index("sfax") < route_places.index("kerkennah") < route_places.index("lampedusa")


def test_followup_text_updates_route_prior_without_claiming_current_fix(monkeypatch):
    from core.intel import landmask
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: False)
    event = SimpleNamespace(
        source="alarm_phone",
        title="Boat departed from Sfax heading to Lampedusa",
        text="People request urgent rescue.",
        timestamp_utc="2026-11-03T08:00:00Z",
        metadata={
            "is_distress": True,
            "thread_reposts": [{
                "tweet_id": "follow-1",
                "posted_at": "2026-11-03T10:00:00Z",
                "note": "Update: last contact south of Kerkennah.",
            }],
        },
    )
    prior = spatial_prior_for_event(event)
    assert prior["geometry"] is not None
    assert prior["location_evidence"] == "route_followup_text_spatial_prior"
    assert prior["spatial_model"] == "sea_only_route_followup_prior"
    assert prior["temporal_route_evidence"]["follow_up_count"] == 1
    assert prior["temporal_route_evidence"]["latest_follow_up_at"] == "2026-11-03T10:00:00+00:00"
    assert prior["temporal_route_evidence"]["estimated_current_position"] is None
    assert prior["physical_drift_computed"] is False
    assert prior["calibrated_probability"] is False


def test_region_area_candidate_keeps_region_polygon_not_departure_centroid(monkeypatch):
    from core.intel import landmask
    monkeypatch.setattr(landmask, "is_on_land", lambda lat, lon: False)
    event = SimpleNamespace(
        source="alarm_phone",
        title="17 people in distress in the WesternMed",
        text="They left Mostaganem, Algeria on 27 October and there is no news.",
        lat=37.5, lon=1.5,
        timestamp_utc="2026-11-02T19:36:32+00:00",
        metadata={
            "is_distress": True,
            "coordinate_source": "region_area",
            "location_uncertainty_m": 180000,
            "coordinate_review_status": "not_applicable",
        },
    )
    prior = spatial_prior_for_event(event)
    assert prior["geometry"] is not None
    assert prior["location_evidence"] == "reported_region_radius_spatial_prior"
    assert prior["spatial_model"] == "sea_only_reported_region_prior"
    places = {p.casefold() for p in prior["mentioned_places"]}
    assert "mostaganem" in places
    assert prior["physical_drift_computed"] is False


def test_date_only_departure_becomes_time_window_not_exact_time():
    event = SimpleNamespace(
        source="alarm_phone",
        title="17 people in distress in the WesternMed",
        text="They left Mostaganem, Algeria on 27 October, since then there are no news.",
        lat=37.5, lon=1.5,
        timestamp_utc="2026-11-02T19:36:32+00:00",
        metadata={"is_distress": True, "coordinate_source": "region_area", "location_uncertainty_m": 180000},
    )
    result = temporal_route_evidence(event)
    assert result["departure_time"] == ""
    assert result["departure_time_window"]["start_utc"] == "2026-10-27T00:00:00+00:00"
    assert result["departure_time_window"]["end_utc"] == "2026-10-28T00:00:00+00:00"
    assert result["departure_time_window"]["precision"] == "date_only"
    assert result["elapsed_departure_to_report_hours_min"] > 130
    assert result["elapsed_departure_to_report_hours_max"] > result["elapsed_departure_to_report_hours_min"]
    assert result["estimated_current_position"] is None


def test_french_date_only_departure_is_parsed():
    event = SimpleNamespace(
        source="alarm_phone", title="",
        text="10 personnes parties de Boumerdès vers l'Espagne le 26 octobre.",
        timestamp_utc="2026-11-02T18:40:34+00:00", metadata={"is_distress": True},
    )
    result = temporal_route_evidence(event)
    assert result["departure_time_window"]["start_utc"] == "2026-10-26T00:00:00+00:00"
    assert result["departure_time_window"]["precision"] == "date_only"


def test_broad_destination_country_is_preserved_as_route_evidence_not_current_fix():
    event = SimpleNamespace(
        source="alarm_phone",
        title="10 people left Boumerdes heading towards Spain",
        text="No further position was reported.",
        lat=37.5, lon=1.5,
        timestamp_utc="2026-11-02T18:40:34+00:00",
        metadata={
            "is_distress": True,
            "coordinate_source": "region_area",
            "location_uncertainty_m": 180000,
        },
    )
    route = temporal_route_evidence(event)
    destinations = {c["place"].casefold() for c in route["destination_claims"]}
    assert "spain" in destinations
    assert route["estimated_current_position"] is None


def test_followup_cannot_overwrite_explicit_source_area(monkeypatch):
    from core.intel import landmask
    monkeypatch.setattr(landmask, 'is_on_land', lambda lat, lon: False)
    polygon = {'type': 'Polygon', 'coordinates': [[[12, 35], [13, 35], [13, 36], [12, 35]]]}
    event = SimpleNamespace(source='Alarm Phone', title='Boat departed from Sfax heading to Lampedusa', text='Urgent rescue', timestamp_utc='2026-11-03T08:00:00Z', metadata={'is_distress': True, 'area_geojson': polygon, 'area_confidence': 'source_reported', 'thread_reposts': [{'note': 'Last contact south of Kerkennah', 'posted_at': '2026-11-03T09:00:00Z'}]})
    prior = spatial_prior_for_event(event)
    assert prior['geometry'] == polygon
    assert prior['location_evidence'] == 'named_area_from_source_text'
    assert prior['temporal_route_evidence']['follow_up_count'] == 1
    assert prior['physical_drift_computed'] is False
