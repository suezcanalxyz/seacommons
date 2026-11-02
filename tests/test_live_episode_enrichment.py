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


def test_public_open_episode_corroboration_requires_canonical_independent_lineages() -> None:
    """DB-backed Live projection must not contradict itself or count AIS aliases twice."""
    from core.db.models import IntelEventDB, MaritimeEpisodeDB
    from core.db.session import engine, session_scope
    from core.live.feed import _published_open_episode_features

    MaritimeEpisodeDB.__table__.create(bind=engine(), checkfirst=True)
    IntelEventDB.__table__.create(bind=engine(), checkfirst=True)
    episode_id = "episode:test:open-lineage-contract"
    event_id = "spoof:372497000:test-open-lineage-contract"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cases = [
        (["ais_sensor_lineage", "ais"], "multi_source_corroborated", False),
        (["ais_sensor_lineage", "news:independent"], "single_source_multi_indicator", False),
        (["ais_sensor_lineage", "news:independent"], "multi_source_corroborated", True),
    ]
    try:
        for groups, verification, expected in cases:
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
                    title="Position integrity candidate",
                    source="mda",
                    linked_mmsi="372497000",
                    maritime_domain="grey_zone",
                    # Untrusted source metadata must not override the canonical
                    # persisted episode's independent-source verification.
                    meta={
                        "anomaly_type": "position_jump",
                        "contributing_independence_groups": ["ais", "gfw_sar"],
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
                    independence_groups=groups,
                    verification_status=verification,
                    behaviour_context={
                        "analysis": {
                            "analysis_state": "evidence_candidate",
                            "publication_state": "published",
                            "resolution_state": "open",
                        },
                        "case_opening": {"reason_codes": ["SUSTAINED_POSITION_RELOCATION"]},
                    },
                    alternative_explanations=[],
                    evidence_fingerprint="test-open-lineage-contract",
                    method_version="test",
                    status="active",
                ))
            features = _published_open_episode_features(500)
            props = next(item for item in features if item["id"] == episode_id)["properties"]
            assert props["corroborated"] is expected
            assert ("corroborated" in props["facets"]) is expected
            assert props["verification_status"] == (
                "multi_source_corroborated" if expected else (
                    "derived" if verification == "multi_source_corroborated"
                    else verification
                )
            )
            assert props["independent_source_count"] == (2 if expected else 0)
            assert "independence_groups" not in props

        # The episode is retained in storage, but a malformed WGS84 point
        # must never reach Live or the mobile map.
        for invalid_geometry in (
            {"type": "Point", "coordinates": [181, 35.5]},
            {"type": "Point", "coordinates": [14.1, -91]},
            {"type": "Point", "coordinates": ["14.1", 35.5]},
            {"type": "Point", "coordinates": [True, 35.5]},
            {"type": "Point", "coordinates": [14.1]},
        ):
            with session_scope() as db:
                episode = db.query(MaritimeEpisodeDB).filter_by(episode_id=episode_id).one()
                episode.geometry = invalid_geometry
            assert all(
                feature["id"] != episode_id
                for feature in _published_open_episode_features(500)
            )
            with session_scope() as db:
                persisted = db.query(MaritimeEpisodeDB).filter_by(episode_id=episode_id).one()
                assert persisted.geometry == invalid_geometry
    finally:
        with session_scope() as db:
            db.query(MaritimeEpisodeDB).filter_by(episode_id=episode_id).delete()
            db.query(IntelEventDB).filter_by(id=event_id).delete()
