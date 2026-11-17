"""Live-edge receipt lifecycle: exact incident IDs and rescan-safe retention."""

from datetime import datetime, timedelta, timezone

from core.live_edge_publisher import LiveEdgePublisher, Outbox, PublisherSettings


def test_receipt_lookup_escapes_sql_like_wildcards(tmp_path):
    outbox = Outbox(tmp_path / "receipts.db")
    try:
        for incident in ("case_1%", r"case\id"):
            event_id = f"{incident}:v1"
            assert outbox.enqueue(event_id, {"id": event_id})
            outbox.acknowledge(event_id)
            assert outbox.was_ever_delivered(incident)
        assert not outbox.was_ever_delivered("caseX1Z")
        assert not outbox.was_ever_delivered("case_1")
        assert not outbox.was_ever_delivered(r"case\id-extra")
    finally:
        outbox.connection.close()


def test_runtime_prune_retains_receipts_through_scan_window(tmp_path, monkeypatch):
    settings = PublisherSettings(
        edge_url="https://example.invalid/ingest",
        ingest_secret="test-secret",
        node_id="node",
        outbox_path=tmp_path / "receipts.db",
        live_window_minutes=8 * 24 * 60,
        poll_seconds=1.0,
    )
    publisher = LiveEdgePublisher(settings)
    now = datetime.now(timezone.utc)
    try:
        for incident, days_old in (("within-window", 3), ("outside-window", 12)):
            event_id = f"{incident}:v1"
            publisher.outbox.enqueue(event_id, {"id": event_id})
            publisher.outbox.acknowledge(event_id)
            publisher.outbox.connection.execute(
                "UPDATE delivered SET delivered_at=? WHERE event_id=?",
                ((now - timedelta(days=days_old)).isoformat(), event_id),
            )
        publisher.outbox.connection.commit()
        publisher.cycles = 3599
        monkeypatch.setattr(publisher, "collect", lambda: 0)

        def deliver_and_stop():
            publisher.stop()
            return 0

        monkeypatch.setattr(publisher, "deliver", deliver_and_stop)
        monkeypatch.setattr(publisher, "heartbeat", lambda status: None)
        monkeypatch.setattr(publisher, "origin_status", lambda: "active")
        monkeypatch.setattr(
            "core.live_edge_publisher.record_publisher_cycle", lambda **kw: None
        )
        publisher.run()
        assert publisher.outbox.was_ever_delivered("within-window")
        assert not publisher.outbox.was_ever_delivered("outside-window")
    finally:
        publisher.client.close()
        publisher.outbox.connection.close()
