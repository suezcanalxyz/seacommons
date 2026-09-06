import json
from datetime import datetime, timezone
from pathlib import Path


def _load(path):
    return json.loads(Path(path).read_text().strip())


def _assess_fixture(monkeypatch, fixture):
    from core.mda import behavioural_baseline as bb
    from core.mda.behaviour_assessment import assess_behaviour

    monkeypatch.setattr(bb, "_load_tracks", lambda mmsi, since, until: fixture["behavioural_history"])
    monkeypatch.setattr(bb, "_registry_identity", lambda mmsi: {"imo": fixture["vessel"]["imo"]})
    monkeypatch.setattr(bb, "_derive_port_calls", lambda rows: fixture["port_calls"])
    now = datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc)
    baseline = bb.build_baseline(fixture["vessel"]["mmsi"], window_days=30, now=now)
    assert baseline is not None
    return assess_behaviour(fixture["current_track"], baseline, evaluated_at=now)


def test_your_wisdom_recurrent_service_is_expected(monkeypatch):
    fixture = _load("tests/fixtures/osint/benign_service_vessels.jsonl")
    result = _assess_fixture(monkeypatch, fixture)
    assert result.status == fixture["expected"]["behaviour_status"]
    assert result.reason_codes == ()


def test_same_identity_contrastive_deviation_is_unusual(monkeypatch):
    fixture = _load("tests/fixtures/osint/behaviour_contrastive.jsonl")
    result = _assess_fixture(monkeypatch, fixture)
    assert result.status == fixture["expected"]["behaviour_status"]
    assert set(fixture["expected"]["reason_codes"]) <= set(result.reason_codes)


def test_production_code_has_no_benign_fixture_exception():
    root = Path("apps/api/core")
    forbidden = ("YOUR WISDOM", "229113000", "9848388")
    hits = []
    for path in root.rglob("*.py"):
        text = path.read_text(errors="ignore")
        if any(value in text for value in forbidden):
            hits.append(str(path))
    assert hits == []
