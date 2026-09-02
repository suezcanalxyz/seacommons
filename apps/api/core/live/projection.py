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
from core.domain.visual_category import visual_category_fields
from core.intel import lifecycle
from core.intel.public_geometry import public_geometry_and_precision
from core.intel.public_policy import (
    is_blocked_source,
    is_explicitly_private,
    public_maritime_domains,
)
from core.intel.store import IntelEvent

logger = logging.getLogger(__name__)

_PUBLIC_INTEL_TYPES = frozenset({"distress", "twitter", "mastodon", "ngo_activity"})
# OSINT context types that may appear on the public map when their maritime
# compartment is allow-listed (PUBLIC_MARITIME_DOMAINS). A sanctions / grey-zone
# signal never surfaces on the default (sar, piracy) posture — only the SAR /
# safety / environmental context does.
# ais_spike (routine loiter / stop clusters) is deliberately excluded: it is
# high-volume and low-signal, and would swamp the public feed. Only the
# meaningful AIS derivative — ais_anomaly (spoofing / dark-zone / impossible
# speed) — and the fused alert it may feed are eligible.
_PUBLIC_CONTEXT_TYPES = frozenset(
    {"news", "bluesky", "gdacs", "vessel_incident", "iom_incident",
     "ais_anomaly", "correlated_alert", "oil_spill",
     # vessel_identity (sanctions/identity findings) and dark_candidate
     # (satellite-vs-AIS mismatch) are Security-mode content -- eligible
     # here, actually reachable only when mode=security opens their domain
     # (sanctions/grey_zone) via domains_for_mode(). Humanitarian mode's
     # allow-list never includes those domains, so this addition changes
     # nothing for the existing default feed.
     "vessel_identity", "dark_candidate"}
)
# Types SeaCommons computes from telemetry (AIS, sensor fusion) rather than
# scrapes — they carry no source_policy but are safe to surface, still subject
# to the domain + geometry gates below.
_SEACOMMONS_DERIVED_TYPES = frozenset(
    {"ais_anomaly", "correlated_alert", "vessel_incident", "vessel_identity", "dark_candidate"}
)
# GDACS event types worth showing on a maritime SAR map (TC cyclone, EQ
# earthquake / tsunami, FL flood, VO volcano) — excludes WF wildfire, DR drought.
_MARITIME_GDACS_TYPES = frozenset({"TC", "EQ", "FL", "VO"})
_PUBLIC_METADATA = frozenset(
    {
        "category",
        "coordinate_review_status",
        "coordinate_source",
        "country",
        "dead",
        "distress_classification",
        "drift_status",
        "drift_job_id",
        "first_source_seen_at",
        "incident_id",
        "is_distress",
        "maritime_domain",
        "alert_type",
        "confidence",
        "contributing_sources",
        "cluster_id",
        "anomaly_type",
        "ais_nav_status_kind",
        "anomaly_confidence",
        "confidence_v2",
        "sanctions_matched",
        "detection_reason",
        "detail",
        "drift_eligible",
        "drift_event_id",
        "drift_vessel_type",
        "episode_update_count",
        "first_observed_at",
        "in_jamming_zone",
        "infrastructure",
        "jamming_score",
        "last_observed_at",
        "loiter_minutes",
        "observed_track",
        "vessel_name",
        "imo",
        "ship_type",
        "flag",
        "spike_type",
        "last_source_seen_at",
        "location_uncertainty_m",
        "location_status",
        "ocr_queue_state",
        "media_transport",
        "humanitarian_case_id",
        "humanitarian_case_type",
        "humanitarian_status",
        "people_reported",
        "people_precision",
        "verification_level",
        "source_count",
        "ocr_engine",
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


def _public_intel_feature(
    event: IntelEvent, *, allowed_domains: frozenset[str] | None = None
) -> dict[str, Any] | None:
    """Convert an internal event to the stable public signal contract.

    allowed_domains defaults to the humanitarian posture (PUBLIC_MARITIME_
    DOMAINS, e.g. sar/piracy/safety) for full backward compatibility with
    every existing caller. Live-mode callers (see feed.py's `mode` param)
    pass a different set to open sanctions/grey_zone content instead,
    without touching the default behaviour.
    """
    if (
        event.type == "sar_model"
        or (event.title or "").strip().lower() == "computed sar drift product"
    ):
        # Model outputs belong to Play/Engine, never to the received-signal feed.
        return None
    if event.type == "news" and event.verification_status() not in {
        VerificationStatus.MULTI_SOURCE_CORROBORATED.value,
        "confirmed",
    }:
        # A published URL proves provenance, not the claims in the article.
        # Live only carries news with an explicit corroboration decision.
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
    domains = allowed_domains if allowed_domains is not None else public_maritime_domains()
    resolved_domain = str(event.maritime_domain() or "sar").strip().lower()
    domain_public = resolved_domain in domains
    is_derived = event.type in _SEACOMMONS_DERIVED_TYPES
    linked_mmsi = str(event.linked_mmsi or event.metadata.get("mmsi") or "").strip()
    if (
        event.type == "correlated_alert"
        and event.metadata.get("alert_type") in {"infra_proximity", "infrastructure_threat"}
        and not (len(linked_mmsi) == 9 and linked_mmsi.isdigit())
    ):
        # Anonymous GFW loiter detections cannot support professional vessel
        # identity or an AIS trajectory. Keep them as operator research cues,
        # never present them as public vessel cases.
        return None
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
    # Feed-volume filter for non-operational OSINT *chatter* — secondary news,
    # social posts, generic GDACS notifications. It reaches the public map only
    # when explicitly published or multi-source corroborated. This is a volume
    # control on secondary reporting, NOT a risk score on maritime
    # intelligence: SeaCommons classifies by category, it does not score
    # (product policy §4). SeaCommons-derived context (ais_anomaly, vessel
    # identity, dark candidate, oil spill, IOM, vessel incident) is the signal
    # itself and passes on its category + domain + type gates alone.
    if (
        event.type in {"news", "bluesky", "gdacs"}
        and publication != PublicationStatus.PUBLISHED.value
        and event.verification_status() not in {
            VerificationStatus.MULTI_SOURCE_CORROBORATED.value,
            "confirmed",
        }
    ):
        return None
    # GDACS: only genuinely SAR-relevant natural hazards (cyclone, coastal
    # quake / tsunami, flood, volcano) — never wildfires / droughts inland.
    if event.type == "gdacs" and str(
        event.metadata.get("gdacs_event_type") or ""
    ).upper() not in _MARITIME_GDACS_TYPES:
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
    # Always publish the resolved compartment. This also prevents a legacy raw
    # metadata value from overwriting a compatibility reclassification below.
    metadata["maritime_domain"] = resolved_domain
    if (
        resolved_domain == "sar"
        and event.metadata.get("is_distress")
        and event.metadata.get("tweet_id")
        and "humanitarian_case_id" not in metadata
    ):
        from core.intel.humanitarian import humanitarian_case_metadata

        metadata.update(humanitarian_case_metadata(
            event.text,
            incident_id=str(event.metadata["tweet_id"]),
            source=str(event.metadata.get("tracked_account") or event.source),
            distress=True,
            resolved=(
                str(event.metadata.get("report_kind") or "") == "resolved"
                or lifecycle.has_own_reply_resolution(event)
            ),
        ))
    if event.is_vessel_mobility_incident():
        # Legacy fusion alerts pre-date the dedicated vessel-incident monitor.
        # Give them the same contract so they coalesce by MMSI and gain the
        # observed AIS path plus an optional cargo-vessel drift forecast.
        metadata.setdefault("ais_nav_status_kind", "not_under_command")
        metadata.setdefault("drift_eligible", True)
        metadata.setdefault("drift_event_id", f"intel:{event.id}")
        metadata.setdefault("drift_vessel_type", "cargo")
    # MMSI/IMO/name/flag are professional vessel identifiers broadcast in AIS
    # or drawn from the local public registry.  Keeping them on every linked
    # alert is what lets the client join updates into one vessel episode.
    mmsi = linked_mmsi
    if len(mmsi) == 9 and mmsi.isdigit():
        metadata["linked_mmsi"] = mmsi
        metadata["mmsi"] = mmsi
        try:
            from core.vessels.registry import registry
            from core.mda.identity import mmsi_flag

            vessel = (getattr(registry, "_cache", {}) or {}).get(mmsi, {})
            identity_fields = {
                "vessel_name": vessel.get("ship_name"),
                "imo": vessel.get("imo"),
                "ship_type": vessel.get("ship_type"),
                "flag": vessel.get("flag") or mmsi_flag(mmsi),
            }
            for key, value in identity_fields.items():
                if value not in (None, "") and key not in metadata:
                    metadata[key] = value
        except Exception:  # pragma: no cover - registry enrichment is best effort
            pass
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
    # SeaCommons-derived MDA events (spoofing, sanctions, vessel incidents)
    # never went through core.intel.lifecycle's distress state machine --
    # they had no incident_lifecycle at all and sat "active" forever, even
    # a week later. There's no reply-thread to detect resolution from (no
    # human posts an update when a vessel resumes normal AIS behaviour), so
    # this only tracks staleness, same ARCHIVE_AFTER_HOURS threshold as
    # distress markers: unrefreshed past that window is no longer worth
    # highlighting as current, though it stays visible and searchable.
    lifecycle_state = None
    explicit_lifecycle = str(event.metadata.get("incident_lifecycle") or "").lower()
    if explicit_lifecycle in {"active", "resolved", "needs_review", "archived"}:
        lifecycle_state = explicit_lifecycle
    elif is_derived:
        observed = lifecycle.parse_utc(event.timestamp_utc)
        if observed is not None:
            age_hours = (datetime.now(UTC) - observed).total_seconds() / 3600
            lifecycle_state = (
                "archived" if age_hours >= lifecycle.ARCHIVE_AFTER_HOURS else "active"
            )

    geometry, location_precision = public_geometry_and_precision(event)
    # Canonical semantic visual taxonomy. Colour/identity is a pure function of
    # category — never severity, OCR confidence or lifecycle. Alarm Phone is
    # always `humanitarian_alarm_phone` (red).
    category = visual_category_fields(
        source=event.source,
        event_type=event.type,
        maritime_domain=resolved_domain,
        humanitarian_case_type=metadata.get("humanitarian_case_type"),
        metadata=event.metadata,
    )
    feature = {
        "type": "Feature",
        "id": f"intel:{event.id}",
        "geometry": geometry,
        "properties": {
            "schema": LIVE_SIGNAL_SCHEMA,
            "id": f"intel:{event.id}",
            "type": event.type,
            **category,
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
            **({"incident_lifecycle": lifecycle_state} if lifecycle_state else {}),
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
    category: dict[str, str],
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
            # Drift colour inherits its origin signal's category. No severity.
            "origin_category": category.get("visual_category"),
            "visual_category": category.get("visual_category"),
            "visual_color": category.get("visual_color"),
            "category_label": category.get("category_label"),
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
        and metadata.get("forcing_quality") in {
            "spatiotemporal",  # persisted legacy runs
            "observed-spatiotemporal",
        }
        and metadata.get("operational_use") is True
        and len(coordinates) >= 2
        and len(properties.get("timestamps_utc") or []) == len(coordinates)
        and len(properties.get("speed_ms") or []) == len(coordinates)
    )
