# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.vessels.ais_provider import AISPositionObservation
from core.vessels.ais_reconcile import AISReconciler

_BASE = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)


def _obs(provider, lat, lon, *, second=0, upstream=None, raw_id=None, station=None):
    t = _BASE + timedelta(seconds=second)
    return AISPositionObservation(
        mmsi="247123456", ship_name="TEST", lat=lat, lon=lon,
        sog=8.0, cog=90.0, heading=90.0, nav_status=0,
        observed_at=t, received_at=t, provider=provider,
        upstream_source=upstream or provider, station_id=station,
        raw_message_id=raw_id,
    )


def test_same_aisstream_lineage_delivered_through_aiscast_collapses():
    r = AISReconciler(max_time_delta_s=15, max_distance_m=250)
    first = r.ingest(_obs("aisstream", 35.0, 15.0, second=0, upstream="aisstream"))
    duplicate = r.ingest(_obs("aiscast", 35.0002, 15.0002, second=5, upstream="aisstream"))
    assert first is not None
    assert duplicate is None
    context = r.context_for("247123456")
    assert context.transport_providers == frozenset({"aisstream", "aiscast"})
    assert context.upstream_sources == frozenset({"aisstream"})


def test_materially_new_volunteer_fix_is_preserved_without_averaging():
    r = AISReconciler(max_time_delta_s=15, max_distance_m=250)
    r.ingest(_obs("aisstream", 35.0, 15.0, second=0, upstream="aisstream"))
    fix = r.ingest(_obs("aiscast", 35.02, 15.02, second=10, upstream="volunteer", station="mt-01"))
    assert fix is not None
    assert fix.lat == 35.02 and fix.lon == 15.02
    assert fix.transport_providers == frozenset({"aiscast"})
    assert fix.upstream_sources == frozenset({"volunteer"})
    assert fix.station_ids == frozenset({"mt-01"})


def test_exact_raw_message_identity_collapses_duplicate_delivery():
    r = AISReconciler()
    first = r.ingest(_obs("aiscast", 35.0, 15.0, raw_id="abc", upstream="volunteer"))
    second = r.ingest(_obs("aiscast", 35.0, 15.0, second=0, raw_id="abc", upstream="volunteer"))
    assert first is not None
    assert second is None


def test_close_but_different_upstream_fix_is_not_suppressed_without_shared_identity():
    r = AISReconciler(max_time_delta_s=15, max_distance_m=250)
    r.ingest(_obs("aisstream", 35.0, 15.0, upstream="aisstream"))
    second = r.ingest(_obs("aiscast", 35.0001, 15.0001, second=4, upstream="volunteer"))
    assert second is not None


def test_track_store_preserves_selected_upstream_on_reconciled_fix(monkeypatch):
    import core.vessels.track_store as track_module
    from core.vessels.track_store import TrackStore

    monkeypatch.setattr(track_module, "_SYNC", False)

    r = AISReconciler()
    fix = r.ingest(_obs("aiscast", 35.02, 15.02, upstream="volunteer", station="mt-01"))
    store = TrackStore()
    store.on_reconciled_fix(fix)
    assert store._buffer[-1]["source"] == "volunteer"


def test_registry_projects_reconciled_provider_context(tmp_path):
    from core.vessels.registry import VesselRegistry

    r = AISReconciler()
    fix = r.ingest(_obs("aiscast", 35.02, 15.02, upstream="volunteer", station="mt-01"))
    registry = VesselRegistry(tmp_path / "vessels.db")
    registry.upsert_reconciled(fix)
    feature = registry.get_geojson(since="2026-09-06T00:00:00+00:00")["features"][0]
    assert feature["properties"]["sources"] == ["aiscast"]
    assert feature["properties"]["upstream_sources"] == ["volunteer"]
    assert feature["properties"]["stations"] == ["mt-01"]
