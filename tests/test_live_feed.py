from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./core/data/test_live_feed.db")
os.environ.setdefault("RUNTIME_PROFILE", "operational")

from fastapi.testclient import TestClient

from core.api.main import app
from core.api.routes.live import _public_intel_feature
from core.config import config
from core.ingestion.signal import DistressSignal
from core.intel.store import IntelEvent


client = TestClient(app)


def test_public_projection_excludes_sensitive_content() -> None:
    event = IntelEvent(
        id="public01",
        type="distress",
        severity="high",
        lat=35.5,
        lon=14.1,
        title="Reported maritime distress",
        text="Private phone and free-form message",
        author="@private_handle",
        source="Public source",
        url="https://example.org/report",
        metadata={"is_distress": True, "private_note": "must not leak"},
    )
    feature = _public_intel_feature(event)
    assert feature is not None
    assert feature["properties"]["text"] == ""
    assert "author" not in feature["properties"]
    assert "private_note" not in feature["properties"]
    assert feature["properties"]["publication_status"] == "published"


def test_manual_event_requires_explicit_publication() -> None:
    private = IntelEvent(
        id="manual01",
        type="manual",
        severity="high",
        lat=35.5,
        lon=14.1,
        title="Operator note",
        source="operator",
    )
    assert _public_intel_feature(private) is None
    private.metadata["publication_status"] = "published"
    assert _public_intel_feature(private) is not None


def test_user_signal_is_private_by_default() -> None:
    signal = DistressSignal(
        source_channel="whatsapp",
        source_id="+390000000",
        raw_text="help",
        lat=35.5,
        lon=14.1,
    )
    assert signal.publication_status == "private"


def test_live_routes_remain_public_when_internal_reads_require_auth() -> None:
    previous = config.AUTH_ENABLED
    config.AUTH_ENABLED = True
    try:
        public_feed = client.get("/api/v1/live/signals")
        internal_feed = client.get("/api/v1/intel")
        assert public_feed.status_code == 200
        assert public_feed.json()["meta"]["schema"] == "org.seacommons.live-feed/v1"
        assert internal_feed.status_code == 401
    finally:
        config.AUTH_ENABLED = previous
