from datetime import datetime, timedelta, timezone


def test_build_vessel_context_projects_existing_truth(monkeypatch):
    from core.mda import vessel_context

    now = datetime.now(timezone.utc)
    track = [
        {"mmsi": "229113000", "ts": (now - timedelta(hours=3)).isoformat(), "lat": 35.9, "lon": 14.5, "sog": 18.0, "nav_status": 0},
        {"mmsi": "229113000", "ts": (now - timedelta(hours=2)).isoformat(), "lat": 36.0, "lon": 14.4, "sog": 17.0, "nav_status": 0},
        {"mmsi": "229113000", "ts": (now - timedelta(hours=1)).isoformat(), "lat": 36.1, "lon": 14.3, "sog": 16.0, "nav_status": 0},
    ]
    monkeypatch.setattr(vessel_context, "_registry_row", lambda mmsi: {"mmsi": mmsi, "ship_name": "YOUR WISDOM", "imo": "9848388", "ship_type": 40, "flag": "MT", "destination": "MTMSX<>MTMGZ"})
    monkeypatch.setattr(vessel_context, "_track", lambda mmsi, since: track)
    monkeypatch.setattr(vessel_context, "_recent_port_calls", lambda rows: [{"port": "Malta", "evidence_level": "derived"}])

    result = vessel_context.build_vessel_context("229113000", hours=24)

    assert result["subject_id"] == "subj:imo:9848388"
    assert result["static"]["name"] == "YOUR WISDOM"
    assert result["history"]["sample_count"] == 3
    assert result["recent_port_calls"][0]["evidence_level"] == "derived"
    assert result["context_labels"] == [{"code": "RECURRENT_HISTORY_AVAILABLE", "evidence_level": "derived"}]
