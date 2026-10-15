from __future__ import annotations

from core.acquisition.status import _sanitize_radio_pipeline
from core.radio.pipeline import public_radio_pipeline


def _pipeline(*, accepted=0, persisted=0, review=0, matches=0, episodes=0):
    return public_radio_pipeline(
        radio_state="live", structured_state="listening" if accepted == 0 else "live",
        active_receivers=3,
        decoder={"frames": 1234, "decoded": accepted, "accepted": accepted,
                 "dsc_accepted": accepted, "navtex_accepted": 0},
        structured={"accepted": persisted, "dsc_persisted": persisted, "projected": review},
        correlations={"ais_strong_matches": matches, "episodes_linked": episodes},
    )


def test_radio_pipeline_listening_does_not_invent_messages_evidence_or_distress():
    payload = _pipeline()
    rows = {item["id"]: item for item in payload["stages"]}
    assert payload["count_scope"] == "since_process_start"
    assert rows["reception"]["count"] == 3
    assert rows["demodulation"]["count"] == 1234
    for stage in ("validation", "evidence", "ais_correlation", "episode", "safety_review"):
        assert rows[stage]["count"] == 0
    assert rows["demodulation"]["state"] == "listening"
    assert rows["safety_review"]["state"] == "none_verified"


def test_radio_pipeline_tracks_only_verified_dsc_evidence_and_review_candidates():
    payload = _pipeline(accepted=4, persisted=3, review=1, matches=2, episodes=1)
    rows = {item["id"]: item for item in payload["stages"]}
    assert rows["validation"]["state"] == "verified"
    assert rows["validation"]["count"] == 4
    assert rows["evidence"]["count"] == 3
    assert rows["ais_correlation"]["count"] == 2
    assert rows["episode"]["count"] == 1
    assert rows["safety_review"]["state"] == "review_required"
    assert rows["safety_review"]["count"] == 1


def test_public_radio_pipeline_never_exposes_unknown_stage_or_private_metadata():
    data = _pipeline()
    data["physical_lineage"] = "SECRET:receiver"
    data["stages"][0]["private_url"] = "https://internal.example"
    data["stages"][0]["label"] = "SECRET: receiver host"
    data["stages"].append({"id": "unknown", "state": "live", "count": 2})
    assert _sanitize_radio_pipeline(data) == {}
    data["stages"].pop()
    public = _sanitize_radio_pipeline(data)
    assert public["count_scope"] == "since_process_start"
    assert all("physical_lineage" not in str(stage) for stage in public["stages"])
    assert "internal.example" not in str(public)
    assert "SECRET" not in str(public)


def test_orderly_shutdown_stops_producers_before_decoder_and_ocr(monkeypatch):
    from core.api.lifecycle import stop_background_services
    from core.intel.engine import intel_engine
    from core.intel.media_ocr_queue import media_ocr_queue
    from core import scheduler
    from core.radio import decoder_runtime, runtime as remote_runtime
    from core.vessels import aisstream

    called = []
    monkeypatch.setattr(scheduler, "stop", lambda: called.append("scheduler"))
    monkeypatch.setattr(intel_engine, "stop", lambda: called.append("intel"))
    monkeypatch.setattr(aisstream, "stop_clients", lambda: called.append("ais"))
    monkeypatch.setattr(remote_runtime, "stop_remote_radio", lambda: called.append("receivers"))
    monkeypatch.setattr(decoder_runtime, "stop_radio_decoder_runtime", lambda: called.append("decoder"))
    monkeypatch.setattr(media_ocr_queue, "shutdown", lambda: called.append("ocr"))
    assert stop_background_services() == []
    assert called == ["scheduler", "intel", "ais", "receivers", "decoder", "ocr"]


def test_shutdown_keeps_releasing_resources_when_one_service_fails(monkeypatch):
    from core.api.lifecycle import stop_background_services
    from core.intel.engine import intel_engine
    from core.intel.media_ocr_queue import media_ocr_queue
    from core import scheduler
    from core.radio import decoder_runtime, runtime as remote_runtime
    from core.vessels import aisstream

    called = []
    monkeypatch.setattr(scheduler, "stop", lambda: called.append("scheduler"))
    monkeypatch.setattr(intel_engine, "stop", lambda: called.append("intel"))
    monkeypatch.setattr(aisstream, "stop_clients", lambda: called.append("ais"))
    def fail():
        called.append("receivers")
        raise RuntimeError("simulated socket shutdown error")
    monkeypatch.setattr(remote_runtime, "stop_remote_radio", fail)
    monkeypatch.setattr(decoder_runtime, "stop_radio_decoder_runtime", lambda: called.append("decoder"))
    monkeypatch.setattr(media_ocr_queue, "shutdown", lambda: called.append("ocr"))
    assert stop_background_services() == ["radio_receivers"]
    assert called[-2:] == ["decoder", "ocr"]


def test_ocr_shutdown_refuses_new_work_and_reset_allows_test_reuse():
    from core.intel.media_ocr_queue import MediaOcrQueue
    pool = MediaOcrQueue(workers=1, maxsize=2)
    pool.shutdown()
    assert pool.submit("later", lambda: None) == "dropped"
    assert pool.stats()["depth"] == 0
    pool.reset()
    pool.shutdown()


def test_ais_shutdown_closes_both_independent_clients(monkeypatch):
    from core.vessels import aisstream
    closed = []
    class FakeClient:
        def __init__(self, name):self.name = name
        def stop(self):closed.append(self.name)
    monkeypatch.setattr(aisstream, "_client", FakeClient("regional"))
    monkeypatch.setattr(aisstream, "_ngo_client", FakeClient("ngo"))
    aisstream.stop_clients()
    assert closed == ["regional", "ngo"]
    assert aisstream._client is None and aisstream._ngo_client is None


def test_navtex_decodes_cannot_be_mistaken_for_verified_dsc():
    pipeline = public_radio_pipeline(
        radio_state="live", structured_state="live", active_receivers=2,
        decoder={"frames": 100, "accepted": 9, "dsc_accepted": 0, "navtex_accepted": 9},
        structured={"dsc_persisted": 0, "navtex_persisted": 9, "projected": 0},
        correlations={},
    )
    stages = {stage["id"]: stage for stage in pipeline["stages"]}
    assert stages["validation"]["count"] == 0
    assert stages["evidence"]["count"] == 0
    assert stages["safety_review"]["count"] == 0
