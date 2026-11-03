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
import re
from urllib.parse import urlsplit


_ALLOWED_LINK_BASIS = frozenset({
    "shared_vhf_mayday", "same_original_document", "explicit_republication",
    "matching_event_details_unverified_origin",
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


def _valid_https_source_url(value: object) -> bool:
    """Reject malformed, credential-bearing or fragment-only evidence URLs."""
    if not isinstance(value, str) or any(char.isspace() for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
            and parsed.port != 0
        )
    except ValueError:
        return False


def _time_uncertainty_minutes(preview: Mapping[str, object]) -> float:
    """Validate source-declared uncertainty; never infer it from 'approximate'.

    An unknown bound remains zero for automated comparisons, not a fabricated
    margin. Very broad bounds are retained but cannot justify lineage links.
    """
    precision = preview.get("event_time_precision")
    bound = preview.get("reported_time_uncertainty_minutes")
    if bound is None:
        return 0.0
    if (precision != "approximate" or preview.get("occurred_at_utc") is None
            or type(bound) not in (int, float) or not isfinite(bound)
            or not 0 < bound <= 1440):
        raise ValueError("lineage_invalid_time_uncertainty")
    return float(bound)


def _source_provenance(preview: Mapping[str, object]) -> None:
    """Validate optional source clocks and hashes before fingerprinting."""
    uncertainty = _time_uncertainty_minutes(preview)
    clocks: dict[str, datetime] = {}
    for field in ("published_at_utc", "received_at_utc"):
        stamp = preview.get(field)
        if stamp is not None:
            clocks[field] = _utc(stamp)
    if (
        "published_at_utc" in clocks
        and "received_at_utc" in clocks
        and clocks["published_at_utc"] > clocks["received_at_utc"]
    ):
        raise ValueError("lineage_publication_after_receipt")
    event_stamp = preview.get("occurred_at_utc")
    if event_stamp is not None:
        event_at = _utc(event_stamp)
        for field in ("published_at_utc", "received_at_utc"):
            if (field in clocks and
                    (event_at - clocks[field]).total_seconds() > uncertainty * 60):
                raise ValueError("lineage_event_after_" + field)
    for field in ("publication_date", "source_checked_on_utc"):
        value = preview.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("lineage_invalid_source_day")
        try:
            day = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("lineage_invalid_source_day") from exc
        if "received_at_utc" in clocks and day > clocks["received_at_utc"].date():
            raise ValueError("lineage_source_day_after_receipt")
    # A source's day-only publication date may be local rather than UTC.
    # Allow a one-day boundary, but never accept a report published two
    # or more calendar days before the event it claims to describe.
    publication_day = (
        clocks["published_at_utc"].date()
        if "published_at_utc" in clocks
        else date.fromisoformat(preview["publication_date"])
        if preview.get("publication_date") is not None else None
    )
    if (publication_day is not None
            and (_day(preview) - publication_day).days > 1):
        raise ValueError("lineage_publication_day_before_event")
    for field in ("raw_payload_hash", "source_document_sha256"):
        digest = preview.get(field)
        if digest is not None and (
            not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise ValueError("lineage_invalid_source_digest")


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
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raise ValueError("lineage_invalid_event_day")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("lineage_invalid_event_day") from exc


def _position(preview: Mapping[str, object]) -> tuple[float, float, float] | None:
    value = preview.get("reported_location")
    if value is None:
        return None
    if (not isinstance(value, Mapping)
            or set(value) != {"lat", "lon", "role", "uncertainty_km"}
            or value.get("role") != "incident_site"):
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
    left_day, right_day = _day(a), _day(b)
    left, right = a.get("occurred_at_utc"), b.get("occurred_at_utc")
    if left is not None and right is not None:
        # UTC midnight is not an incident boundary. Two clocked reports may
        # describe one event across adjacent dates, provided their timestamps
        # are within the conservative two-hour review window. A day-only
        # report has no such precision and must retain its calendar boundary.
        # A source-declared bound is not evidence of a shared origin. Apply
        # only documented bounds, cap the extra allowance at two hours and
        # require human review for very broad (>2h) uncertainty intervals.
        lmargin = _time_uncertainty_minutes(a)
        rmargin = _time_uncertainty_minutes(b)
        if lmargin > 120 or rmargin > 120:
            raise ValueError("lineage_temporal_uncertainty_too_broad")
        margin_seconds = min(120, lmargin + rmargin) * 60
        if abs((_utc(left) - _utc(right)).total_seconds()) > 120 * 60 + margin_seconds:
            raise ValueError("lineage_temporal_conflict")
    elif left_day != right_day:
        raise ValueError("lineage_event_day_conflict")
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
                or type(p.get("independent_origins_verified")) is not int
                or p["independent_origins_verified"] != 0
                or p.get("review_status") != "candidate"
                or p.get("source_kind") not in {"attack", "piracy"}):
            raise ValueError("lineage_untrusted_or_publishable_candidate")
        rid, oid = p.get("original_report_id"), p.get("canonical_observation_id")
        if (not isinstance(rid, str) or not rid
                or not isinstance(oid, str) or not oid
                or rid in by_id or oid in seen_observations):
            raise ValueError("lineage_duplicate_or_missing_source_id")
        if not _valid_https_source_url(p.get("source_url")):
            raise ValueError("lineage_invalid_source_url")
        _source_provenance(p)
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
        if not _valid_https_source_url(url):
            raise ValueError("lineage_link_source_required")
        pair = tuple(sorted((left, right)))
        # A manually documented match between *different* publishers is a
        # hypothesis of shared upstream reporting, not an extra witness.
        # Require tightly matching UTC event clocks and a supporting original
        # URL, rather than merging merely because two alerts say "attack".
        if basis == "matching_event_details_unverified_origin":
            a, b = by_id[left], by_id[right]
            first, second = a.get("occurred_at_utc"), b.get("occurred_at_utc")
            if (first is None or second is None
                    or abs((_utc(first) - _utc(second)).total_seconds()) > 300):
                raise ValueError("lineage_matching_details_clock_mismatch")
            hosts = (urlsplit(a["source_url"]).hostname,
                     urlsplit(b["source_url"]).hostname)
            if (hosts[0] == hosts[1]
                    or url not in (a["source_url"], b["source_url"])):
                raise ValueError("lineage_matching_details_sources_required")
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
    # A graph-only digest is unsafe: changing an event clock, vessel identity,
    # source URL or reported position could previously leave the same digest.
    # Fingerprint the complete *selected source evidence* as well as the links.
    # This is still a staging snapshot hash, NOT a source-document signature.
    source_fields = (
        "canonical_observation_id", "original_report_id", "source_url",
        "source_kind", "source_rights", "source_checked_on_utc",
        "raw_payload_hash", "source_document_sha256", "received_at_utc",
        "published_at_utc", "publication_date", "occurred_at_utc",
        "event_date", "event_time_precision",
        "reported_time_uncertainty_minutes", "vessel_name_as_reported",
        "vessel_imo_as_reported", "vessel_mmsi_as_reported",
    )
    evidence = []
    for rid in sorted(by_id):
        source = by_id[rid]
        entry = {field: source.get(field) for field in source_fields}
        location = source.get("reported_location")
        entry["reported_location"] = (
            None if location is None else {
                "lat": location["lat"], "lon": location["lon"],
                "role": location["role"],
                "uncertainty_km": location.get("uncertainty_km"),
            }
        )
        evidence.append(entry)
    ledger = {"groups": groups, "links": links, "source_evidence": evidence}
    try:
        canonical = json.dumps(
            ledger, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("lineage_noncanonical_evidence") from exc
    digest = sha256(canonical.encode("utf-8")).hexdigest()
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
