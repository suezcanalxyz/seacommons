# SPDX-License-Identifier: AGPL-3.0-or-later
"""TimeZero Professional bridge — push drift results as marks, routes, and zones.

Endpoint paths are centralised in _TZ_ENDPOINTS so they can be updated to match
the installed TZ version without touching any logic below.
"""
from __future__ import annotations

import logging
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── TimeZero Remote API endpoint paths ────────────────────────────────────────
# Verify these against your TZ Professional version's Remote API documentation.
_TZ_ENDPOINTS: dict[str, str] = {
    "status":  "/api/v1/status",
    "mark":    "/api/v1/objects/marks",
    "route":   "/api/v1/objects/routes",
    "zone":    "/api/v1/objects/zones",
}

# KML color in AABBGGRR format (TZ / Google Earth standard)
_CONE_COLORS = {
    "6h":  ("Amber 6h",  "7f00a5ff"),
    "12h": ("Orange 12h","7f0055ff"),
    "24h": ("Red 24h",   "7f0000ff"),
}


class TimeZeroClient:
    """Thin sync HTTP wrapper around the TZ Professional Remote API."""

    def __init__(self, host: str, port: int, api_key: str | None) -> None:
        self._base = f"http://{host}:{port}"
        self._headers: dict[str, str] = {}
        if api_key:
            self._headers["X-API-Key"] = api_key

    def _post(self, path: str, payload: dict) -> None:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                self._base + path,
                json=payload,
                headers=self._headers,
            )
            resp.raise_for_status()

    def health_check(self) -> bool:
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(
                    self._base + _TZ_ENDPOINTS["status"],
                    headers=self._headers,
                )
            return resp.status_code == 200
        except Exception:
            return False

    def push_mark(self, lat: float, lon: float, name: str, color: str = "red") -> None:
        self._post(_TZ_ENDPOINTS["mark"], {
            "name": name,
            "lat": lat,
            "lon": lon,
            "color": color,
        })

    def push_route(self, waypoints: list[tuple[float, float]], name: str) -> None:
        self._post(_TZ_ENDPOINTS["route"], {
            "name": name,
            "waypoints": [{"lat": lat, "lon": lon} for lat, lon in waypoints],
        })

    def push_zone(
        self,
        polygon: list[tuple[float, float]],
        name: str,
        color: str = "red",
    ) -> None:
        self._post(_TZ_ENDPOINTS["zone"], {
            "name": name,
            "color": color,
            "polygon": [{"lat": lat, "lon": lon} for lat, lon in polygon],
        })


# ── Internal helpers ───────────────────────────────────────────────────────────

def _geojson_line_to_waypoints(feature: dict) -> list[tuple[float, float]]:
    """Extract (lat, lon) tuples from a LineString GeoJSON feature."""
    coords = feature.get("geometry", {}).get("coordinates", [])
    return [(c[1], c[0]) for c in coords if len(c) >= 2]


def _geojson_polygon_to_ring(feature: dict) -> list[tuple[float, float]]:
    """Extract outer ring (lat, lon) tuples from a Polygon GeoJSON feature."""
    rings = feature.get("geometry", {}).get("coordinates", [[]])
    return [(c[1], c[0]) for c in rings[0] if len(c) >= 2]


def _do_push(
    client: TimeZeroClient,
    drift_id: str,
    origin_lat: float,
    origin_lon: float,
    result: Any,
    label: str,
) -> None:
    short_id = drift_id[:8]

    client.push_mark(origin_lat, origin_lon, f"{label} DATUM [{short_id}]", color="red")

    waypoints = _geojson_line_to_waypoints(result.trajectory)
    if waypoints:
        client.push_route(waypoints, f"{label} Trajectory [{short_id}]")

    for cone_attr, (cone_label, _) in _CONE_COLORS.items():
        feature = getattr(result, f"cone_{cone_attr}", None)
        if feature is None:
            continue
        ring = _geojson_polygon_to_ring(feature)
        if ring:
            client.push_zone(ring, f"{label} {cone_label} [{short_id}]", color=cone_attr)


