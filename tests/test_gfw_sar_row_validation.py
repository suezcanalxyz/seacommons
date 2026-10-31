# SPDX-License-Identifier: AGPL-3.0-or-later
"""GFW SAR ingestion must isolate malformed rows and preserve UTC provenance.

Hermetic provider fixture: no live requests or production credentials.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from core.config import config
from core.mda.darkship_cue import _gfw_sar_in_area
from core.intel.satellite_observation import materialize_sar_detections


def test_gfw_sar_skips_invalid_rows_without_losing_valid_detections(monkeypatch):
    monkeypatch.setattr(config, "GFW_API_TOKEN", "synthetic-test-token")
    records = [
        {"lat": 35.2, "lon": 14.1, "entryTimestamp": "2026-10-30T12:00:00Z",
         "mmsi": "123456789"},
        {"lat": "not-a-latitude", "lon": 14.1, "entryTimestamp": "2026-10-30T12:01:00Z"},
        {"lat": float("nan"), "lon": 14.1, "entryTimestamp": "2026-10-30T12:02:00Z"},
        {"lat": 35.2, "lon": float("inf"), "entryTimestamp": "2026-10-30T12:03:00Z"},
        {"lat": True, "lon": 14.1, "entryTimestamp": "2026-10-30T12:04:00Z"},
        {"lat": 91.0, "lon": 14.1, "entryTimestamp": "2026-10-30T12:05:00Z"},
        {"lat": 35.2, "lon": -181.0, "entryTimestamp": "2026-10-30T12:06:00Z"},
        # A date or naive clock is not a time-qualified satellite acquisition.
        {"lat": 35.2, "lon": 14.1, "entryTimestamp": "2026-10-30"},
        {"lat": 35.2, "lon": 14.1, "entryTimestamp": "2026-10-30T12:07:00"},
        {"lat": 35.3, "lon": 14.2, "entryTimestamp": "2026-10-30T13:00:00+01:00",
         "vesselId": "gfw-test-vessel"},
    ]

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"entries": [{"public-global-sar-presence:latest": records}]}

    def fake_post(url, *, params, json, headers, timeout):
        assert url == "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
        assert headers["Authorization"] == "Bearer synthetic-test-token"
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    since = datetime(2026, 10, 30, 0, 0, tzinfo=timezone.utc)
    until = datetime(2026, 10, 30, 23, 59, tzinfo=timezone.utc)
    found = _gfw_sar_in_area((13.0, 34.0, 15.0, 36.0), since, until=until)

    assert len(found) == 2
    assert [(d["lat"], d["lon"]) for d in found] == [(35.2, 14.1), (35.3, 14.2)]
    assert [d["timestamp"] for d in found] == [
        "2026-10-30T12:00:00Z", "2026-10-30T12:00:00Z",
    ]
    assert found[0]["matched"] is True
    assert found[1]["matched"] is True


def test_gfw_sar_missing_token_does_not_call_provider(monkeypatch):
    monkeypatch.setattr(config, "GFW_API_TOKEN", "")

    def forbidden_post(*args, **kwargs):
        raise AssertionError("provider must not be contacted without credentials")

    monkeypatch.setattr(httpx, "post", forbidden_post)
    since = datetime(2026, 10, 30, tzinfo=timezone.utc)
    assert _gfw_sar_in_area((13.0, 34.0, 15.0, 36.0), since) == []


def test_gfw_sar_report_to_canonical_evidence_preserves_lineage_and_match_gate(monkeypatch):
    """A real-shaped provider report must not turn unrelated SAR targets into corroboration."""
    monkeypatch.setattr(config, "GFW_API_TOKEN", "synthetic-test-token")
    dataset = "public-global-sar-presence:latest"
    records = [
        {"lat": 35.2, "lon": 14.1, "entryTimestamp": "2026-10-30T12:00:00Z",
         "mmsi": "123456789", "vesselId": "gfw-exact"},
        {"lat": 35.3, "lon": 14.2, "entryTimestamp": "2026-10-30T12:01:00Z",
         "mmsi": "987654321", "vesselId": "gfw-other"},
        {"lat": 35.4, "lon": 14.3, "entryTimestamp": "2026-10-30T12:02:00Z"},
        {"lat": 35.5, "lon": 14.4, "entryTimestamp": "2026-10-30T12:03:00Z",
         "mmsi": "not-an-mmsi"},
    ]

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"entries": [{dataset: records}]}

    def fake_post(url, *, params, json, headers, timeout):
        assert params["datasets[0]"] == dataset
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    since = datetime(2026, 10, 30, tzinfo=timezone.utc)
    until = datetime(2026, 10, 30, 23, 59, tzinfo=timezone.utc)
    detections = _gfw_sar_in_area((13.0, 34.0, 15.0, 36.0), since, until=until)
    assert len(detections) == 4

    observations = materialize_sar_detections(
        incident_id="incident:fixture",
        cue={"gfw_sar_detections": detections},
        expected_mmsi="123456789",
        episode_id="episode:fixture",
    )
    assert len(observations) == 4
    assert [obs.association_status for obs in observations] == [
        "strong", "conflict", "unmatched_candidate", "provider_matched_unresolved",
    ]
    assert [obs.episode_id for obs in observations] == [
        "episode:fixture", None, None, None,
    ]
    assert [obs.evidence_status for obs in observations] == [
        "associated", "contextual", "contextual", "contextual",
    ]
    assert observations[0].provenance["source_dataset"] == dataset
    assert observations[0].provenance["source_vessel_id"] == "gfw-exact"
    assert observations[0].provenance["match_inference"] == "identity_field_present"
    assert observations[2].provenance["match_inference"] == "no_identity_field"
    assert observations[2].provenance["source_vessel_id"] is None
    assert all(obs.acquisition_time.endswith("+00:00") for obs in observations)
