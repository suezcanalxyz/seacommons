from datetime import datetime, timedelta, timezone


def test_public_live_episode_inherits_detector_identity_assessment_and_trigger() -> None:
    from core.db.models import IntelEventDB, MaritimeEpisodeDB
    from core.db.session import engine, session_scope
    from core.live.feed import _published_open_episode_features

    MaritimeEpisodeDB.__table__.create(bind=engine(), checkfirst=True)
    IntelEventDB.__table__.create(bind=engine(), checkfirst=True)
    event_id = "spoof:372497000:test-teleport"
    episode_id = "episode:test:spoofing-enriched"
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with session_scope() as db:
        db.query(MaritimeEpisodeDB).filter_by(episode_id=episode_id).delete()
        db.query(IntelEventDB).filter_by(id=event_id).delete()
        db.add(IntelEventDB(
            id=event_id,
            timestamp_utc=now.replace(tzinfo=timezone.utc).isoformat(),
            type="ais_anomaly",
            severity="medium",
            lat=35.5,
            lon=14.1,
            title="AIS impossible-movement candidate — 372497000",
            source="mda",
            linked_mmsi="372497000",
            maritime_domain="grey_zone",
            meta={
                "anomaly_type": "position_jump",
                "detail": "625 km between two fixes",
                "movement_evidence": {
                    "from": {"lat": 42.3, "lon": 7.1},
                    "to": {"lat": 35.5, "lon": 14.1},
                    "distance_km": 625.4,
                    "time_delta_s": 660,
                    "implied_speed_kn": 1840.0,
                    "from_at": "2026-10-05T21:00:00Z",
                    "to_at": "2026-10-05T21:11:00Z",
                },
            },
        ))
        db.add(MaritimeEpisodeDB(
            episode_id=episode_id,
            episode_family="spoofing_episode",
            subject_ids=["subj:mmsi:372497000"],
            start_at=now - timedelta(minutes=10),
            end_at=now,
            geometry={"type": "Point", "coordinates": [14.1, 35.5]},
            observation_ids=[event_id],
            feature_ids=[],
            independence_groups=["ais_sensor_lineage"],
            verification_status="single_source_observed",
            behaviour_context={
                "analysis": {
                    "analysis_state": "evidence_candidate",
                    "publication_state": "published",
                    "resolution_state": "open",
                    "lineage_ids": ["ais_sensor_lineage"],
                },
                "case_opening": {
                    "reason_codes": [
                        "SUSTAINED_POSITION_RELOCATION",
                        "HIGH_CONFIDENCE_POSITION_INTEGRITY_ANOMALY",
                    ],
                },
            },
            alternative_explanations=["transponder_error"],
            evidence_fingerprint="test-spoofing-enriched",
            method_version="test",
            status="active",
        ))

    try:
        features = _published_open_episode_features(500)
        feature = next(item for item in features if item["id"] == episode_id)
        props = feature["properties"]
        assert props["linked_mmsi"] == "372497000"
        assert props["mmsi"] == "372497000"
        assert props["anomaly_type"] == "position_jump"
        assert props["movement_evidence"]["implied_speed_kn"] == 1840.0
        assert props["counter_indicators"] == ["transponder_error"]
        assert "625.4 km" in props["assessment"]["interpretation"]
        assert "1840 kn" in props["assessment"]["interpretation"]
        assert "625 km between two fixes" in props["assessment"]["observation"]
    finally:
        with session_scope() as db:
            db.query(MaritimeEpisodeDB).filter_by(episode_id=episode_id).delete()
            db.query(IntelEventDB).filter_by(id=event_id).delete()
