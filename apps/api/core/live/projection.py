# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure privacy and geometry projections for the public Live contracts."""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from core.domain.live_contracts import (
    APPROVED_SOURCE_POLICIES,
    LIVE_SIGNAL_SCHEMA,
    LiveSignalKind,
    PublicationStatus,
    Severity,
    SourcePolicy,
    VerificationStatus,
    validate_live_signal,
)
from core.intel.public_geometry import public_geometry_and_precision
from core.intel.public_policy import is_blocked_source, is_explicitly_private, is_public_domain
from core.intel.store import IntelEvent

logger = logging.getLogger(__name__)

_PUBLIC_INTEL_TYPES = frozenset({"distress", "twitter", "mastodon", "ngo_activity"})
# OSINT context types that may appear on the public map when their maritime
# compartment is allow-listed (PUBLIC_MARITIME_DOMAINS). A sanctions / grey-zone
# signal never surfaces on the default (sar, piracy) posture — only the SAR /
# safety / environmental context does.
_PUBLIC_CONTEXT_TYPES = frozenset(
    {"news", "bluesky", "gdacs", "vessel_incident", "iom_incident",
     "ais_spike", "ais_anomaly", "correlated_alert", "oil_spill"}
)
# Types SeaCommons computes from telemetry (AIS, sensor fusion) rather than
# scrapes — they carry no source_policy but are safe to surface, still subject
# to the domain + geometry gates below.
_SEACOMMONS_DERIVED_TYPES = frozenset(
    {"ais_spike", "ais_anomaly", "correlated_alert", "vessel_incident"}
)
_PUBLIC_METADATA = frozenset(
    {
        "category",
        "coordinate_review_status",
        "coordinate_source",
        "country",
        "dead",
        "distress_classification",
        "drift_status",
        "first_source_seen_at",
        "incident_id",
        "is_distress",
        "maritime_domain",
        "alert_type",
        "confidence",
        "contributing_sources",
        "cluster_id",
        "anomaly_type",
        "spike_type",
        "last_source_seen_at",
        "location_uncertainty_m",
        "missing",
        "ocr_attempted",
        "platform",
        "region",
        "source_policy",
        "source_scan_count",
        "repost_count",
        "last_repost_at",
        "area_weather_narrowed",
    }
)


def _safe_public_url(value: str) -> str:
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    return value if parsed.scheme in {"http", "https"} and bool(parsed.netloc) else ""


def _public_intel_feature(event: IntelEvent) -> dict[str, Any] | None:
    """Convert an internal event to the stable public signal contract."""
    if (
        event.type == "sar_model"
        or (event.title or "").strip().lower() == "computed sar drift product"
    ):
        # Model outputs belong to Play/Engine, never to the received-signal feed.
        return None
    publication = str(event.metadata.get("publication_status") or "").lower()
    source_policy = str(event.metadata.get("source_policy") or "").lower()
    if is_blocked_source(event.metadata):
        # Old scraper records may still be persisted; they must never re-enter Live.
        return None
    # Explicit privacy is absolute. An approved transport/source policy may
    # make an otherwise-unlabelled public observation eligible, but it must
    # never override a producer's explicit private decision (RSS/news and
    # direct-message channels rely on this guarantee).
    if is_explicitly_private(event.metadata):
        return None
    domain_public = is_public_domain(event.maritime_domain())
    is_derived = event.type in _SEACOMMONS_DERIVED_TYPES
    if (
        publication != PublicationStatus.PUBLISHED.value
        and source_policy not in APPROVED_SOURCE_POLICIES
        and not (is_derived and domain_public)
    ):
        return None
    type_eligible = (
        event.type in _PUBLIC_INTEL_TYPES
        or (event.type in _PUBLIC_CONTEXT_TYPES and domain_public)
    )
    if not type_eligible and publication != PublicationStatus.PUBLISHED.value:
        return None
    try:
        canonical_source_policy = (
            SourcePolicy(source_policy).value
            if source_policy
            else SourcePolicy.OPERATOR_PUBLISHED.value
        )
    except ValueError:
        logger.warning("Dropping public event with unknown source policy id=%s", event.id)
        return None
    try:
        severity = Severity(event.severity or Severity.LOW.value).value
    except ValueError:
        severity = Severity.LOW.value
    metadata = {key: event.metadata[key] for key in _PUBLIC_METADATA if key in event.metadata}
    # Unlike the event's own `text` (stripped everywhere on public Live,
    # since it may originate from a private WhatsApp/SMS caller who never
    # consented to publication), a thread_reposts `note` only ever comes from
    # the tracked account's OWN public quote/reply to its OWN tweet — already
    # readable by anyone on X. Without it the public "Update" panel would
    # show a link with no indication of what the update actually says, which
    # defeats the point of surfacing it at all.
    thread_reposts = event.metadata.get("thread_reposts")
    if thread_reposts:
        metadata["thread_reposts"] = [
            {
                "tweet_id": r.get("tweet_id"),
                "posted_at": r.get("posted_at"),
                "url": r.get("url"),
                "kind": r.get("kind"),
                "note": r.get("note"),
            }
            for r in thread_reposts
        ]
    geometry, location_precision = public_geometry_and_precision(event)
    feature = {
        "type": "Feature",
        "id": f"intel:{event.id}",
        "geometry": geometry,
        "properties": {
            "schema": LIVE_SIGNAL_SCHEMA,
            "id": f"intel:{event.id}",
            "type": event.type,
            "kind": (
                LiveSignalKind.DISTRESS.value
                if event.tier() == "operational"
                else LiveSignalKind.CONTEXT.value
            ),
            "severity": severity,
            "tier": event.tier(),
            "priority": event.priority(),
            "maritime_domain": event.maritime_domain(),
            "verification_status": event.verification_status(),
            "publication_status": PublicationStatus.PUBLISHED.value,
            "source_policy": canonical_source_policy,
            "title": (event.title or "Maritime signal")[:255],
            # Public Live deliberately excludes raw text and author identifiers.
            "text": "",
            "url": _safe_public_url(event.url),
            "source": (event.source or event.type or "public feed")[:64],
            "timestamp_utc": event.timestamp_utc,
            "source_timestamp_utc": event.timestamp_utc,
            "received_at": event.metadata.get("first_source_seen_at") or event.timestamp_utc,
            "location_precision": location_precision,
            **metadata,
        },
    }
    try:
        return validate_live_signal(feature)
    except ValueError:
        logger.warning("Dropping event that violates the public Live contract id=%s", event.id)
        return None


