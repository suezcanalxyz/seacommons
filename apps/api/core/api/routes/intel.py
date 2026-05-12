# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Maritime intelligence API routes.

GET  /api/v1/intel                   All events GeoJSON (filterable)
GET  /api/v1/intel/stats             Event counts by type/severity
GET  /api/v1/intel/ngo               NGO/coastguard vessel positions (GeoJSON)
GET  /api/v1/intel/ais-spikes        AIS anomaly events only
WS   /ws/intel                       Real-time event stream (JSON per event)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from core.intel.ngo_registry import NGO_VESSELS, get_ngo_info, is_ngo
from core.intel.store import intel_store

router = APIRouter()
logger = logging.getLogger(__name__)


# ── REST endpoints ─────────────────────────────────────────────────────────────

@router.get("/api/v1/intel")
async def get_intel(
    severity: Optional[str] = Query(None, description="critical|high|medium|low"),
    type_filter: Optional[str] = Query(None, alias="type",
                                        description="twitter|news|iom_incident|ais_spike|ngo_activity"),
    limit: int = Query(200, ge=1, le=500),
):
    """
    All intelligence events as GeoJSON FeatureCollection.
    Only events with known coordinates are included in `features`.
    Events without coordinates are listed in `meta.no_coords`.
    """
    all_events = intel_store.events(severity=severity, type_filter=type_filter, limit=limit)
    with_coords = [e for e in all_events if e.lat is not None and e.lon is not None]
    no_coords   = [e for e in all_events if e.lat is None or e.lon is None]

    return {
        "type": "FeatureCollection",
        "features": [e.to_geojson_feature() for e in with_coords],
        "meta": {
            "total": len(all_events),
            "with_coords": len(with_coords),
            "no_coords_count": len(no_coords),
            "no_coords": [
                {"id": e.id, "type": e.type, "severity": e.severity,
                 "title": e.title[:100], "source": e.source,
                 "timestamp_utc": e.timestamp_utc}
                for e in no_coords[:30]
            ],
        },
    }


@router.get("/api/v1/intel/stats")
async def get_intel_stats():
    """Event counts by type and severity."""
    return intel_store.stats()


@router.get("/api/v1/intel/ngo")
async def get_ngo_positions():
    """
    Live positions of known NGO and coastguard vessels from AIS registry.
    Enriched with org, role, and website data.
    Returns GeoJSON FeatureCollection.
    """
    from core.vessels.registry import registry  # lazy to avoid circular

    geojson = registry.get_geojson()
    ngo_features = []
    seen_mmsi: set[str] = set()

    # Enrich positioned NGO vessels from live AIS
    for feat in geojson.get("features", []):
        props = feat.get("properties") or {}
        mmsi = str(props.get("mmsi", ""))
        if not is_ngo(mmsi):
            continue
        info = get_ngo_info(mmsi) or {}
        seen_mmsi.add(mmsi)
        ngo_features.append({
            **feat,
            "properties": {
                **props,
                "intel_type": "ngo_vessel",
                "org": info.get("org", ""),
                "role": info.get("role", ""),
                "vessel_class": "ngo",
            },
        })

    # Add known NGO vessels not currently in AIS (show as "last known" or "offline")
    for mmsi, info in NGO_VESSELS.items():
        if mmsi in seen_mmsi:
            continue
        ngo_features.append({
            "type": "Feature",
            "geometry": None,  # no current position
            "properties": {
                "mmsi": mmsi,
                "ship_name": info.get("name", ""),
                "org": info.get("org", ""),
                "role": info.get("role", ""),
                "flag": info.get("flag", ""),
                "intel_type": "ngo_vessel",
                "ais_status": "offline",
                "vessel_class": "ngo",
            },
        })

    return {
        "type": "FeatureCollection",
        "features": ngo_features,
        "meta": {
            "total_registered": len(NGO_VESSELS),
            "live_ais": len(seen_mmsi),
            "offline": len(NGO_VESSELS) - len(seen_mmsi),
        },
    }


@router.get("/api/v1/intel/ais-spikes")
async def get_ais_spikes(limit: int = Query(50, ge=1, le=200)):
    """AIS anomaly events (sudden stops, clusters, NGO search patterns)."""
    events = intel_store.events(type_filter="ais_spike", limit=limit)
    features = [e.to_geojson_feature() for e in events if e.lat is not None]
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {"count": len(features)},
    }


@router.get("/api/v1/intel/twitter")
async def get_twitter_events(
    severity: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=300),
):
    """Social media (Twitter/X) distress signals only."""
    events = intel_store.events(severity=severity, type_filter="twitter", limit=limit)
    features = [e.to_geojson_feature() for e in events if e.lat is not None]
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "count": len(features),
            "no_coords": len(events) - len(features),
        },
    }


@router.get("/api/v1/intel/incidents")
async def get_iom_incidents(limit: int = Query(50, ge=1, le=200)):
    """IOM Missing Migrants verified incidents."""
    events = intel_store.events(type_filter="iom_incident", limit=limit)
    features = [e.to_geojson_feature() for e in events if e.lat is not None]
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {"count": len(features)},
    }


# ── WebSocket real-time stream ─────────────────────────────────────────────────

@router.websocket("/ws/intel")
async def ws_intel(websocket: WebSocket):
    """
    Real-time intel stream.  Sends a JSON payload for every new IntelEvent
    as it arrives.  Client receives GeoJSON Feature objects.

    On connect: sends the last 50 events as a batch (type="snapshot").
    Then: individual events streamed as type="event".
    """
    await websocket.accept()
    loop = asyncio.get_event_loop()
    intel_store.register_ws(websocket, loop)
    logger.info("Intel WebSocket client connected")

    try:
        # Snapshot of recent events on connect
        recent = intel_store.events(limit=50)
        import json
        snapshot = json.dumps({
            "type": "snapshot",
            "features": [e.to_geojson_feature() for e in recent],
        })
        await websocket.send_text(snapshot)

        # Keep connection alive; new events are pushed via intel_store.broadcast()
        while True:
            await asyncio.sleep(30)
            await websocket.send_text('{"type":"ping"}')

    except WebSocketDisconnect:
        logger.info("Intel WebSocket client disconnected")
    except Exception as exc:
        logger.warning("Intel WebSocket error: %s", exc)
    finally:
        intel_store.unregister_ws(websocket)
