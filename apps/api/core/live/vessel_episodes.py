# SPDX-License-Identifier: AGPL-3.0-or-later
"""Collapse vessel-centric Live signals into stable, updateable episodes."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any

_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_SANCTIONS_TYPES = {"sdn_match", "sanctioned_vessel"}


def _timestamp(value: Any) -> float:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return 0.0


def _mmsi(feature: dict[str, Any]) -> str:
    properties = feature.get("properties") or {}
    value = str(properties.get("linked_mmsi") or properties.get("mmsi") or "").strip()
    return value if len(value) == 9 and value.isdigit() else ""


def _point(feature: dict[str, Any]) -> list[float] | None:
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates")
    if geometry.get("type") != "Point" or not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    try:
        return [float(coordinates[0]), float(coordinates[1])]
    except (TypeError, ValueError):
        return None


def _track_points(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for feature in features:
        properties = feature.get("properties") or {}
        for raw in properties.get("observed_track") or []:
            if not isinstance(raw, dict):
                continue
            try:
                lon, lat = float(raw["lon"]), float(raw["lat"])
            except (KeyError, TypeError, ValueError):
                continue
            points.append(
                {
                    "lon": round(lon, 6),
                    "lat": round(lat, 6),
                    "ts": raw.get("ts") or properties.get("timestamp_utc"),
                    **({"sog": raw.get("sog")} if raw.get("sog") is not None else {}),
                    **(
                        {"nav_status": raw.get("nav_status")}
                        if raw.get("nav_status") is not None
                        else {}
                    ),
                }
            )
        point = _point(feature)
        if point:
            points.append(
                {
                    "lon": round(point[0], 6),
                    "lat": round(point[1], 6),
                    "ts": properties.get("timestamp_utc"),
                }
            )

    points.sort(key=lambda item: _timestamp(item.get("ts")))
    unique: list[dict[str, Any]] = []
    seen: set[tuple[float, float, str]] = set()
    for point in points:
        key = (point["lon"], point["lat"], str(point.get("ts") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(point)
    return unique[-120:]


def coalesce_security_vessel_episodes(
    features: list[dict[str, Any]],
    *,
    track_history: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Return one current marker per MMSI, retaining its evidence timeline.

    Non-vessel signals remain independent.  Sanctions is selected as the
    episode domain only for an actual sanctions match; legacy AIS gaps that
    were stored with ``maritime_domain=sanctions`` are normalised to generic
    maritime-security context here.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    ungrouped: list[dict[str, Any]] = []
    for feature in features:
        mmsi = _mmsi(feature)
        if not mmsi:
            ungrouped.append(feature)
            continue
        grouped.setdefault(mmsi, []).append(feature)

    episodes: list[dict[str, Any]] = []
    for mmsi, items in grouped.items():
        items.sort(key=lambda item: _timestamp((item.get("properties") or {}).get("timestamp_utc")))
        positioned = [item for item in items if _point(item)]
        primary = deepcopy(positioned[-1] if positioned else items[-1])
        props = primary.setdefault("properties", {})
        history_feature = {
            "properties": {"observed_track": (track_history or {}).get(mmsi, [])}
        }
        track = _track_points([*items, history_feature])
        if track:
            latest = track[-1]
            primary["geometry"] = {
                "type": "Point",
                "coordinates": [latest["lon"], latest["lat"]],
            }

        item_props = [item.get("properties") or {} for item in items]
        anomaly_types = sorted(
            {
                str(p.get("anomaly_type") or p.get("ais_nav_status_kind") or "")
                for p in item_props
                if p.get("anomaly_type") or p.get("ais_nav_status_kind")
            }
        )
        has_sanctions_match = any(
            str(p.get("anomaly_type") or "") in _SANCTIONS_TYPES
            or bool(p.get("sanctions_matched"))
            for p in item_props
        )
        most_severe = max(
            (str(p.get("severity") or "low") for p in item_props),
            key=lambda severity: _SEVERITY_RANK.get(severity, 0),
        )
        raw_ids = [str(p.get("id") or "") for p in item_props if p.get("id")]
        update_count = max(
            len(track),
            sum(max(1, int(p.get("episode_update_count") or 1)) for p in item_props),
        )
        drift_source = next(
            (p for p in reversed(item_props) if p.get("drift_eligible")),
            None,
        )
        updates = [
            {
                "id": p.get("id"),
                "timestamp_utc": p.get("timestamp_utc"),
                "type": p.get("type"),
                "anomaly_type": p.get("anomaly_type") or p.get("ais_nav_status_kind"),
                "title": p.get("title"),
                "severity": p.get("severity"),
                "source": p.get("source"),
            }
            for p in reversed(item_props)
        ][:12]
        episode_id = f"vessel-episode:{mmsi}"
        first_signal_at = item_props[0].get("timestamp_utc")
        last_signal_at = item_props[-1].get("timestamp_utc")
        first_observed_at = (
            track[0].get("ts")
            if track and _timestamp(track[0].get("ts")) < _timestamp(first_signal_at)
            else first_signal_at
        )
        last_observed_at = (
            track[-1].get("ts")
            if track and _timestamp(track[-1].get("ts")) > _timestamp(last_signal_at)
            else last_signal_at
        )
        props.update(
            {
                "id": episode_id,
                "episode_id": episode_id,
                "linked_mmsi": mmsi,
                "mmsi": mmsi,
                "severity": most_severe,
                "maritime_domain": "sanctions" if has_sanctions_match else "grey_zone",
                "sanctions_matched": has_sanctions_match,
                "signal_count": len(items),
                "episode_update_count": update_count,
                "first_observed_at": first_observed_at,
                "last_observed_at": last_observed_at,
                "timestamp_utc": last_observed_at,
                "related_signal_ids": raw_ids,
                "alert_types": sorted({str(p.get("type")) for p in item_props if p.get("type")}),
                "anomaly_types": anomaly_types,
                "contributing_sources": sorted(
                    {str(p.get("source")) for p in item_props if p.get("source")}
                ),
                "observed_track": track,
                "track_kind": "observed_ais",
                "track_last_seen": track[-1].get("ts") if track else None,
                "latest_sog": track[-1].get("sog") if track else None,
                "latest_nav_status": track[-1].get("nav_status") if track else None,
                "updates": updates,
                "drift_eligible": bool(drift_source),
                **(
                    {
                        "drift_event_id": drift_source.get("id"),
                        "drift_vessel_type": drift_source.get("drift_vessel_type") or "cargo",
                        "drift_status": drift_source.get("drift_status"),
                        "drift_job_id": drift_source.get("drift_job_id"),
                    }
                    if drift_source
                    else {}
                ),
            }
        )
        # A later normal AIS navigation status is direct evidence that a
        # previous NUC episode ended.  It does not invalidate other anomalies
        # (for example a subsequent reporting gap), so only the incident state
        # and its explanatory note are changed.
        if (
            "not_under_command" in anomaly_types
            and track
            and track[-1].get("nav_status") in {0, 1, 5, 8}
        ):
            props["incident_lifecycle"] = "resolved"
            props["status_note"] = "Latest AIS navigation status returned to normal."
        primary["id"] = episode_id
        episodes.append(primary)

    return ungrouped + episodes


def _distance_nm(a: list[float], b: list[float]) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    h = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 3440.065 * 2 * asin(sqrt(max(0.0, min(1.0, h))))


def add_nearby_humanitarian_context(
    security: list[dict[str, Any]],
    humanitarian: list[dict[str, Any]],
    *,
    radius_nm: float = 20.0,
    window_hours: float = 24.0,
) -> None:
    """Annotate, never merge: proximity is context, not proof of relation."""
    for feature in security:
        origin = _point(feature)
        if not origin:
            continue
        properties = feature.get("properties") or {}
        observed = _timestamp(properties.get("timestamp_utc"))
        nearby: list[dict[str, Any]] = []
        for candidate in humanitarian:
            target = _point(candidate)
            other = candidate.get("properties") or {}
            if not target or abs(observed - _timestamp(other.get("timestamp_utc"))) > window_hours * 3600:
                continue
            distance = _distance_nm(origin, target)
            if distance <= radius_nm:
                nearby.append(
                    {
                        "id": other.get("id"),
                        "title": other.get("title"),
                        "timestamp_utc": other.get("timestamp_utc"),
                        "distance_nm": round(distance, 1),
                    }
                )
        nearby.sort(key=lambda item: item["distance_nm"])
        properties["nearby_humanitarian_count"] = len(nearby)
        properties["nearby_humanitarian"] = nearby[:3]
