# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed, metadata-only preview from persisted staging source observations.

Not a PLAY endpoint, public incident, scheduler, collector or promotion path.
A preview is deliberately NOT a canonical MaritimeEpisode and cannot count
a publisher, AIS stop or registry crosswalk as an independent attack witness.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date, datetime, timezone
from math import isclose, isfinite

from core.intel.maritime_attack_staging_manifest import StagingSourceRecord
from core.intel.official_maritime_bulletin import prepare_official_bulletin
from core.domain.visual_category import CATEGORY_COLORS

_PREVIEW_KINDS = {
    "attack": "maritime_attack",
    "piracy": "piracy",
    "suspicious_activity": None,
}


def _canonical_receipt_utc(value: object) -> datetime:
    """Return a timezone-aware UTC receipt; only DB receipts may be naive.

    Reject day-only strings: a receipt is a measured clock, not a calendar
    date. External publication/event clocks always require explicit offsets.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and "T" in value and ":" in value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid_canonical_receipt_clock") from exc
    else:
        raise ValueError("invalid_canonical_receipt_clock")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _same_optional_number(actual: object, expected: object) -> bool:
    """Compare persisted Float columns without accepting invented precision."""
    if expected is None:
        return actual is None
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False
    value = float(actual)
    return isfinite(value) and isclose(value, float(expected), rel_tol=1e-10, abs_tol=1e-7)


def _verify_source_chronology(receipt: datetime, provenance: dict) -> None:
    """Never accept an observation received before a documented source clock.

    Day-only source dates remain dates: they are checked at calendar-day
    granularity and are never silently promoted to midnight timestamps.
    """
    for field in ("occurred_at_utc", "published_at_utc"):
        stamp = provenance[field]
        if stamp is not None:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed > receipt:
                raise ValueError("canonical_receipt_precedes_source_clock")
    for field in ("event_date", "publication_date", "source_checked_on_utc"):
        stamp = provenance[field]
        if stamp is not None and date.fromisoformat(stamp) > receipt.date():
            raise ValueError("canonical_receipt_precedes_source_date")


def build_staging_attack_previews(
    records: Sequence[StagingSourceRecord], observations: Sequence[object],
) -> tuple[dict, ...]:
    """Require an exact one-to-one match against canonical persisted metadata.

    This is for a caller-owned disposable staging transaction only. The
    returned dictionaries deliberately omit incident_type/visual_category,
    which are reserved for canonical, reviewed PLAY episode projections.
    """
    if not 1 <= len(records) <= 32 or len(observations) != len(records):
        raise ValueError("staging_observation_batch_mismatch")
    by_id: dict[str, object] = {}
    for observation in observations:
        key = str(getattr(observation, "observation_id", "") or "")
        if not key or key in by_id:
            raise ValueError("duplicate_or_missing_canonical_observation")
        by_id[key] = observation

    previews: list[dict] = []
    for record in records:
        if not isinstance(record, StagingSourceRecord):
            raise ValueError("invalid_staging_source_record")
        envelope = record.envelope
        # A caller must not fabricate a trusted envelope by changing both
        # the row and the expected metadata in lockstep. Re-derive it from
        # the validated, source-faithful bulletin.
        if envelope != prepare_official_bulletin(record.bulletin):
            raise ValueError("staging_bulletin_envelope_mismatch")
        delivery_key = f'{envelope["source_name"]}:{envelope["source_id"]}'
        expected_id = "obs:" + hashlib.blake2s(delivery_key.encode(), digest_size=16).hexdigest()
        row = by_id.pop(expected_id, None)
        if row is None:
            raise ValueError("missing_canonical_observation")
        raw = envelope["raw_payload"].encode("utf-8")
        expected_hash = hashlib.sha256(raw).hexdigest()
        provenance = getattr(row, "provenance", None)
        expected_provenance = envelope["provenance"]
        if (
            getattr(row, "service", None) != "maritime"
            or getattr(row, "lane", None) != "safety"
            or getattr(row, "observation_type", None) != "official_maritime_bulletin"
            or getattr(row, "source_policy", None) != "official_metadata_unverified"
            or getattr(row, "source_name", None) != envelope["source_name"]
            or getattr(row, "source_id", None) != envelope["source_id"]
            or getattr(row, "source_url", None) != envelope["source_url"]
            or getattr(row, "raw_payload_hash", None) != expected_hash
            or getattr(row, "observed_at", None) != envelope["observed_at"]
            or not _same_optional_number(getattr(row, "lat", None), envelope["lat"])
            or not _same_optional_number(getattr(row, "lon", None), envelope["lon"])
            or not _same_optional_number(
                getattr(row, "uncertainty_m", None), envelope["uncertainty_m"]
            )
            or getattr(row, "location_precision", None) is not None
            or getattr(row, "subject_refs", None) != envelope["subject_refs"]
            or not isinstance(provenance, dict)
            or provenance != expected_provenance
            or expected_provenance["origin_authority_verified"] is not False
            or expected_provenance["attack_corroboration_allowed"] is not False
            or expected_provenance["reuse_rights_verified"] is not False
            or record.publication_allowed is not False
            or record.origin_independence_verified is not False
        ):
            raise ValueError("canonical_source_provenance_mismatch")

        receipt = _canonical_receipt_utc(getattr(row, "received_at", None))
        _verify_source_chronology(receipt, expected_provenance)
        kind = expected_provenance["bulletin_kind"]
        if kind not in _PREVIEW_KINDS:
            raise ValueError("unsupported_staging_preview_kind")
        proposed_type = _PREVIEW_KINDS[kind]
        review_color = CATEGORY_COLORS[proposed_type] if proposed_type else None
        blockers = ["origin_independence_unverified", "publication_review_required",
                    "reuse_rights_not_verified"]
        if not expected_provenance["vessel_imo"] and not expected_provenance["vessel_mmsi"]:
            blockers.append("strong_vessel_identity_unverified")
        if not expected_provenance["vessel_name"]:
            blockers.append("vessel_name_unavailable")
        if expected_provenance["published_at_utc"] is None:
            blockers.append("exact_publication_time_unavailable")
        if expected_provenance["event_time_precision"] == "approximate" and (
            expected_provenance["reported_time_uncertainty_minutes"] is None
        ):
            blockers.append("approximate_event_time_unbounded")
        if expected_provenance["source_rights"] == "restricted_republication":
            blockers.append("restricted_republication")
        if proposed_type is None:
            blockers.append("not_an_attack")
        previews.append({
            "preview_id": "staging-attack-preview:" + expected_id,
            "canonical_observation_id": expected_id,
            "original_report_id": expected_provenance["original_report_id"],
            "source_url": envelope["source_url"],
            "source_rights": expected_provenance["source_rights"],
            "source_checked_on_utc": expected_provenance["source_checked_on_utc"],
            "source_document_sha256": expected_provenance["original_document_sha256"],
            "raw_payload_hash": expected_hash,
            "received_at_utc": receipt.isoformat(),
            "canonical_observed_at": envelope["observed_at"],
            "observed_at_semantics": expected_provenance["observed_at_semantics"],
            "reported_location": (
                {"lat": envelope["lat"], "lon": envelope["lon"],
                 "role": expected_provenance["location_role"],
                 "uncertainty_km": record.bulletin.location_uncertainty_km}
                if envelope["lat"] is not None else None
            ),
            "occurred_at_utc": expected_provenance["occurred_at_utc"],
            "event_date": expected_provenance["event_date"],
            "published_at_utc": expected_provenance["published_at_utc"],
            "publication_date": expected_provenance["publication_date"],
            "event_time_precision": expected_provenance["event_time_precision"],
            "reported_time_uncertainty_minutes": expected_provenance["reported_time_uncertainty_minutes"],
            "vessel_name_as_reported": expected_provenance["vessel_name"],
            "vessel_imo_as_reported": expected_provenance["vessel_imo"],
            "vessel_mmsi_as_reported": expected_provenance["vessel_mmsi"],
            "source_kind": kind,
            "proposed_incident_type": proposed_type,
            "review_color": review_color,
            "review_status": "candidate" if proposed_type else "context_only",
            "review_blockers": blockers,
            "independent_origins_verified": 0,
            "ais_as_attack_proof": False,
            "publication_allowed": False,
            "staging_only": True,
        })
    if by_id:
        raise ValueError("unexpected_canonical_observation")
    return tuple(previews)