def _approximate_public_point(signal_id: str, lat: float, lon: float) -> tuple[float, float]:
    """Deterministically displace sensitive inbound coordinates by 0.8-2.5 km."""
    digest = hashlib.blake2s(signal_id.encode(), digest_size=8).digest()
    angle = int.from_bytes(digest[:4], "big") / (2**32) * 2 * math.pi
    radius_m = 800 + int.from_bytes(digest[4:], "big") / (2**32) * 1700
    lat_offset = math.sin(angle) * radius_m / 111_320
    lon_scale = max(0.2, math.cos(math.radians(lat)))
    lon_offset = math.cos(angle) * radius_m / (111_320 * lon_scale)
    return round(lat + lat_offset, 5), round(lon + lon_offset, 5)


def _public_drift_feature(
    feature: dict[str, Any],
    *,
    event_id: str,
    title: str,
    source: str,
    severity: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    return {
        "type": "Feature",
        "geometry": feature.get("geometry"),
        "properties": {
            "type": properties.get("type"),
            "horizon_h": properties.get("horizon_h"),
            "radius_m": properties.get("radius_m"),
            "timestamps_utc": properties.get("timestamps_utc"),
            "speed_ms": properties.get("speed_ms"),
            "speed_kn": properties.get("speed_kn"),
            "course_deg": properties.get("course_deg"),
            "distance_m": properties.get("distance_m"),
            "mean_speed_ms": properties.get("mean_speed_ms"),
            "max_speed_ms": properties.get("max_speed_ms"),
            "sample_interval_s": properties.get("sample_interval_s"),
            "sample_count": properties.get("sample_count"),
            "elapsed_hours": properties.get("elapsed_hours"),
            "estimate_time_utc": properties.get("estimate_time_utc"),
            "trajectory_state": properties.get("trajectory_state"),
            "intel_event_id": event_id,
            "intel_title": title[:80],
            "intel_source": source[:64],
            "intel_severity": severity,
            "auto_drift": True,
            "publication_status": PublicationStatus.PUBLISHED.value,
            "trajectory_kind": "model_forecast",
            "observed_track": False,
            "model": metadata.get("model"),
            "forcing_resolution": metadata.get("forcing_resolution"),
            "forcing_quality": metadata.get("forcing_quality"),
            "verification_status": VerificationStatus.MODELLED_SPATIOTEMPORAL.value,
        },
    }


def _current_trajectory_estimate(
    trajectory: dict[str, Any],
    *,
    event_timestamp: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Interpolate the modelled position at wall-clock time."""
    geometry = trajectory.get("geometry") or {}
    properties = trajectory.get("properties") or {}
    coordinates = geometry.get("coordinates") or []
    timestamps = properties.get("timestamps_utc") or []
    if len(coordinates) < 2 or len(timestamps) != len(coordinates):
        return None
    try:
        parsed_times = [datetime.fromisoformat(str(value)).astimezone(UTC) for value in timestamps]
        event_time = datetime.fromisoformat(event_timestamp)
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=UTC)
        event_time = event_time.astimezone(UTC)
    except (AttributeError, TypeError, ValueError):
        return None
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if current <= parsed_times[0]:
        coordinate = coordinates[0]
        state = "before_model_start"
    elif current >= parsed_times[-1]:
        coordinate = coordinates[-1]
        state = "model_horizon_reached"
    else:
        upper = next(index for index, value in enumerate(parsed_times) if value >= current)
        lower = upper - 1
        span = max(1.0, (parsed_times[upper] - parsed_times[lower]).total_seconds())
        ratio = (current - parsed_times[lower]).total_seconds() / span
        coordinate = [
            float(coordinates[lower][0])
            + (float(coordinates[upper][0]) - float(coordinates[lower][0])) * ratio,
            float(coordinates[lower][1])
            + (float(coordinates[upper][1]) - float(coordinates[lower][1])) * ratio,
        ]
        state = "interpolated"
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": coordinate[:2]},
        "properties": {
            "type": "current_estimate",
            "elapsed_hours": round(max(0.0, (current - event_time).total_seconds() / 3600), 2),
            "estimate_time_utc": current.isoformat(),
            "trajectory_state": state,
        },
    }


def _is_publishable_live_drift(drift: dict[str, Any]) -> bool:
    """Only expose model runs backed by varying forcing, never demo fallbacks."""
    metadata = drift.get("metadata") or {}
    trajectory = drift.get("trajectory") or {}
    properties = trajectory.get("properties") or {}
    coordinates = (trajectory.get("geometry") or {}).get("coordinates") or []
    return bool(
        drift.get("status") == "completed"
        and str(metadata.get("model") or "").startswith("OpenDrift ")
        and metadata.get("forcing_quality") == "spatiotemporal"
        and metadata.get("operational_use") is True
        and len(coordinates) >= 2
        and len(properties.get("timestamps_utc") or []) == len(coordinates)
        and len(properties.get("speed_ms") or []) == len(coordinates)
    )
