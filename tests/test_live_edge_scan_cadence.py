"""Ensure edge scans do not saturate PostgreSQL while delivery stays responsive."""

from core.live_edge_publisher import LiveEdgePublisher, PublisherSettings


def test_edge_db_scan_throttled_but_outbox_delivers_each_poll(tmp_path, monkeypatch):
    class Clock:
        now = 0.0
        def monotonic(self):
            return self.now
        def sleep(self, duration):
            self.now += duration

    clock = Clock()
    monkeypatch.setattr("core.live_edge_publisher.time.monotonic", clock.monotonic)
    monkeypatch.setattr("core.live_edge_publisher.time.sleep", clock.sleep)
    monkeypatch.setattr("core.live_edge_publisher.record_publisher_cycle", lambda **kw: None)
    settings = PublisherSettings(
        edge_url="https://example.invalid/ingest", ingest_secret="test-secret",
        node_id="test", outbox_path=tmp_path / "outbox.db",
        poll_seconds=1.0, scan_interval_seconds=5.0, origin_health_url="",
    )
    publisher = LiveEdgePublisher(settings)
    scans = []
    deliveries = []
    def collect():
        scans.append(clock.now)
        return 0
    def deliver():
        deliveries.append(clock.now)
        if len(deliveries) == 7:
            publisher.stop()
        return 0
    monkeypatch.setattr(publisher, "collect", collect)
    monkeypatch.setattr(publisher, "deliver", deliver)
    monkeypatch.setattr(publisher, "heartbeat", lambda status: None)
    monkeypatch.setattr(publisher, "origin_status", lambda: "active")
    try:
        publisher.run()
    finally:
        publisher.client.close()
        publisher.outbox.connection.close()
    assert scans == [0.0, 5.0]
    assert deliveries == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_scan_interval_default_and_env_override(monkeypatch):
    monkeypatch.delenv("LIVE_EDGE_SCAN_INTERVAL_SECONDS", raising=False)
    assert PublisherSettings.from_env().scan_interval_seconds == 5.0
    monkeypatch.setenv("LIVE_EDGE_SCAN_INTERVAL_SECONDS", "2")
    assert PublisherSettings.from_env().scan_interval_seconds == 2.0


def test_slow_db_scan_waits_full_interval_after_completion(tmp_path, monkeypatch):
    """A slow DB scan cannot cause an immediate follow-up scan under CPU load."""
    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    clock = Clock()
    monkeypatch.setattr("core.live_edge_publisher.time.monotonic", clock.monotonic)
    monkeypatch.setattr("core.live_edge_publisher.time.sleep", clock.sleep)
    monkeypatch.setattr("core.live_edge_publisher.record_publisher_cycle", lambda **kw: None)
    publisher = LiveEdgePublisher(PublisherSettings(
        edge_url="https://example.invalid/ingest", ingest_secret="test-secret",
        node_id="test", outbox_path=tmp_path / "slow-scan.db",
        poll_seconds=1.0, scan_interval_seconds=5.0, origin_health_url="",
    ))
    scans = []
    deliveries = []

    def slow_collect():
        scans.append(clock.now)
        clock.now += 7.0
        return 0

    def deliver():
        deliveries.append(clock.now)
        if len(deliveries) == 3:
            publisher.stop()
        return 0

    monkeypatch.setattr(publisher, "collect", slow_collect)
    monkeypatch.setattr(publisher, "deliver", deliver)
    monkeypatch.setattr(publisher, "heartbeat", lambda status: None)
    monkeypatch.setattr(publisher, "origin_status", lambda: "active")
    try:
        publisher.run()
    finally:
        publisher.client.close()
        publisher.outbox.connection.close()
    assert scans == [0.0]
    assert deliveries == [7.0, 7.0, 8.0]
