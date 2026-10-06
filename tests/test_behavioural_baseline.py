from datetime import datetime, timedelta, timezone


def _synthetic_track(count=30):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(count):
        rows.append({
            "mmsi": "229113000",
            "ts": (start + timedelta(hours=i * 4)).isoformat(),
            "lat": 35.90 + (i % 6) * 0.02,
            "lon": 14.30 + (i % 6) * 0.03,
            "sog": 16.0 + (i % 4),
            "nav_status": 0,
            "source": "aisstream",
        })
    return rows


def test_baseline_builder_is_deterministic(monkeypatch):
    from core.mda import behavioural_baseline as bb

    rows = _synthetic_track()
    monkeypatch.setattr(bb, "_load_tracks", lambda mmsi, since, until: rows)
    monkeypatch.setattr(bb, "_registry_identity", lambda mmsi: {"imo": "9848388"})
    monkeypatch.setattr(bb, "_derive_port_calls", lambda track: [
        {"port": "Malta", "arrived_at": track[0]["ts"]},
        {"port": "Gozo", "arrived_at": track[10]["ts"]},
        {"port": "Malta", "arrived_at": track[20]["ts"]},
        {"port": "Gozo", "arrived_at": track[29]["ts"]},
    ])

    a = bb.build_baseline("229113000", window_days=30, now=datetime(2026, 8, 6, tzinfo=timezone.utc))
    b = bb.build_baseline("229113000", window_days=30, now=datetime(2026, 8, 6, tzinfo=timezone.utc))

    assert a is not None and b is not None
    assert a.baseline_id == b.baseline_id
    assert a.evidence_fingerprint == b.evidence_fingerprint
    assert a.sample_count == 30
    assert a.speed_model["p50"] >= 16.0
    assert a.silence_model["p95_seconds"] >= a.silence_model["p50_seconds"]
    assert ["Malta", "Gozo"] in a.port_model["recurrent_pairs"]


def test_baseline_fails_closed_on_sparse_history(monkeypatch):
    from core.mda import behavioural_baseline as bb

    rows = _synthetic_track(5)
    monkeypatch.setattr(bb, "_load_tracks", lambda mmsi, since, until: rows)
    monkeypatch.setattr(bb, "_registry_identity", lambda mmsi: {})
    monkeypatch.setattr(bb, "_derive_port_calls", lambda track: [])
    assert bb.build_baseline("229113000", window_days=30, now=datetime(2026, 8, 2, tzinfo=timezone.utc)) is None


def test_behavioural_baseline_model_has_versioned_schema():
    from core.db.models import VesselBehaviouralBaselineDB

    names = {column.name for column in VesselBehaviouralBaselineDB.__table__.columns}
    assert {
        "baseline_id", "subject_id", "primary_mmsi", "primary_imo",
        "window_start", "window_end", "sample_count", "history_days",
        "route_model", "speed_model", "port_model", "silence_model",
        "evidence_fingerprint", "method_version", "created_at",
    } <= names


def test_persist_baseline_is_idempotent_and_latest(monkeypatch):
    from contextlib import contextmanager
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from core.db.models import Base, VesselBehaviouralBaselineDB
    from core.mda import behavioural_baseline as bb

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    @contextmanager
    def scope():
        with Session(engine) as session:
            yield session
            session.commit()

    monkeypatch.setattr(bb, "_session_scope", scope)
    rows = _synthetic_track()
    monkeypatch.setattr(bb, "_load_tracks", lambda mmsi, since, until: rows)
    monkeypatch.setattr(bb, "_registry_identity", lambda mmsi: {"imo": "9848388"})
    monkeypatch.setattr(bb, "_derive_port_calls", lambda track: [])
    baseline = bb.build_baseline("229113000", window_days=30, now=datetime(2026, 8, 6, tzinfo=timezone.utc))
    assert baseline is not None

    assert bb.persist_baseline(baseline).baseline_id == baseline.baseline_id
    assert bb.persist_baseline(baseline).baseline_id == baseline.baseline_id
    with Session(engine) as session:
        assert session.query(VesselBehaviouralBaselineDB).count() == 1
    assert bb.latest_baseline("229113000").baseline_id == baseline.baseline_id


def test_recent_registry_candidates_uses_persistent_registry_cache(monkeypatch):
    from core.mda import behavioural_baseline as bb
    from core.vessels.registry import registry

    now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(registry, "_cache", {
        "111111111": {"last_seen": (now - timedelta(minutes=5)).isoformat()},
        "222222222": {"last_seen": (now - timedelta(hours=2)).isoformat()},
        "333333333": {"last_seen": (now - timedelta(hours=30)).isoformat()},
        "444444444": {"last_seen": None},
    })

    rows = bb._recent_registry_candidates(now=now, limit=10)
    assert [mmsi for mmsi, _ in rows] == ["111111111", "222222222"]


def test_refresh_recent_baselines_uses_bounded_registry_selector(monkeypatch):
    from core.mda import behavioural_baseline as bb

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        bb,
        "_recent_registry_candidates",
        lambda **kwargs: [("111111111", now), ("222222222", now)],
    )
    monkeypatch.setattr(bb, "latest_baseline", lambda mmsi: None)
    built = []

    def fake_build(mmsi, *, window_days, now):
        if mmsi == "222222222":
            return None
        return object()

    monkeypatch.setattr(bb, "build_baseline", fake_build)
    monkeypatch.setattr(bb, "persist_baseline", lambda baseline: built.append(baseline))

    result = bb.refresh_recent_baselines(limit=2, window_days=30, min_age_hours=24)
    assert result == {
        "built": 1,
        "skipped_fresh": 0,
        "insufficient_history": 1,
        "failed": 0,
    }
    assert len(built) == 1
