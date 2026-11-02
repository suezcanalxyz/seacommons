# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed, staging-only review bundle for one attack and its follow-up notices.

A later wreck notice, prosecutor investigation, and AIS slowdown may belong
to the same vessel without constituting new attacks or independent attack
witnesses. This module only composes already validated staging previews;
it cannot query/write a database, publish, schedule work or change geometry.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import re
from datetime import datetime, date, timedelta, timezone
from math import asin, cos, isfinite, radians, sin, sqrt

from core.intel.maritime_attack_correlation import _name, _valid_imo, _valid_mmsi


_CONTEXT_KINDS = frozenset({"investigation", "rescue", "navigational_hazard", "damage_assessment"})


def _clock(value: object) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("case_review_requires_exact_event_clock")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("case_review_requires_exact_event_clock") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("case_review_requires_exact_event_clock")
    return result.astimezone(timezone.utc)


def _preview_boundary(preview: Mapping[str, object]) -> None:
    if (
        preview.get("staging_only") is not True
        or preview.get("publication_allowed") is not False
        or preview.get("independent_origins_verified") != 0
        or preview.get("ais_as_attack_proof") is not False
        or not isinstance(preview.get("canonical_observation_id"), str)
        or not preview["canonical_observation_id"]
        or not isinstance(preview.get("original_report_id"), str)
        or not preview["original_report_id"]
    ):
        raise ValueError("untrusted_or_publishable_staging_preview")


def _source_location(value: object) -> dict[str, object] | None:
    """Validate and fingerprint source-reported geometry, never infer an attack site.

    This is a derived review snapshot, not authentication of the original
    bulletin. A changed location must change the evidence-ledger fingerprint.
    """
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {
        "lat", "lon", "role", "uncertainty_km"
    }:
        raise ValueError("invalid_source_reported_location")
    lat, lon, uncertainty = value["lat"], value["lon"], value["uncertainty_km"]
    if (type(lat) not in (float, int) or type(lon) not in (float, int)
            or not isfinite(lat) or not isfinite(lon)
            or not -90 <= lat <= 90 or not -180 <= lon <= 180):
        raise ValueError("invalid_source_reported_location")
    if (uncertainty is not None and
            (type(uncertainty) not in (float, int)
             or not isfinite(uncertainty) or uncertainty < 0)):
        raise ValueError("invalid_source_location_uncertainty")
    if value["role"] not in {
        "incident_site", "hazard_position", "last_reported_position", "anchorage"
    }:
        raise ValueError("invalid_source_location_role")
    return {
        "lat": float(lat), "lon": float(lon), "role": value["role"],
        "uncertainty_km": float(uncertainty) if uncertainty is not None else None,
    }