def _build_kml(
    drift_id: str,
    origin_lat: float,
    origin_lon: float,
    result: Any,
) -> str:
    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = f"Drift {drift_id[:8]}"

    def _style(sid: str, color: str) -> None:
        st = ET.SubElement(doc, "Style", id=sid)
        ps = ET.SubElement(st, "PolyStyle")
        ET.SubElement(ps, "color").text = color
        ET.SubElement(ps, "fill").text = "1"
        ET.SubElement(ps, "outline").text = "1"
        ls = ET.SubElement(st, "LineStyle")
        ET.SubElement(ls, "color").text = color
        ET.SubElement(ls, "width").text = "2"

    _style("amber", "7f00a5ff")
    _style("orange_", "7f0055ff")
    _style("red_", "7f0000ff")

    # Datum placemark
    pm = ET.SubElement(doc, "Placemark")
    ET.SubElement(pm, "name").text = "DATUM"
    pt = ET.SubElement(pm, "Point")
    ET.SubElement(pt, "coordinates").text = f"{origin_lon},{origin_lat},0"

    # Trajectory
    waypoints = _geojson_line_to_waypoints(result.trajectory)
    if waypoints:
        pm = ET.SubElement(doc, "Placemark")
        ET.SubElement(pm, "name").text = "Trajectory"
        ls_el = ET.SubElement(pm, "LineString")
        ET.SubElement(ls_el, "coordinates").text = " ".join(
            f"{lon},{lat},0" for lat, lon in waypoints
        )

    # Cones
    style_map = {"6h": "amber", "12h": "orange_", "24h": "red_"}
    for cone_attr, (cone_label, _) in _CONE_COLORS.items():
        feature = getattr(result, f"cone_{cone_attr}", None)
        if feature is None:
            continue
        ring = _geojson_polygon_to_ring(feature)
        if not ring:
            continue
        pm = ET.SubElement(doc, "Placemark")
        ET.SubElement(pm, "name").text = cone_label
        ET.SubElement(pm, "styleUrl").text = f"#{style_map[cone_attr]}"
        poly = ET.SubElement(pm, "Polygon")
        ob = ET.SubElement(poly, "outerBoundaryIs")
        lr = ET.SubElement(ob, "LinearRing")
        ET.SubElement(lr, "coordinates").text = " ".join(
            f"{lon},{lat},0" for lat, lon in ring
        )

    ET.indent(kml)
    return ET.tostring(kml, encoding="unicode", xml_declaration=True)


def _write_kml_fallback(
    drift_id: str,
    origin_lat: float,
    origin_lon: float,
    result: Any,
    export_dir: str | None,
) -> None:
    try:
        out_dir = Path(export_dir) if export_dir else Path(tempfile.gettempdir())
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"drift_{drift_id}.kml"
        path.write_text(_build_kml(drift_id, origin_lat, origin_lon, result), encoding="utf-8")
        logger.info("TimeZero unreachable — KML written to %s", path)
    except Exception as exc:
        logger.warning("KML fallback write failed: %s", exc)


# ── Public API ─────────────────────────────────────────────────────────────────

def push_drift_to_timezero(
    drift_id: str,
    result: Any,
    origin_lat: float,
    origin_lon: float,
    label: str = "Drift",
) -> None:
    """Push a DriftResult to TimeZero Professional, or write a KML fallback."""
    from core.config import config as _cfg

    if not _cfg.TIMEZERO_ENABLED:
        return

    client = TimeZeroClient(
        host=_cfg.TIMEZERO_HOST,
        port=_cfg.TIMEZERO_PORT,
        api_key=_cfg.TIMEZERO_API_KEY,
    )

    if not client.health_check():
        logger.warning("TimeZero not reachable at %s:%d — writing KML fallback",
                       _cfg.TIMEZERO_HOST, _cfg.TIMEZERO_PORT)
        _write_kml_fallback(drift_id, origin_lat, origin_lon, result, _cfg.TIMEZERO_EXPORT_DIR)
        return

    try:
        _do_push(client, drift_id, origin_lat, origin_lon, result, label)
        logger.info("TimeZero push OK — drift %s", drift_id[:8])
    except Exception as exc:
        logger.warning("TimeZero push failed (%s) — writing KML fallback", exc)
        _write_kml_fallback(drift_id, origin_lat, origin_lon, result, _cfg.TIMEZERO_EXPORT_DIR)


def timezero_health() -> dict[str, Any]:
    """Return bridge status — suitable for an API health endpoint."""
    from core.config import config as _cfg

    enabled = _cfg.TIMEZERO_ENABLED
    if not enabled:
        return {"enabled": False, "reachable": None, "host": _cfg.TIMEZERO_HOST,
                "port": _cfg.TIMEZERO_PORT}

    client = TimeZeroClient(_cfg.TIMEZERO_HOST, _cfg.TIMEZERO_PORT, _cfg.TIMEZERO_API_KEY)
    reachable = client.health_check()
    return {
        "enabled": True,
        "reachable": reachable,
        "host": _cfg.TIMEZERO_HOST,
        "port": _cfg.TIMEZERO_PORT,
    }
