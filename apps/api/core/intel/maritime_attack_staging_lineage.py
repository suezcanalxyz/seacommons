# SPDX-License-Identifier: AGPL-3.0-or-later
"""Conservative, staging-only review of potentially shared attack-report origins.

Different publishers are not independent witnesses. An explicit *suspected*
lineage link groups likely republications for human review; it never certifies
the origin, verifies an incident or authorizes PLAY/LIVE publication.
No database access, network access, scheduler or production side effects.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from math import asin, cos, isfinite, radians, sin, sqrt


_ALLOWED_LINK_BASIS = frozenset({
    "shared_vhf_mayday", "same_original_document", "explicit_republication",
})


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("lineage_exact_clock_required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("lineage_invalid_event_clock") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("lineage_timezone_required")
    return result.astimezone(timezone.utc)


def _day(preview: Mapping[str, object]) -> date:
    stamp = preview.get("occurred_at_utc")
    if stamp is not None:
        day = _utc(stamp).date()
        reported = preview.get("event_date")
        if reported is not None and reported != day.isoformat():
            raise ValueError("lineage_event_date_conflict")
        if preview.get("event_time_precision") not in {"exact", "approximate"}:
            raise ValueError("lineage_event_precision_conflict")
        return day
    if preview.get("event_time_precision") != "day":
        raise ValueError("lineage_missing_event_clock")
    raw = preview.get("event_date")
    if not isinstance(raw, str):
        raise ValueError("lineage_event_day_required")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("lineage_invalid_event_day") from exc


def _position(preview: Mapping[str, object]) -> tuple[float, float, float] | None:
    value = preview.get("reported_location")
    if value is None:
        return None
    if not isinstance(value, Mapping) or value.get("role") != "incident_site":
        raise ValueError("lineage_non_incident_geometry")
    lat, lon, uncertainty = (
        value.get("lat"), value.get("lon"), value.get("uncertainty_km")
    )
    if any(type(v) not in (float, int) or not isfinite(v) for v in (lat, lon)):
        raise ValueError("lineage_invalid_geometry")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("lineage_invalid_geometry")
    if uncertainty is not None and (
        type(uncertainty) not in (float, int)
        or not isfinite(uncertainty) or uncertainty < 0
    ):
        raise ValueError("lineage_invalid_uncertainty")
    return float(lat), float(lon), float(uncertainty or 0)


def _distance_km(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    lat1, lon1, _ = a
    lat2, lon2, _ = b
    p1, p2 = radians(lat1), radians(lat2)
    h = sin(radians(lat2 - lat1) / 2) ** 2 + cos(p1) * cos(p2) * (
        sin(radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0088 * asin(sqrt(min(1.0, max(0.0, h))))


def _compatible(a: Mapping[str, object], b: Mapping[str, object]) -> None:
    if a.get("source_kind") != b.get("source_kind"):
        raise ValueError("lineage_attack_type_conflict")
    if _day(a) != _day(b):
        raise ValueError("lineage_event_day_conflict")
    left, right = a.get("occurred_at_utc"), b.get("occurred_at_utc")
    if left is not None and right is not None:
        if abs((_utc(left) - _utc(right)).total_seconds()) > 120 * 60:
            raise ValueError("lineage_temporal_conflict")
    for key in ("vessel_imo_as_reported", "vessel_mmsi_as_reported"):
        x, y = a.get(key), b.get(key)
        if x and y and x != y:
            raise ValueError("lineage_vessel_identity_conflict")
    x, y = a.get("vessel_name_as_reported"), b.get("vessel_name_as_reported")
    if x and y and " ".join(x.upper().split()) != " ".join(y.upper().split()):
        raise ValueError("lineage_vessel_name_conflict")
    p, q = _position(a), _position(b)
    if p is not None and q is not None:
        if _distance_km(p, q) > 100 + p[2] + q[2]:
            raise ValueError("lineage_spatial_conflict")


def build_staging_attack_lineage_review(
    previews: Sequence[Mapping[str, object]],
    suspected_shared_origins: Sequence[Mapping[str, str]] = (),
) -> dict[str, object]:
    """Return a deterministic *suspected* origin graph; zero verified witnesses.

    Each link is a bounded, sourced hypothesis, not proof of common origin.
    Different report IDs alone do not establish independent corroboration.
    """
    if (not isinstance(previews, Sequence) or isinstance(previews, (str, bytes))
            or not 1 <= len(previews) <= 32):
        raise ValueError("lineage_candidate_batch_out_of_bounds")
    if (not isinstance(suspected_shared_origins, Sequence)
            or isinstance(suspected_shared_origins, (str, bytes))
            or len(suspected_shared_origins) > 64):
        raise ValueError("lineage_link_batch_out_of_bounds")
    by_id: dict[str, Mapping[str, object]] = {}
    seen_observations: set[str] = set()
    for p in previews:
        if not isinstance(p, Mapping):
            raise ValueError("lineage_candidate_mapping_required")
        if (p.get("staging_only") is not True
                or p.get("publication_allowed") is not False
                or p.get("independent_origins_verified") != 0
                or p.get("review_status") != "candidate"
                or p.get("source_kind") not in {"attack", "piracy"}):
            raise ValueError("lineage_untrusted_or_publishable_candidate")
        rid, oid = p.get("original_report_id"), p.get("canonical_observation_id")
        if (not isinstance(rid, str) or not rid
                or not isinstance(oid, str) or not oid
                or rid in by_id or oid in seen_observations):
            raise ValueError("lineage_duplicate_or_missing_source_id")
        if not isinstance(p.get("source_url"), str) or not p["source_url"].startswith("https://"):
            raise ValueError("lineage_invalid_source_url")
        _day(p)
        _position(p)
        by_id[rid] = p
        seen_observations.add(oid)

    parent = {rid: rid for rid in by_id}

    def root(rid: str) -> str:
        while parent[rid] != rid:
            rid = parent[rid]
        return rid

    links: list[dict[str, str]] = []
    seen_links: set[tuple[str, str]] = set()
    for link in suspected_shared_origins:
        if not isinstance(link, Mapping):
            raise ValueError("lineage_link_mapping_required")
        left, right = link.get("left_report_id"), link.get("right_report_id")
        basis, url = link.get("basis"), link.get("supporting_source_url")
        if (not isinstance(left, str) or not isinstance(right, str)
                or left not in by_id or right not in by_id or left == right):
            raise ValueError("lineage_invalid_link_endpoints")
        if basis not in _ALLOWED_LINK_BASIS:
            raise ValueError("lineage_invalid_link_basis")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError("lineage_link_source_required")
        pair = tuple(sorted((left, right)))
        if pair in seen_links:
            raise ValueError("lineage_duplicate_link")
        seen_links.add(pair)
        _compatible(by_id[left], by_id[right])
        # Also validate every cross-component pair: transitive merges must not
        # hide a contradictory vessel identity, clock or location.
        lroot, rroot = root(left), root(right)
        if lroot != rroot:
            lmembers = [rid for rid in by_id if root(rid) == lroot]
            rmembers = [rid for rid in by_id if root(rid) == rroot]
            for a in lmembers:
                for b in rmembers:
                    _compatible(by_id[a], by_id[b])
            parent[max(lroot, rroot)] = min(lroot, rroot)
        links.append({
            "left_report_id": pair[0], "right_report_id": pair[1],
            "basis": basis, "supporting_source_url": url,
            "status": "suspected_shared_origin_not_verified",
        })

    clusters: dict[str, list[str]] = {}
    for rid in by_id:
        clusters.setdefault(root(rid), []).append(rid)
    groups = [
        {
            "report_ids": sorted(members),
            "canonical_observation_ids": sorted(
                by_id[r]["canonical_observation_id"] for r in members
            ),
            "publication_count": len(members),
            "verified_independent_witnesses": 0,
            "lineage_status": "suspected_shared_origin" if len(members) > 1
                              else "origin_independence_unknown",
        }
        for members in clusters.values()
    ]
    groups.sort(key=lambda group: group["report_ids"])
    links.sort(key=lambda link: (link["left_report_id"], link["right_report_id"]))
    ledger = {"groups": groups, "links": links}
    digest = sha256(json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "source_count": len(previews),
        "provisional_origin_groups": len(groups),
        "suspected_duplicate_publications": len(previews) - len(groups),
        "lineage_groups": groups,
        "suspected_shared_origin_links": links,
        "lineage_snapshot_sha256": digest,
        "lineage_digest_is_source_proof": False,
        "independent_origins_verified": 0,
        "review_blockers": [
            "origin_independence_unverified",
            "manual_lineage_and_source_review_required",
        ],
        "publication_allowed": False,
        "staging_only": True,
    }
