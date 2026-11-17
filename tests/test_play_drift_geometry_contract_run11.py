"""Regression contract: historical simulated drift is not an observed AIS track."""
from datetime import datetime, timezone
from types import SimpleNamespace

from core.api.routes.play import _drift_item


def test_historical_drift_serializes_as_forecast_with_geometry():
    track = {"type": "LineString", "coordinates": [[14.2, 35.4], [14.3, 35.5]]}
    cone = {"type": "Polygon", "coordinates": [[[14.1, 35.3], [14.4, 35.3], [14.1, 35.3]]]}
    row = SimpleNamespace(
        drift_id="historical-drift", created_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
        trajectory=track, cone_24h=cone, impact_point=None, domain="ocean_sar",
        metadata_json={"model": "OceanDrift"}, model_version="fallback",
    )
    item = _drift_item(row)
    assert item["type"] == "drift"
    assert item["geometry"] == track
    assert item["properties"]["forecast"] is True
    assert item["properties"]["cone_24h"] == cone
    assert item["properties"]["model"] == "OceanDrift"
    assert item["at"].startswith("2026-10-28")
