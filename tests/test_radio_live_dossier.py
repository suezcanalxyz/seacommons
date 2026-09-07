def test_public_receiver_summary_exposes_coarse_location_not_endpoint():
    from core.db.models import ReceiverCatalogDB
    from core.db.session import engine, session_scope
    from core.radio.catalog_store import public_catalog_summary

    ReceiverCatalogDB.__table__.create(bind=engine(), checkfirst=True)
    key = "test:radio-live-location"
    with session_scope() as db:
        db.query(ReceiverCatalogDB).filter_by(discovery_key=key).delete()
        db.add(ReceiverCatalogDB(
            discovery_key=key,
            receiver_id="rx-test",
            public_label="Test receiver",
            network_family="openwebrx",
            physical_lineage="private-lineage",
            endpoint="https://private.example/ws",
            directory_source="test",
            license_class="open_source",
            terms_status="allowed",
            activation_status="eligible",
            country="MT",
            lat=35.90123,
            lon=14.51234,
            capabilities=[{"min_hz": 100000, "max_hz": 30000000, "modes": ["usb"]}],
            reachable=True,
            score=99.0,
        ))
    summary = public_catalog_summary(limit=1)
    receiver = summary["receivers"][0]
    assert receiver["latitude"] == 35.901
    assert receiver["longitude"] == 14.512
    assert "endpoint" not in receiver
    assert "physical_lineage" not in receiver
    with session_scope() as db:
        db.query(ReceiverCatalogDB).filter_by(discovery_key=key).delete()


def test_vessel_dossier_includes_public_safe_radio_associations(monkeypatch):
    from core.api.routes import mda

    monkeypatch.setattr(mda, "_radio_associations_for_vessel", lambda mmsi: [{
        "observation_id": "obs:dsc-1",
        "match_status": "strong",
        "confidence": 0.95,
        "distance_km": 1.3,
        "ais_observed_at": "2026-09-07T15:00:00+00:00",
        "episode_eligible": True,
        "created_at": "2026-09-07T15:00:02+00:00",
    }])
    monkeypatch.setattr("core.vessels.track_store.track_store.track", lambda *args, **kwargs: [])
    monkeypatch.setattr("core.mda.identity.screen", lambda **kwargs: {})
    monkeypatch.setattr("core.vessels.registry.registry._cache", {}, raising=False)

    dossier = mda.build_vessel_dossier("123456789", hours=24, track_limit=240)
    assert dossier["radio_associations"][0]["match_status"] == "strong"
    assert dossier["radio_associations"][0]["confidence"] == 0.95
