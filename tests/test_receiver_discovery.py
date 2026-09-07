from core.radio.discovery import (
    DiscoveryRegistry,
    parse_kiwi_public_html,
    parse_receiverbook_html,
)


def test_receiverbook_discovery_normalizes_public_candidate_without_auto_authorizing():
    html = '''<div class="receiver-details"><h5>Catania SDR</h5>
    <ul class="stationreceiverlist"><li><div><a href="http://rx.example:8073/">Catania HF</a></div>
    <div>OpenWebRX 1.2.123</div></li></ul></div>'''
    rows = parse_receiverbook_html(html)
    assert len(rows) == 1
    row = rows[0]
    assert row.network_family == "openwebrx"
    assert row.public_label == "Catania HF"
    assert row.terms_status == "review_required"
    assert row.activation_status == "catalogued"


def test_kiwi_directory_discovery_normalizes_candidate_without_auto_authorizing():
    html = '''<div>KiwiSDR 2 v1.832</div><b>0-30 MHz SDR | MALTA</b>
    <a href="http://malta.example:8073">http://malta.example:8073</a>'''
    rows = parse_kiwi_public_html(html)
    assert len(rows) == 1
    assert rows[0].network_family == "kiwisdr"
    assert rows[0].terms_status == "review_required"
    assert rows[0].activation_status == "catalogued"


def test_discovery_registry_deduplicates_candidates_and_hides_endpoints_publicly():
    registry = DiscoveryRegistry()
    registry.replace_source("receiverbook", parse_receiverbook_html('''
      <div class="receiver-details"><h5>Station</h5><ul class="stationreceiverlist"><li>
      <div><a href="http://same.example:8073/">Station RX</a></div><div>OpenWebRX 1.2</div>
      </li></ul></div>'''))
    registry.replace_source("other", parse_receiverbook_html('''
      <div class="receiver-details"><h5>Station Duplicate</h5><ul class="stationreceiverlist"><li>
      <div><a href="http://same.example:8073/">Station RX duplicate</a></div><div>OpenWebRX 1.2</div>
      </li></ul></div>'''))
    snapshot = registry.public_snapshot(limit=10)
    assert snapshot["catalogued"] == 1
    assert len(snapshot["receivers"]) == 1
    assert "endpoint" not in snapshot["receivers"][0]
    assert "same.example" not in str(snapshot)


def test_discovery_source_failure_is_recorded_without_losing_other_sources():
    registry = DiscoveryRegistry()
    registry.replace_source("receiverbook", parse_receiverbook_html('''
      <div class="receiver-details"><h5>Station</h5><ul class="stationreceiverlist"><li>
      <div><a href="http://ok.example:8073/">Station RX</a></div><div>OpenWebRX 1.2</div>
      </li></ul></div>'''))
    registry.record_failure("kiwi", "private upstream detail")
    snapshot = registry.public_snapshot(limit=10)
    assert snapshot["sources"]["receiverbook"] == "live"
    assert snapshot["sources"]["kiwi"] == "offline"
    assert "private upstream detail" not in str(snapshot)


def test_refresh_discovery_is_bounded_and_fail_isolated():
    from core.radio.discovery import refresh_discovery

    registry = DiscoveryRegistry()
    pages = {
        "receiverbook": '''<div class="receiver-details"><h5>A</h5><ul class="stationreceiverlist"><li><div><a href="http://a.example:8073/">A RX</a></div><div>OpenWebRX 1.2</div></li></ul></div>''',
    }

    def fetch(url: str) -> str:
        if "receiverbook" in url:
            return pages["receiverbook"]
        raise OSError("upstream secret")

    refresh_discovery(registry=registry, fetch_text=fetch)
    snapshot = registry.public_snapshot(limit=10)
    assert snapshot["catalogued"] == 1
    assert snapshot["sources"]["receiverbook"] == "live"
    assert snapshot["sources"]["kiwi_public"] == "offline"
    assert "upstream secret" not in str(snapshot)


def test_discovery_public_snapshot_endpoint_is_safe(monkeypatch):
    from core.api.main import app
    from core.radio import discovery
    from fastapi.testclient import TestClient

    registry = DiscoveryRegistry()
    registry.replace_source("receiverbook", parse_receiverbook_html('''
      <div class="receiver-details"><h5>Malta candidate</h5>
      <ul class="stationreceiverlist"><li><div>
      <a href="http://secret-malta.example:8073/">Malta RX</a></div>
      <div>OpenWebRX 1.2</div></li></ul></div>'''))
    monkeypatch.setattr(discovery, "discovery_registry", registry)
    response = TestClient(app).get("/api/v1/live/receivers/discovery?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["catalogued"] == 1
    assert payload["receivers"][0]["terms_status"] == "review_required"
    assert "endpoint" not in str(payload)
    assert "secret-malta.example" not in str(payload)


def test_scheduler_receiver_discovery_job_is_fail_closed(monkeypatch):
    from core.radio import discovery

    from core import scheduler

    calls = []
    monkeypatch.setattr(discovery, "refresh_discovery", lambda: calls.append("refresh") or {"catalogued": 3})
    scheduler._job_receiver_discovery()
    assert calls == ["refresh"]

    def boom():
        raise RuntimeError("private upstream detail")

    monkeypatch.setattr(discovery, "refresh_discovery", boom)
    scheduler._job_receiver_discovery()


def test_refresh_discovery_follows_bounded_receiverbook_pages():
    from core.radio.discovery import refresh_discovery

    registry = DiscoveryRegistry()
    page1 = '''<a href="/?band=any-public&amp;type=openwebrx&amp;page=2">2</a>
      <div class="receiver-details"><h5>A</h5><ul class="stationreceiverlist"><li>
      <div><a href="http://a.example:8073/">A RX</a></div><div>OpenWebRX 1.2</div>
      </li></ul></div>'''
    page2 = '''<div class="receiver-details"><h5>B</h5><ul class="stationreceiverlist"><li>
      <div><a href="http://b.example:8073/">B RX</a></div><div>OpenWebRX 1.2</div>
      </li></ul></div>'''
    seen = []

    def fetch(url: str) -> str:
        seen.append(url)
        if "kiwisdr.com" in url:
            raise OSError("offline")
        return page2 if "page=2" in url else page1

    snapshot = refresh_discovery(registry=registry, fetch_text=fetch)
    assert snapshot["catalogued"] == 2
    assert any("page=2" in url for url in seen)
