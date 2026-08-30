from __future__ import annotations

from core.live.vessel_episodes import (
    add_nearby_humanitarian_context,
    coalesce_security_vessel_episodes,
)


def _feature(event_id, timestamp, lon, lat, **properties):
    return {
        "type": "Feature",
        "id": event_id,
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "id": event_id,
            "timestamp_utc": timestamp,
            "severity": "medium",
            "source": "ais",
            **properties,
        },
    }


def test_one_vessel_becomes_one_episode_with_current_point_and_track() -> None:
    gap = _feature(
        "intel:gap", "2026-08-30T19:00:00+00:00", 29.14, 41.33,
        type="ais_anomaly", linked_mmsi="352001914", anomaly_type="gap",
        maritime_domain="sanctions", title="AIS gap — ST. OLGA",
    )
    incident = _feature(
        "intel:nuc", "2026-08-30T20:00:00+00:00", 29.16, 41.34,
        type="vessel_incident", linked_mmsi="352001914",
        ais_nav_status_kind="not_under_command", maritime_domain="grey_zone",
        title="Vessel unable to manoeuvre — ST. OLGA", drift_eligible=True,
    )

    result = coalesce_security_vessel_episodes(
        [gap, incident],
        track_history={
            "352001914": [
                {"lon": 29.12, "lat": 41.32, "ts": "2026-08-30T18:00:00+00:00", "nav_status": 2, "sog": 0.2},
                {"lon": 29.18, "lat": 41.35, "ts": "2026-08-30T21:00:00+00:00", "nav_status": 0, "sog": 7.2},
            ]
        },
    )

    assert len(result) == 1
    episode = result[0]
    assert episode["id"] == "vessel-episode:352001914"
    assert episode["geometry"]["coordinates"] == [29.18, 41.35]
    assert episode["properties"]["maritime_domain"] == "grey_zone"
    assert episode["properties"]["signal_count"] == 2
    assert len(episode["properties"]["observed_track"]) == 4
    assert episode["properties"]["drift_event_id"] == "intel:nuc"
    assert episode["properties"]["incident_lifecycle"] == "resolved"
    assert episode["properties"]["latest_nav_status"] == 0


def test_real_sanctions_match_enriches_episode_domain() -> None:
    result = coalesce_security_vessel_episodes([
        _feature(
            "intel:sdn", "2026-08-30T20:00:00+00:00", 20.0, 35.0,
            type="vessel_identity", linked_mmsi="273999000", anomaly_type="sdn_match",
            maritime_domain="sanctions", title="Sanctioned vessel",
        )
    ])
    assert result[0]["properties"]["sanctions_matched"] is True
    assert result[0]["properties"]["maritime_domain"] == "sanctions"


def test_humanitarian_proximity_is_context_not_a_merge() -> None:
    security = [_feature(
        "vessel-episode:1", "2026-08-30T20:00:00+00:00", 14.0, 35.0,
        type="ais_anomaly", title="AIS gap",
    )]
    humanitarian = [_feature(
        "intel:sos", "2026-08-30T19:30:00+00:00", 14.1, 35.0,
        type="distress", title="Distress alert",
    )]

    add_nearby_humanitarian_context(security, humanitarian)

    props = security[0]["properties"]
    assert props["nearby_humanitarian_count"] == 1
    assert props["nearby_humanitarian"][0]["title"] == "Distress alert"
