from datetime import datetime, timezone


def test_radio_burst_roundtrip_is_idempotent():
    from core.db.models import RadioBurstDB
    from core.db.session import engine, session_scope
    from core.radio.burst import RadioBurst
    from core.radio.burst_store import persist_radio_burst

    RadioBurstDB.__table__.create(bind=engine(), checkfirst=True)
    burst = RadioBurst(
        "rfb:test", "rx-lineage", 2_187_500,
        datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 7, 12, 0, 2, tzinfo=timezone.utc),
        3, -80.0, -84.0,
    )
    with session_scope() as db:
        persist_radio_burst(db, burst)
        persist_radio_burst(db, burst)
    with session_scope() as db:
        rows = db.query(RadioBurstDB).filter_by(burst_id="rfb:test").all()
        assert len(rows) == 1
        assert rows[0].sample_count == 3
        db.query(RadioBurstDB).filter_by(burst_id="rfb:test").delete()


def test_bridge_feeds_observations_into_burst_detector(monkeypatch):
    from core.radio import bridge
    from core.radio.burst import RadioBurst
    from core.radio.provider import RadioObservation

    calls = []
    class FakeDetector:
        def ingest(self, observation):
            return (RadioBurst(
                "rfb:bridge", observation.physical_lineage, observation.frequency_hz,
                observation.observed_at, observation.observed_at, 2, -70.0, -72.0,
            ),)

    monkeypatch.setattr(bridge, "_burst_detector", FakeDetector())
    monkeypatch.setattr(bridge, "_persist_radio_observation", lambda observation: calls.append("observation"))
    monkeypatch.setattr(bridge, "_persist_radio_burst", lambda burst: calls.append(burst.burst_id))
    bridge.handle_radio_observation(RadioObservation(
        receiver_id="med_rx_1", provider="kiwisdr", physical_lineage="med_physical_1",
        frequency_hz=2_187_500, mode="usb",
        observed_at=datetime(2026, 9, 7, tzinfo=timezone.utc), signal_dbm=-70.0,
        source_terms="allowed", session_id="s",
    ))
    assert calls == ["observation", "rfb:bridge"]


def test_recent_bursts_create_one_multi_receiver_event():
    from core.db.models import RadioBurstDB, RadioEventDB
    from core.db.session import engine, session_scope
    from core.radio.burst import RadioBurst
    from core.radio.burst_store import persist_radio_burst, correlate_and_persist_recent

    RadioBurstDB.__table__.create(bind=engine(), checkfirst=True)
    RadioEventDB.__table__.create(bind=engine(), checkfirst=True)
    t = datetime(2026, 9, 7, 12, 30, tzinfo=timezone.utc)
    bursts = (
        RadioBurst("rfb:a", "lineage-a", 2_187_500, t, t, 2, -80, -82),
        RadioBurst("rfb:b", "lineage-b", 2_187_500, t, t, 2, -79, -81),
    )
    with session_scope() as db:
        for burst in bursts:
            persist_radio_burst(db, burst)
        event = correlate_and_persist_recent(db, bursts[-1], window_seconds=5)
        assert event is not None
        assert event.independent_receivers == 2
        assert set(event.physical_lineages) == {"lineage-a", "lineage-b"}
    with session_scope() as db:
        db.query(RadioEventDB).filter(RadioEventDB.event_id.like("rfe:%")).delete(synchronize_session=False)
        db.query(RadioBurstDB).filter(RadioBurstDB.burst_id.in_(["rfb:a", "rfb:b"])).delete(synchronize_session=False)


def test_live_radio_events_endpoint_is_bounded_and_hides_lineages():
    from fastapi.testclient import TestClient
    from core.api.main import app
    from core.db.models import RadioEventDB
    from core.db.session import engine, session_scope

    RadioEventDB.__table__.create(bind=engine(), checkfirst=True)
    event_id = "rfe:public-test"
    with session_scope() as db:
        db.merge(RadioEventDB(
            event_id=event_id, frequency_hz=2_187_500,
            started_at=datetime(2026, 9, 7, 13, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 9, 7, 13, 0, 2, tzinfo=timezone.utc),
            independent_receivers=3, physical_lineages=["secret-a", "secret-b", "secret-c"],
            burst_ids=["rfb:a", "rfb:b", "rfb:c"], confidence=0.95,
        ))
    payload = TestClient(app).get("/api/v1/live/radio/events?limit=5").json()
    row = next(item for item in payload["events"] if item["event_id"] == event_id)
    assert row["independent_receivers"] == 3
    assert "physical_lineages" not in str(payload)
    assert "secret-a" not in str(payload)
    assert "burst_ids" not in str(payload)
    with session_scope() as db:
        db.query(RadioEventDB).filter_by(event_id=event_id).delete()