def _evidence_ledger_entry(preview: Mapping[str, object], *, role: str) -> dict[str, object]:
    """Preserve source-level clocks and rights without claiming corroboration.

    The ledger digest below fingerprints this *derived staging snapshot*.
    It is not a signature, original-document hash or evidence attestation.
    """
    _preview_boundary(preview)
    receipt = _clock(preview.get("received_at_utc"))
    checked = preview.get("source_checked_on_utc")
    if not isinstance(checked, str):
        raise ValueError("missing_source_check_date")
    try:
        checked_day = date.fromisoformat(checked)
    except ValueError as exc:
        raise ValueError("invalid_source_check_date") from exc
    if checked_day > receipt.date():
        raise ValueError("source_check_after_receipt")
    source_url = preview.get("source_url")
    if not isinstance(source_url, str) or not source_url.startswith("https://"):
        raise ValueError("invalid_review_source_url")
    rights = preview.get("source_rights")
    if not isinstance(rights, str) or not rights.strip():
        raise ValueError("missing_review_source_rights")
    metadata_digest = preview.get("raw_payload_hash")
    original_digest = preview.get("source_document_sha256")
    if not isinstance(metadata_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", metadata_digest):
        raise ValueError("invalid_canonical_metadata_digest")
    if original_digest is not None and (
        not isinstance(original_digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", original_digest)
    ):
        raise ValueError("invalid_original_document_digest")
    event_clock = preview.get("occurred_at_utc")
    publication_clock = preview.get("published_at_utc")
    for field, stamp in (("event", event_clock), ("publication", publication_clock)):
        if stamp is not None and _clock(stamp) > receipt:
            raise ValueError(f"{field}_after_canonical_receipt")
    for field in ("event_date", "publication_date"):
        stamp = preview.get(field)
        if stamp is not None:
            if not isinstance(stamp, str):
                raise ValueError("invalid_source_day")
            try:
                source_day = date.fromisoformat(stamp)
            except ValueError as exc:
                raise ValueError("invalid_source_day") from exc
            if source_day > receipt.date():
                raise ValueError("source_day_after_receipt")
    return {
        "role": role,
        "canonical_observation_id": preview["canonical_observation_id"],
        "original_report_id": preview["original_report_id"],
        "source_url": source_url,
        "source_kind": preview.get("source_kind"),
        "source_rights": rights,
        "vessel_name_as_reported": preview.get("vessel_name_as_reported"),
        "vessel_imo_as_reported": preview.get("vessel_imo_as_reported"),
        "vessel_mmsi_as_reported": preview.get("vessel_mmsi_as_reported"),
        "reported_location": _source_location(preview.get("reported_location")),
        "source_checked_on_utc": checked,
        "original_document_sha256": original_digest,
        "original_document_digest_available": original_digest is not None,
        "canonical_metadata_sha256": metadata_digest,
        "occurred_at_utc": event_clock,
        "event_date": preview.get("event_date"),
        "event_time_precision": preview.get("event_time_precision"),
        "reported_time_uncertainty_minutes": preview.get("reported_time_uncertainty_minutes"),
        "published_at_utc": publication_clock,
        "publication_date": preview.get("publication_date"),
        "received_at_utc": receipt.isoformat(),
        "independent_attack_witness_verified": False,
        "republication_approved": False,
        "publication_allowed": False,
    }


def _nominal_distance_km(a: Mapping[str, object], b: Mapping[str, object]) -> float:
    """Coordinate-only distance; NOT a route, site fix or error-bounded match."""
    coords = (a.get("lat"), a.get("lon"), b.get("lat"), b.get("lon"))
    if any(type(v) not in (float, int) or not isfinite(v) for v in coords):
        raise ValueError("invalid_contextual_position")
    lat1, lon1, lat2, lon2 = map(float, coords)
    if any(abs(lat) > 90 for lat in (lat1, lat2)) or any(
        abs(lon) > 180 for lon in (lon1, lon2)
    ):
        raise ValueError("invalid_contextual_position")
    phi1, phi2 = radians(lat1), radians(lat2)
    delta_phi, delta_lon = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lon / 2) ** 2
    return round(2 * 6371.0088 * asin(sqrt(min(1.0, max(0.0, h)))), 2)


def build_staging_attack_case_review(
    attack_preview: Mapping[str, object],
    context_previews: Sequence[Mapping[str, object]],
    *,
    ais_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Link reviewed context to ONE attack candidate, never corroborate it.

    A NAVWARN sinking position is a later *hazard* coordinate, not the attack
    location. A named official IMO in that follow-up can aid identity review,
    but it cannot certify an MMSI or an independent attack witness.
    """
    if not isinstance(attack_preview, Mapping):
        raise ValueError("attack_staging_preview_required")
    _preview_boundary(attack_preview)
    kind = attack_preview.get("source_kind")
    expected_type = {"attack": "maritime_attack", "piracy": "piracy"}.get(kind)
    if (expected_type is None
            or attack_preview.get("review_status") != "candidate"
            or attack_preview.get("proposed_incident_type") != expected_type):
        raise ValueError("attack_candidate_required")
    name = attack_preview.get("vessel_name_as_reported")
    if not isinstance(name, str) or not _name(name):
        raise ValueError("named_attack_vessel_required")
    attack_at = _clock(attack_preview.get("occurred_at_utc"))
    if not isinstance(context_previews, Sequence) or isinstance(
        context_previews, (str, bytes)
    ) or len(context_previews) > 16:
        raise ValueError("unbounded_context_preview_batch")

    seen = {attack_preview["canonical_observation_id"]}
    seen_reports = {attack_preview["original_report_id"]}
    official_imos: set[str] = set()
    if attack_preview.get("vessel_imo_as_reported"):
        imo = attack_preview["vessel_imo_as_reported"]
        if not isinstance(imo, str) or not _valid_imo(imo):
            raise ValueError("invalid_original_imo")
        official_imos.add(imo)

    followups: list[dict[str, object]] = []
    for preview in context_previews:
        if not isinstance(preview, Mapping):
            raise ValueError("invalid_context_preview")
        _preview_boundary(preview)
        if (preview.get("review_status") != "context_only"
                or preview.get("proposed_incident_type") is not None
                or preview.get("source_kind") not in _CONTEXT_KINDS):
            raise ValueError("attack_witness_must_not_be_followup_context")
        if (preview["canonical_observation_id"] in seen
                or preview["original_report_id"] in seen_reports):
            raise ValueError("duplicate_case_source")
        seen.add(preview["canonical_observation_id"])
        seen_reports.add(preview["original_report_id"])
        reported_name = preview.get("vessel_name_as_reported")
        if not isinstance(reported_name, str) or _name(reported_name) != _name(name):
            raise ValueError("context_vessel_identity_conflict")
        imo = preview.get("vessel_imo_as_reported")
        if imo:
            if not isinstance(imo, str) or not _valid_imo(imo):
                raise ValueError("invalid_context_imo")
            official_imos.add(imo)
        context_mmsi = preview.get("vessel_mmsi_as_reported")
        if context_mmsi and (not isinstance(context_mmsi, str) or not _valid_mmsi(context_mmsi)):
            raise ValueError("invalid_context_mmsi")
        context_at = preview.get("occurred_at_utc")
        context_kind = preview["source_kind"]
        if context_kind == "navigational_hazard":
            hazard_at = _clock(context_at)
            if not attack_at < hazard_at <= attack_at + timedelta(days=30):
                raise ValueError("hazard_not_a_later_followup")
            reported_location = preview.get("reported_location")
            if reported_location is not None and (
                not isinstance(reported_location, Mapping)
                or reported_location.get("role") not in {"hazard_position", "last_reported_position"}
            ):
                raise ValueError("hazard_location_cannot_be_attack_site")
            offset_minutes = round((hazard_at - attack_at).total_seconds() / 60, 3)
        else:
            # Investigation and rescue reports are documentary context.
            # Their day-only clocks never become minute-precision events.
            published = preview.get("publication_date")
            if published is None:
                raise ValueError("context_publication_date_required")
            try:
                issue_day = date.fromisoformat(published)
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid_context_publication_date") from exc
            if not attack_at.date() <= issue_day <= (attack_at + timedelta(days=30)).date():
                raise ValueError("context_not_in_followup_window")
            event_day = preview.get("event_date")
            if event_day is not None:
                try:
                    day = date.fromisoformat(event_day)
                except (TypeError, ValueError) as exc:
                    raise ValueError("invalid_context_event_date") from exc
                if not attack_at.date() <= day <= issue_day:
                    raise ValueError("context_event_not_after_attack")
            if context_at is not None:
                exact_context_at = _clock(context_at)
                if not attack_at <= exact_context_at:
                    raise ValueError("context_exact_clock_precedes_attack")
                if exact_context_at.date() > issue_day:
                    raise ValueError("context_exact_clock_after_publication")
                if event_day is not None and exact_context_at.date() != day:
                    raise ValueError("context_exact_clock_conflicts_with_event_day")
            reported_location = preview.get("reported_location")
            if reported_location is not None and (
                not isinstance(reported_location, Mapping)
                or reported_location.get("role") == "incident_site"
            ):
                raise ValueError("followup_location_cannot_be_attack_site")
            offset_minutes = None
        followups.append({
            "original_report_id": preview["original_report_id"],
            "source_url": preview.get("source_url"),
            "source_kind": context_kind,
            "occurred_at_utc": context_at,
            "publication_date": preview.get("publication_date"),
            "reported_location": dict(reported_location) if reported_location else None,
            "minutes_after_attack": offset_minutes,
            "imo_as_reported": imo or None,
            "role": (
                "later_hazard_not_attack" if context_kind == "navigational_hazard"
                else "rescue_not_attack_witness" if context_kind == "rescue"
                else "damage_assessment_not_attack_witness" if context_kind == "damage_assessment"
                else "investigation_not_attack_witness"
            ),
            "attack_witness": False,
        })
    if len(official_imos) > 1:
        raise ValueError("conflicting_official_imo_sources")

    crosswalk = None
    ais_summary = None
    if ais_context is not None:
        if not isinstance(ais_context, Mapping) or (
            ais_context.get("staging_only") is not True
            or ais_context.get("publication_allowed") is not False
            or ais_context.get("ais_as_attack_proof") is not False
            or ais_context.get("independent_origins_verified") != 0
            or ais_context.get("preview_id") != attack_preview.get("preview_id")
            or ais_context.get("canonical_observation_id")
                != attack_preview["canonical_observation_id"]
        ):
            raise ValueError("foreign_or_publishable_ais_context")
        crosswalk = ais_context.get("crosswalk")
        if not isinstance(crosswalk, Mapping):
            raise ValueError("missing_ais_crosswalk")
        if (not isinstance(crosswalk.get("imo"), str)
                or not isinstance(crosswalk.get("mmsi"), str)
                or not _valid_imo(crosswalk["imo"])
                or not _valid_mmsi(crosswalk["mmsi"])
                or not isinstance(crosswalk.get("name"), str)
                or _name(crosswalk["name"]) != _name(name)
                or crosswalk.get("verification_status") != "external_identity_requires_review"):
            raise ValueError("unreviewed_or_conflicting_ais_crosswalk")
        if official_imos and crosswalk["imo"] not in official_imos:
            raise ValueError("official_imo_conflicts_with_ais_crosswalk")
        for preview in (attack_preview, *context_previews):
            asserted = preview.get("vessel_mmsi_as_reported")
            if asserted and asserted != crosswalk["mmsi"]:
                raise ValueError("original_mmsi_conflicts_with_ais_crosswalk")
        ais_summary = {
            "ais_sampling_gap_minutes": ais_context.get("ais_sampling_gap_minutes"),
            "ais_coverage_gap_signal": ais_context.get("ais_coverage_gap_signal"),
            "sudden_stop_signal": ais_context.get("sudden_stop_signal"),
            "receipt_latency_status": ais_context.get("receipt_latency_status"),
            "nearest_before": ais_context.get("nearest_before"),
            "nearest_after": ais_context.get("nearest_after"),
            "ais_as_attack_proof": False,
        }

    # Nominal spatial comparison is permitted only for a later hazard and
    # a dated AIS vessel fix. Neither point becomes the attack geometry.
    # With no stated source uncertainty, no distance-based corroboration
    # or inferred vessel path is possible.
    if ais_context is not None:
        last_ais = ais_context.get("nearest_after")
        if isinstance(last_ais, Mapping):
            last_at = _clock(last_ais.get("observed_at_utc"))
            for followup in followups:
                if (followup["source_kind"] == "navigational_hazard"
                        and followup["reported_location"] is not None
                        and followup["occurred_at_utc"] is not None):
                    hazard_at = _clock(followup["occurred_at_utc"])
                    if last_at <= hazard_at:
                        followup["ais_to_hazard_nominal_context"] = {
                            "nominal_separation_km": _nominal_distance_km(
                                last_ais, followup["reported_location"]
                            ),
                            "elapsed_hours": round(
                                (hazard_at - last_at).total_seconds() / 3600, 3
                            ),
                            "uncertainty_status": "not_quantified",
                            "route_or_attack_site_inferred": False,
                            "independent_attack_witness": False,
                        }
                    else:
                        followup["ais_to_hazard_nominal_context"] = None

    attack_location = attack_preview.get("reported_location")
    if attack_location is not None and (
        not isinstance(attack_location, Mapping)
        or attack_location.get("role") != "incident_site"
    ):
        attack_location = None
    blockers = list(attack_preview.get("review_blockers") or [])
    blockers.extend(["followup_not_independent_attack_witness", "manual_case_review_required"])
    if official_imos:
        blockers.append("official_followup_imo_requires_review")
    if crosswalk is not None:
        blockers.append("external_mmsi_crosswalk_requires_review")
    if any(f["source_kind"] == "navigational_hazard" for f in followups):
        blockers.append("wreck_or_hazard_site_not_attack_site")

    # Keep the complete original-source chronology in a bounded, deterministic
    # staging review ledger. This is an audit snapshot, not an evidence signature.
    ledger = sorted(
        [_evidence_ledger_entry(attack_preview, role="attack_candidate")] +
        [_evidence_ledger_entry(preview, role="followup_context")
         for preview in context_previews],
        key=lambda item: (item["original_report_id"], item["canonical_observation_id"]),
    )
    ledger_snapshot_sha256 = hashlib.sha256(
        json.dumps(ledger, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    return {
        "source_evidence_ledger": ledger,
        "evidence_ledger_snapshot_sha256": ledger_snapshot_sha256,
        "evidence_ledger_digest_is_original_document_proof": False,
        "case_review_id": "staging-case-review:" + attack_preview["canonical_observation_id"],
        "attack_observation_id": attack_preview["canonical_observation_id"],
        "attack_report_id": attack_preview["original_report_id"],
        "attack_source_url": attack_preview.get("source_url"),
        "attack_at_utc": attack_at.isoformat(),
        "proposed_incident_type": expected_type,
        "review_color": attack_preview.get("review_color"),
        "attack_reported_location": dict(attack_location) if attack_location else None,
        "vessel_name_as_reported": name,
        "official_imo_from_documents": next(iter(official_imos), None),
        "external_mmsi_proposed": crosswalk["mmsi"] if crosswalk else None,
        "identity_status": "requires_manual_review",
        "followups": sorted(followups, key=lambda item: item["original_report_id"]),
        "ais_context": ais_summary,
        "review_blockers": sorted(set(blockers)),
        "independent_origins_verified": 0,
        "ais_as_attack_proof": False,
        "publication_allowed": False,
        "staging_only": True,
    }
