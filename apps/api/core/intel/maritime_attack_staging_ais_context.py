# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging-only, read-only AIS context for a reviewed maritime attack preview.

No database access, source collector, scheduler, incident promotion or map
geometry mutation. A crosswalk supplied by a reviewer is *not* proof of vessel
identity; AIS positions and speed changes are *never* attack witnesses.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from math import isclose

from core.intel.maritime_attack_correlation import (
    VesselRef, _canonical_source_url, _name, _utc, _valid_imo,
    _valid_mmsi, ais_fix_from_vessel_track,
)


def _fix_view(fix: object) -> dict[str, object]:
    return {
        "observed_at_utc": fix.observed_at.isoformat(),
        "lat": fix.lat,
        "lon": fix.lon,
        "sog_knots": fix.sog_knots,
        "position_role": "ais_vessel_track_only",
    }


def build_staging_ais_context(
    preview: Mapping[str, object],
    crosswalk: VesselRef,
    tracks: Sequence[object],
    *,
    crosswalk_source_url: str,
) -> dict[str, object]:
    """Join a bounded set of caller-fetched AIS rows to a staging preview.

    The caller must fetch VesselTrackDB rows through a separately authorized
    READ ONLY transaction. This helper cannot open a database connection.
    Crosswalk identifiers are *proposed* external identities, not identities
    asserted by the original bulletin or automatically verified by SeaCommons.
    """
    if not isinstance(preview, Mapping) or preview.get("staging_only") is not True:
        raise ValueError("staging_preview_required")
    if preview.get("publication_allowed") is not False:
        raise ValueError("staging_publication_must_be_disabled")
    if preview.get("review_status") != "candidate" or preview.get("proposed_incident_type") not in {
        "maritime_attack", "piracy"
    }:
        raise ValueError("attack_candidate_preview_required")
    if not isinstance(crosswalk, VesselRef):
        raise ValueError("vessel_crosswalk_required")
    if not _valid_imo(crosswalk.imo) or not _valid_mmsi(crosswalk.mmsi):
        raise ValueError("invalid_crosswalk_imo_or_mmsi")
    reported_name = preview.get("vessel_name_as_reported")
    if not isinstance(reported_name, str) or not reported_name.strip():
        raise ValueError("original_vessel_name_required")
    if _name(reported_name) != _name(crosswalk.name):
        raise ValueError("crosswalk_name_conflict")
    for field, proposed in (
        ("vessel_imo_as_reported", crosswalk.imo),
        ("vessel_mmsi_as_reported", crosswalk.mmsi),
    ):
        asserted = preview.get(field)
        if asserted and asserted != proposed:
            raise ValueError("crosswalk_conflicts_with_original_source")
    source_key = _canonical_source_url(crosswalk_source_url)
    if not source_key:
        raise ValueError("invalid_crosswalk_source_url")
    if not isinstance(tracks, Sequence) or isinstance(tracks, (str, bytes)) or len(tracks) > 256:
        raise ValueError("unbounded_ais_track_batch")

    event_text = preview.get("occurred_at_utc")
    event_at = None
    if event_text is not None:
        if not isinstance(event_text, str):
            raise ValueError("invalid_preview_event_clock")
        try:
            event_at = _utc(datetime.fromisoformat(event_text.replace("Z", "+00:00")))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_preview_event_clock") from exc

    by_time = {}
    for row in tracks:
        fix = ais_fix_from_vessel_track(row)
        if fix.mmsi != crosswalk.mmsi:
            raise ValueError("foreign_mmsi_in_ais_batch")
        previous = by_time.setdefault(fix.observed_at, fix)
        if previous != fix:
            raise ValueError("conflicting_ais_fixes_at_same_timestamp")

    # No event clock means no defensible event-relative AIS window.
    window = sorted(
        (fix for fix in by_time.values()
         if event_at is not None
         and abs((fix.observed_at - event_at).total_seconds()) <= 3 * 3600),
        key=lambda fix: fix.observed_at,
    )
    before = next((fix for fix in reversed(window) if fix.observed_at <= event_at), None) if event_at else None
    after = next((fix for fix in window if fix.observed_at >= event_at), None) if event_at else None
    exact = preview.get("event_time_precision") == "exact"
    gap_minutes = (
        round((after.observed_at - before.observed_at).total_seconds() / 60, 3)
        if before is not None and after is not None else None
    )
    sudden_stop = bool(
        exact and before is not None and after is not None
        and before.sog_knots is not None and after.sog_knots is not None
        and before.sog_knots >= 6 and after.sog_knots <= 2
        and before.sog_knots - after.sog_knots >= 5
        and (event_at - before.observed_at).total_seconds() <= 3600
        and (after.observed_at - event_at).total_seconds() <= 5400
    )
    # Legacy Oracle AIS rows may have received_at copied from ts; this is
    # not an independent measurement of ingestion latency.
    receipt_status = (
        "legacy_equal_event_clock" if window and all(
            isclose((fix.received_at - fix.observed_at).total_seconds(), 0.0, abs_tol=1)
            for fix in window
        ) else "independent_receipt_not_certified"
    )
    return {
        "preview_id": preview.get("preview_id"),
        "canonical_observation_id": preview.get("canonical_observation_id"),
        "crosswalk": {
            "imo": crosswalk.imo,
            "mmsi": crosswalk.mmsi,
            "name": crosswalk.name,
            "source_url": source_key,
            "verification_status": "external_identity_requires_review",
            "asserted_by_original_bulletin": bool(
                preview.get("vessel_imo_as_reported") and preview.get("vessel_mmsi_as_reported")
            ),
        },
        "event_at_utc": event_at.isoformat() if event_at else None,
        "event_time_precision": preview.get("event_time_precision"),
        "ais_fixes_in_6h_window": len(window),
        "nearest_before": _fix_view(before) if before else None,
        "nearest_after": _fix_view(after) if after else None,
        "ais_sampling_gap_minutes": gap_minutes,
        "ais_coverage_gap_signal": bool(exact and gap_minutes is not None and gap_minutes > 30),
        "sudden_stop_signal": sudden_stop,
        "receipt_latency_status": receipt_status,
        "incident_site_from_ais": False,
        "ais_as_attack_proof": False,
        "independent_origins_verified": 0,
        "publication_allowed": False,
        "staging_only": True,
    }
