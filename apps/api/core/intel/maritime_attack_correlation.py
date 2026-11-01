# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure, conservative maritime incident correlation (staging prototype).

No database writes, publication, scheduled execution, or AIS-based attack
inference. An AIS gap is context, NEVER proof of an attack. Independent
lineage groups must reflect the ORIGINAL reporting authority, not merely
different outlets republishing the same announcement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import ipaddress

from core.intel.maritime_attack_play_guard import _canonical_authority_key


@dataclass(frozen=True)
class VesselRef:
    imo: str = ""
    mmsi: str = ""
    name: str = ""


@dataclass(frozen=True)
class IncidentClaim:
    claim_id: str
    kind: str
    occurred_at: datetime
    source_group: str
    source_url: str
    vessel: VesselRef
    lat: float | None = None
    lon: float | None = None
    uncertainty_km: float = 0.0
    published_at: datetime | None = None
    received_at: datetime | None = None
    # The originating document/case identifier, shared by syndicated copies.
    # A publisher URL is not sufficient proof of independent reporting.
    origin_report_id: str | None = None
    # Precision of reported event time, not ingestion latency.
    time_uncertainty_minutes: float = 0.0


@dataclass(frozen=True)
class AISFix:
    mmsi: str
    observed_at: datetime
    lat: float
    lon: float
    # Optional raw AIS speed over ground. Never an independent attack witness.
    sog_knots: float | None = None
    # Optional original collector receipt clock. An AIS event timestamp that
    # postdates its own receipt by >5 minutes is suspect, not vessel evidence.
    received_at: datetime | None = None



def ais_fix_from_vessel_track(track: object) -> AISFix:
    """Adapt an existing VesselTrackDB row without querying or writing a DB.

    VesselTrackDB.ts and .received_at are PostgreSQL timestamp-without-timezone
    columns whose documented convention is UTC. Convert *only these model
    fields* to aware UTC before passing them into the correlator. Never use
    ingestion time as the vessel's observed time, or infer an attack from AIS.
    Missing receipt clocks must fail closed rather than silently disabling
    the future-relative-to-receipt check.
    """
    def clock(field: str) -> datetime:
        value = getattr(track, field, None)
        if not isinstance(value, datetime):
            raise ValueError("Vessel track " + field + " must be datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return _utc(value)

    mmsi = str(getattr(track, "mmsi", "") or "").strip()
    if not _valid_mmsi(mmsi):
        raise ValueError("Invalid vessel track MMSI")
    lat, lon = getattr(track, "lat", None), getattr(track, "lon", None)
    if (isinstance(lat, bool) or isinstance(lon, bool)
            or not isinstance(lat, (int, float))
            or not isinstance(lon, (int, float))
            or not isfinite(lat) or not isfinite(lon)
            or not -90 <= lat <= 90 or not -180 <= lon <= 180):
        raise ValueError("Invalid vessel track coordinates")
    sog = getattr(track, "sog", None)
    if sog is not None and (
        isinstance(sog, bool) or not isinstance(sog, (int, float))
        or not isfinite(sog) or not 0 <= sog <= 70
    ):
        raise ValueError("Invalid vessel track speed")
    return AISFix(
        mmsi=mmsi,
        observed_at=clock("ts"),
        lat=float(lat),
        lon=float(lon),
        sog_knots=float(sog) if sog is not None else None,
        received_at=clock("received_at"),
    )


@dataclass(frozen=True)
class AISGap:
    mmsi: str
    observed_at: datetime
    event_id: str


@dataclass(frozen=True)
class Correlation:
    status: str  # no_match | candidate | corroborated
    incident_type: str
    color_token: str
    claim_ids: tuple[str, ...]
    independent_groups: tuple[str, ...]
    supporting: tuple[str, ...]
    contradicting: tuple[str, ...]
    nearest_ais_km: float | None = None
    nearest_ais_minutes: float | None = None
    related_gap_ids: tuple[str, ...] = ()
    # Provenance is retained even when the claim is only a review candidate.
    source_evidence: tuple[dict[str, str | None], ...] = ()
    publication_allowed: bool = False
    requires_operator_review: bool = True
    # Paired original AIS fix timestamps, for audit only; never corroboration.
    related_sudden_stop_fixes: tuple[tuple[str, str], ...] = ()


_KINDS = frozenset({"attack", "sinking", "explosion", "collision", "piracy"})
_COLORS = {
    "candidate": "maritime_incident_candidate_orange",
    "attack": "maritime_attack_coral",
    "sinking": "maritime_sinking_bordeaux",
    "other": "maritime_incident_red",
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamps must include timezone")
    return value.astimezone(timezone.utc)


def _name(value: str) -> str:
    return "".join(char for char in value.upper() if char.isalnum())


def _valid_imo(value: str) -> bool:
    """IMO ship identifier: six digits plus the official check digit."""
    return (
        len(value) == 7 and value.isascii() and value.isdigit()
        and sum(int(digit) * (7 - i) for i, digit in enumerate(value[:6])) % 10
            == int(value[6])
    )


def _valid_mmsi(value: str) -> bool:
    """Reject incomplete, nonnumeric and placeholder MMSI values."""
    return (
        len(value) == 9 and value.isascii() and value.isdigit()
        and value != "000000000"
    )


def _normalized_identifier(value: object, prefix: str) -> str:
    result = str(value or "").strip()
    if result.upper().startswith(prefix):
        result = result[len(prefix):].lstrip(" :#-")
    return result


def _identity_match(subject: VesselRef, reported: VesselRef) -> str:
    """An explicit contradictory IMO/MMSI is a veto, even when names match."""
    if subject.imo and reported.imo and subject.imo != reported.imo:
        return "conflict"
    if subject.mmsi and reported.mmsi and subject.mmsi != reported.mmsi:
        return "conflict"
    if subject.imo and reported.imo and subject.imo == reported.imo and _valid_imo(subject.imo):
        return "strong"
    if subject.mmsi and reported.mmsi and subject.mmsi == reported.mmsi and _valid_mmsi(subject.mmsi):
        return "strong"
    if subject.name and reported.name and _name(subject.name) == _name(reported.name):
        return "weak"
    return "unknown"


def _km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    dlat, dlon = radians(b_lat - a_lat), radians(b_lon - a_lon)
    h = sin(dlat / 2) ** 2 + cos(radians(a_lat)) * cos(radians(b_lat)) * sin(dlon / 2) ** 2
    return 12742.0 * asin(min(1.0, sqrt(h)))


def _validate_claim_location(claim: IncidentClaim) -> None:
    """Reject malformed coordinates rather than treating them as uncertainty."""
    if (claim.lat is None) != (claim.lon is None):
        raise ValueError("Latitude and longitude must both be supplied")
    if claim.lat is not None and (
        not isfinite(claim.lat) or not isfinite(claim.lon)
        or not -90 <= claim.lat <= 90 or not -180 <= claim.lon <= 180
    ):
        raise ValueError("Invalid incident coordinates")
    if not isfinite(claim.uncertainty_km) or claim.uncertainty_km < 0:
        raise ValueError("Invalid location uncertainty")
    if not isfinite(claim.time_uncertainty_minutes) or claim.time_uncertainty_minutes < 0:
        raise ValueError("Invalid time uncertainty")



def _canonical_source_url(value: str) -> str:
    """Normalize article aliases for evidence deduplication, not for fetching.

    Query identifiers remain intact, but common tracking parameters and URL
    fragments cannot manufacture an additional independent report.
    """
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            return ""
        if parsed.username is not None or parsed.password is not None:
            return ""
        host = parsed.hostname.lower().rstrip(".")
        if host in {"localhost"} or host.endswith((".local", ".internal")):
            return ""
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global:
                return ""
        except ValueError:
            pass
        port = parsed.port  # raises ValueError on malformed ports
        authority = host if port in (None, 443) else f"{host}:{port}"
        path = parsed.path.rstrip("/") or "/"
        query = urlencode(sorted(
            (key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
            and key.lower() not in {"fbclid", "gclid", "msclkid", "mc_cid", "mc_eid"}
        ))
        return urlunsplit(("https", authority, path, query, ""))
    except (ValueError, AttributeError):
        return ""


def claim_from_source_observation(observation: object, extracted: dict) -> IncidentClaim | None:
    """Convert a reviewed extraction from the canonical immutable observation.

    This is a pure staging adapter: it does not fetch, persist, publish or
    infer an attack from AIS. In particular, a model-extracted publisher name
    is NEVER an independent-source group. Only explicitly VERIFIED provenance
    attached by a source adapter/operator may supply that authority.
    """
    kind = str(extracted.get("kind") or "").lower().strip()
    occurred = extracted.get("occurred_at")
    if kind not in _KINDS or not occurred:
        return None

    def parsed_utc(value: object, *, stored_naive_utc: bool = False) -> datetime:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, str):
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("Invalid claim timestamp")
        # SourceObservationDB.received_at is stored as naive UTC by the
        # canonical DB model. Do not extend this exception to event dates.
        if stored_naive_utc and result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return _utc(result)

    provenance = getattr(observation, "provenance", {}) or {}
    if not isinstance(provenance, dict):
        provenance = {}
    observation_type = getattr(observation, "observation_type", "")
    official_bulletin = observation_type == "official_maritime_bulletin"
    operator_relay = observation_type == "operator_incident_statement"
    # The ship manager's report cites the Master's statement but is not
    # itself an independently authenticated original witness artifact.
    source_bound = official_bulletin or operator_relay
    if source_bound:
        # An extraction cannot turn a suspicious approach, anchorage warning
        # or other original bulletin into a verified attack.
        if kind != provenance.get("bulletin_kind"):
            return None
        precision = provenance.get("event_time_precision")
        if precision == "unknown":
            # Publication is not the occurrence of an incident.
            return None
        if precision == "exact":
            original_time = provenance.get("occurred_at_utc")
            if not original_time or parsed_utc(occurred) != parsed_utc(original_time):
                raise ValueError("Bulletin event timestamp differs from original")
        elif precision == "day":
            original_date = provenance.get("event_date")
            if not original_date or parsed_utc(occurred).date().isoformat() != original_date:
                raise ValueError("Bulletin event date differs from original")
        else:
            return None
    verified = (
        provenance.get("origin_authority_verified") is True
        and not operator_relay  # relay never supplies a verified witness group
    )
    group = str(provenance.get("originating_authority_id") or "").strip() if verified else ""
    original_id = str(provenance.get("original_report_id") or "").strip() if verified else ""
    # Some source adapters write published_at_utc, others published_at.
    # Never silently ignore a contradictory secondary publication timestamp.
    publications = []
    for field in ("published_at_utc", "published_at"):
        raw = provenance.get(field)
        if raw is not None:
            publications.append(parsed_utc(raw))
    if len(publications) == 2 and abs(
        (publications[0] - publications[1]).total_seconds()
    ) > 300:
        raise ValueError("Conflicting source publication timestamps")
    received_raw = getattr(observation, "received_at", None)
    vessel = VesselRef(
        imo=_normalized_identifier(extracted.get("imo"), "IMO"),
        mmsi=_normalized_identifier(extracted.get("mmsi"), "MMSI"),
        name=str(extracted.get("vessel_name") or "").strip(),
    )
    # Never promote a claim using a malformed or placeholder vessel ID.
    # Keep the original SourceObservation unchanged for operator review.
    if vessel.imo and not _valid_imo(vessel.imo):
        raise ValueError("Invalid IMO check digit or format")
    if vessel.mmsi and not _valid_mmsi(vessel.mmsi):
        raise ValueError("Invalid MMSI format")
    if source_bound:
        # Do not let news-to-incident extraction silently substitute a vessel
        # or enrich a bulletin with identifiers absent from the original.
        # A separately corroborated entity-resolution claim must be handled
        # as separate evidence, not written back into this immutable claim.
        source_imo = _normalized_identifier(provenance.get("vessel_imo"), "IMO")
        source_mmsi = _normalized_identifier(provenance.get("vessel_mmsi"), "MMSI")
        source_name = str(provenance.get("vessel_name") or "").strip()
        if ((vessel.imo and vessel.imo != source_imo)
                or (vessel.mmsi and vessel.mmsi != source_mmsi)
                or (vessel.name and _name(vessel.name) != _name(source_name))):
            raise ValueError("Official bulletin vessel identity differs from original")
    if not (vessel.imo or vessel.mmsi or vessel.name):
        return None
    # Missing extraction precision is UNKNOWN, not zero. A timestamp
    # synthesized from a day-only report must not silently become minute-
    # precise evidence, and an approximate map pin must not become exact.
    # Explicit zero remains valid when the originating document establishes
    # that precision and an operator verifies the extraction.
    def extracted_precision(field: str, *, unknown: float) -> float:
        value = extracted.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return unknown
        return float(value)

    lat, lon = extracted.get("lat"), extracted.get("lon")
    location_uncertainty = extracted_precision(
        "uncertainty_km",
        unknown=10000.0 if lat is not None or lon is not None else 0.0,
    )
    time_uncertainty = extracted_precision(
        "time_uncertainty_minutes", unknown=1440.0,
    )
    if source_bound:
        # A ship's reported anchorage/last position is not the attack site.
        # Only an explicitly classified incident site may enter the spatial
        # correlator, and its source coordinates/precision take precedence.
        if provenance.get("location_role") != "incident_site":
            lat = lon = None
            location_uncertainty = 0.0
        else:
            source_lat = getattr(observation, "lat", None)
            source_lon = getattr(observation, "lon", None)
            if source_lat is None or source_lon is None:
                raise ValueError("Bulletin incident-site coordinates missing")
            for proposed, original in ((lat, source_lat), (lon, source_lon)):
                if proposed is not None and (
                    not isfinite(float(proposed))
                    or abs(float(proposed) - original) > 0.000001
                ):
                    raise ValueError("Extracted incident site differs from bulletin")
            lat, lon = source_lat, source_lon
            source_uncertainty_m = getattr(observation, "uncertainty_m", None)
            location_uncertainty = (
                max(location_uncertainty, float(source_uncertainty_m) / 1000.0)
                if source_uncertainty_m is not None else 10000.0
            )
        if provenance.get("event_time_precision") == "day":
            # A synthetic clock derived from a day-only bulletin must never
            # masquerade as minute-level evidence, even if extraction says 0.
            time_uncertainty = max(time_uncertainty, 1440.0)
    claim = IncidentClaim(
        claim_id=str(getattr(observation, "observation_id")),
        kind=kind,
        occurred_at=parsed_utc(occurred),
        source_group=group,
        source_url=str(getattr(observation, "source_url", "") or ""),
        vessel=vessel,
        lat=lat,
        lon=lon,
        uncertainty_km=location_uncertainty,
        published_at=publications[0] if publications else None,
        received_at=parsed_utc(received_raw, stored_naive_utc=True) if received_raw else None,
        origin_report_id=original_id or None,
        time_uncertainty_minutes=time_uncertainty,
    )
    _validate_claim_location(claim)
    return claim



def _chronology_issues(claim: IncidentClaim) -> tuple[str, ...]:
    """Report all temporal contradictions without trusting ingestion order."""
    received = _utc(claim.received_at) if claim.received_at is not None else None
    published = _utc(claim.published_at) if claim.published_at is not None else None
    occurred = _utc(claim.occurred_at)
    tolerance_seconds = (claim.time_uncertainty_minutes + 5) * 60
    issues: list[str] = []
    if received is not None and (occurred - received).total_seconds() > tolerance_seconds:
        issues.append("receipt_before_incident:" + claim.claim_id)
    if published is not None and (occurred - published).total_seconds() > tolerance_seconds:
        issues.append("publication_before_incident:" + claim.claim_id)
    if published is not None and received is not None and (published - received).total_seconds() > 300:
        issues.append("publication_after_receipt:" + claim.claim_id)
    return tuple(issues)


def _lineage_components(edges: Sequence[tuple[str, str]]) -> dict[str, str]:
    """Collapse verified derived_from/quotation chains, including intermediates.

    Edges are supplied by the caller from the canonical append-only lineage
    table; this pure function does not query or mutate that table. Unknown
    nodes are harmless, but a derived report must NEVER count as a second
    original source. The lexicographically smallest ID is a stable root.
    """
    parent: dict[str, str] = {}

    def find(identifier: str) -> str:
        # Verified syndication chains can be thousands of documents long.
        # Recursive path compression raises RecursionError for a legitimate
        # deep chain, silently preventing a conservative source collapse.
        # Use an iterative walk and compression; never turn an AIS signal
        # or a copied report into a second original witness.
        parent.setdefault(identifier, identifier)
        node = identifier
        path: list[str] = []
        while parent[node] != node:
            path.append(node)
            node = parent[node]
        for member in path:
            parent[member] = node
        return node

    for derived, original in edges:
        if not derived or not original:
            continue
        left, right = find(derived), find(original)
        if left != right:
            parent[max(left, right)] = min(left, right)
    return {identifier: find(identifier) for identifier in parent}


def _independent_document_groups(
    claims: Sequence[IncidentClaim], lineage_roots: dict[str, str],
) -> tuple[str, ...]:
    """Count attributable original documents, not mirrored URLs or outlets.

    All claims connected through a verified lineage chain count as one
    reporting group even if syndicated under different authority labels.
    Distinct documents from the same original authority also count once.
    """
    # Merge authority labels whenever evidence shares an originating
    # document, canonical URL, or verified lineage. Dropping duplicate
    # documents before merging their authority labels is order-dependent:
    # a syndicated copy could otherwise masquerade as an independent
    # authority when a second document from the real origin is present.
    parent: dict[str, str] = {}
    origin_owner: dict[str, str] = {}
    url_owner: dict[str, str] = {}
    lineage_owner: dict[str, str] = {}

    def find(group: str) -> str:
        parent.setdefault(group, group)
        while parent[group] != group:
            parent[group] = parent[parent[group]]
            group = parent[group]
        return group

    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    for claim in claims:
        # Authority and report identifiers are canonical labels, not display
        # strings: casing/outer whitespace must not manufacture new origins.
        # Keep the original strings on IncidentClaim for the audit trail.
        origin = (claim.origin_report_id or "").strip().casefold()
        # Match the PLAY/DB audit equivalence class for cosmetic separators.
        # Preserve the existing underscore-form group keys for callers.
        group = _canonical_authority_key(claim.source_group).replace(" ", "_")
        url = _canonical_source_url(claim.source_url)
        if not origin or not group or not url:
            continue
        find(group)
        lineage = lineage_roots.get(claim.claim_id, claim.claim_id)
        for owners, key in ((origin_owner, origin), (url_owner, url),
                            (lineage_owner, lineage)):
            if key in owners:
                union(group, owners[key])
            else:
                owners[key] = group
    return tuple(sorted({find(group) for group in parent}))


def correlate(
    subject: VesselRef,
    claims: Sequence[IncidentClaim],
    ais_fixes: Sequence[AISFix] = (),
    ais_gaps: Sequence[AISGap] = (),
    lineage_edges: Sequence[tuple[str, str]] = (),
) -> Correlation:
    """Correlate one claimed incident without promoting or mutating PLAY.

    Separate attacks and sinkings are separate claims/episodes. A single
    official report is still a candidate under the two-lineage rule.
    """
    if not claims:
        return Correlation("no_match", "", "", (), (), (), ("no_incident_claim",))
    # An immutable observation ID must not describe two different reports.
    # Reject the whole input before anchor selection: otherwise whichever
    # conflicting version arrives first can silently change corroboration.
    claims_by_id: dict[str, IncidentClaim] = {}
    for claim in claims:
        previous = claims_by_id.setdefault(claim.claim_id, claim)
        if previous != claim:
            return Correlation(
                "no_match", "", "", (), (), (),
                ("conflicting_duplicate_claim_id:" + claim.claim_id,),
            )
    anchor = claims[0]
    if anchor.kind not in _KINDS:
        raise ValueError("Unsupported maritime incident kind")
    _validate_claim_location(anchor)
    _utc(anchor.occurred_at)
    if _identity_match(subject, anchor.vessel) in {"conflict", "unknown"}:
        return Correlation("no_match", anchor.kind, "", (), (), (), ("anchor_identity_conflict",))
    # Edges must come from canonical, verified derived_from/quotes records.
    # This argument is pure input: no database access or new collector.
    lineage_roots = _lineage_components(lineage_edges)
    # Pick an incident-time reference by corroborated neighborhood rather
    # than arrival order. A chronologically plausible but wrong first report
    # must not split two independent primary observations into false negatives.
    # This selects an anchor only; pairwise checks below remain mandatory.
    # Preserve the original first-report identity veto (never bootstrap an
    # unrelated vessel into an incident merely via later matching reports).
    anchor_options: list[tuple[tuple, IncidentClaim]] = []
    for arrival_index, possible in enumerate(claims):
        if possible.kind != anchor.kind:
            continue
        if _identity_match(subject, possible.vessel) in {"conflict", "unknown"}:
            continue
        _validate_claim_location(possible)
        if _chronology_issues(possible):
            continue
        compatible_peers: list[IncidentClaim] = []
        max_minutes = 360 if possible.kind == "sinking" else 90
        for peer in claims:
            if peer.kind != possible.kind:
                continue
            if _identity_match(subject, peer.vessel) in {"conflict", "unknown"}:
                continue
            # Two reports may each match the subject yet contradict each
            # other on an identifier absent from the subject record.
            if _identity_match(possible.vessel, peer.vessel) == "conflict":
                continue
            _validate_claim_location(peer)
            if _chronology_issues(peer):
                continue
            if abs((_utc(peer.occurred_at) - _utc(possible.occurred_at)).total_seconds()) / 60 > (
                max_minutes + peer.time_uncertainty_minutes + possible.time_uncertainty_minutes
            ):
                continue
            if possible.lat is not None and peer.lat is not None and (
                _km(possible.lat, possible.lon, peer.lat, peer.lon)
                > 35.0 + possible.uncertainty_km + peer.uncertainty_km
            ):
                continue
            compatible_peers.append(peer)
        independent_groups = _independent_document_groups(compatible_peers, lineage_roots)
        # A larger cluster of vague or unclocked reports must not displace
        # two independent, precise primary observations of another episode.
        # Use the same publication/receipt and uncertainty gates as the
        # final corroboration decision when selecting a candidate anchor.
        max_precision_minutes = 360 if possible.kind == "sinking" else 180
        qualified_peers = [
            peer for peer in compatible_peers
            if peer.published_at is not None and peer.received_at is not None
            and peer.time_uncertainty_minutes <= max_precision_minutes
            and (peer.lat is None or peer.uncertainty_km <= 250)
        ]
        qualified_groups = _independent_document_groups(qualified_peers, lineage_roots)
        score = (
            len(qualified_groups),
            len(independent_groups),
            len(compatible_peers),
            -possible.time_uncertainty_minutes,
            -possible.uncertainty_km,
            _identity_match(subject, possible.vessel) == "strong",
            -_utc(possible.occurred_at).timestamp(),
            -arrival_index,  # preserve existing behavior on exact ties
        )
        anchor_options.append((score, possible))
    if anchor_options:
        anchor = max(anchor_options, key=lambda item: item[0])[1]
    valid: list[IncidentClaim] = []
    strong_identity = False
    contradictions: list[str] = []
    seen_ids: set[str] = set()

    # Process the selected anchor first. Otherwise a distant, plausible
    # first-arriving report could still occupy the accepted cluster before
    # the consensus anchor is evaluated, defeating anchor selection.
    ordered_claims = [anchor] + [claim for claim in claims if claim is not anchor]
    for claim in ordered_claims:
        if claim.claim_id in seen_ids:
            continue
        seen_ids.add(claim.claim_id)
        if claim.kind != anchor.kind:
            contradictions.append("different_incident_kind:" + claim.claim_id)
            continue
        _validate_claim_location(claim)
        # Quarantine invalid chronology, but preserve every reason in the
        # audit result. This uses the same check as anchor selection.
        chronology_issues = _chronology_issues(claim)
        if chronology_issues:
            contradictions.extend(chronology_issues)
            continue
        delta_minutes = abs((_utc(claim.occurred_at) - _utc(anchor.occurred_at)).total_seconds()) / 60
        # Separate attacks hours apart must not collapse into one episode.
        max_minutes = 360 if anchor.kind == "sinking" else 90
        if delta_minutes > max_minutes + anchor.time_uncertainty_minutes + claim.time_uncertainty_minutes:
            contradictions.append("temporal_conflict:" + claim.claim_id)
            continue
        identity = _identity_match(subject, claim.vessel)
        if identity in {"conflict", "unknown"}:
            contradictions.append("identity_" + identity + ":" + claim.claim_id)
            continue
        # A subject identified by IMO alone cannot merge a second report
        # with a conflicting MMSI (or vice versa) merely by matching name.
        # Cross-claim identifiers are a veto, never an attack signal.
        if any(_identity_match(prior.vessel, claim.vessel) == "conflict"
               for prior in valid):
            contradictions.append("cross_claim_vessel_identifier_conflict:" + claim.claim_id)
            continue
        # Compare against EVERY accepted observation. An unlocated anchor
        # must not permit two incompatible locations to corroborate each other.
        if any(
            prior.lat is not None and claim.lat is not None
            and _km(prior.lat, prior.lon, claim.lat, claim.lon)
                > 35.0 + prior.uncertainty_km + claim.uncertainty_km
            for prior in valid
        ):
            contradictions.append("spatial_conflict:" + claim.claim_id)
            continue
        # Apply the same pairwise rule to event times, not just the anchor.
        if any(
            abs((_utc(prior.occurred_at) - _utc(claim.occurred_at)).total_seconds()) / 60
                > (360 if anchor.kind == "sinking" else 90)
                  + prior.time_uncertainty_minutes + claim.time_uncertainty_minutes
            for prior in valid
        ):
            contradictions.append("temporal_conflict:" + claim.claim_id)
            continue
        strong_identity |= identity == "strong"
        valid.append(claim)

    if not valid:
        return Correlation("no_match", anchor.kind, "", (), (), (), tuple(contradictions))
    # Corroboration requires an EXPLICIT original document/case identifier.
    # Source names and URLs alone do not establish editorial independence.
    # A single document cannot count twice even if different origins are
    # accidentally assigned to the same URL, or if it is syndicated.
    groups = _independent_document_groups(valid, lineage_roots)
    if len(groups) < len(_independent_document_groups(valid, {})):
        contradictions.append("derived_source_not_independent")
    # An unrelated malformed URL is quarantined, not a veto against two
    # independently attributable primary documents. Conversely, a strong
    # vessel ID from an invalid URL cannot launder two name-only reports.
    for claim in valid:
        if not _canonical_source_url(claim.source_url):
            contradictions.append("invalid_source_url:" + claim.claim_id)
    attributable_strong_identity = any(
        _identity_match(subject, claim.vessel) == "strong"
        and bool((claim.origin_report_id or "").strip())
        and bool(claim.source_group.strip())
        and bool(_canonical_source_url(claim.source_url))
        for claim in valid
    )
    # Very coarse incident times or locations must not turn unrelated
    # attacks into two-source corroboration. Keep such claims in the audit
    # evidence, but only precision-qualified originals can promote an event.
    # A missing coordinate is not a fabricated zero-uncertainty fix: it
    # remains unlocated and is assessed by the independent source review.
    max_time_uncertainty = 360 if anchor.kind == "sinking" else 180
    precise_claims = [
        claim for claim in valid
        if claim.time_uncertainty_minutes <= max_time_uncertainty
        and (claim.lat is None or claim.uncertainty_km <= 250)
    ]
    precision_groups = _independent_document_groups(precise_claims, lineage_roots)
    # The canonical PostgreSQL provenance audit requires publication AND
    # reception chronology. Apply the same fail-closed rule here: a report
    # with unknown ingestion time remains visible as evidence, but cannot
    # supply one of the two independent corroborating origins. Do not invent
    # a publication clock time from a date-only press release.
    chronology_claims = [
        claim for claim in precise_claims
        if claim.published_at is not None and claim.received_at is not None
    ]
    precise_groups = _independent_document_groups(chronology_claims, lineage_roots)
    precise_strong_identity = any(
        _identity_match(subject, claim.vessel) == "strong"
        and bool((claim.origin_report_id or "").strip())
        and bool(claim.source_group.strip())
        and bool(_canonical_source_url(claim.source_url))
        for claim in chronology_claims
    )
    if len(groups) >= 2 and len(precision_groups) < 2:
        contradictions.append("corroboration_precision_insufficient")
    if len(precision_groups) >= 2 and len(precise_groups) < 2:
        contradictions.append("corroboration_chronology_incomplete")
    corroborated = len(precise_groups) >= 2 and precise_strong_identity
    status = "corroborated" if corroborated else "candidate"
    color = (_COLORS.get(anchor.kind, _COLORS["other"]) if corroborated else _COLORS["candidate"])
    support = ["incident_claim", "vessel_identity_matched"]
    if strong_identity:
        support.append("strong_vessel_identifier")
    if len(precise_groups) >= 2:
        support.append("independent_source_groups")

    # Invalid AIS telemetry must not become supporting evidence or bypass
    # distance checks (NaN comparisons are otherwise always false).
    valid_ais_fixes: list[AISFix] = []
    for fix in ais_fixes:
        if (
            not isfinite(fix.lat) or not isfinite(fix.lon)
            or not -90 <= fix.lat <= 90 or not -180 <= fix.lon <= 180
        ):
            contradictions.append("invalid_ais_fix_coordinates")
            continue
        try:
            observed_at = _utc(fix.observed_at)
            if fix.received_at is not None:
                received_at = _utc(fix.received_at)
                # Small receiver clock skew is tolerated; a position that
                # claims to occur >5 min after receipt cannot corroborate
                # spatial context or a sudden stop. Do not infer spoofing.
                if (observed_at - received_at).total_seconds() > 300:
                    contradictions.append("ais_fix_future_relative_to_receipt")
                    continue
        except (ValueError, TypeError, AttributeError):
            contradictions.append("invalid_ais_fix_timestamp")
            continue
        valid_ais_fixes.append(fix)

    nearest: tuple[float, float] | None = None
    # A valid IMO match does not validate an unrelated/placeholder MMSI.
    if _valid_mmsi(subject.mmsi):
        for claim in valid:
            if claim.lat is None or claim.lon is None:
                continue
            for fix in valid_ais_fixes:
                if fix.mmsi != subject.mmsi:
                    continue
                minutes = abs((_utc(fix.observed_at) - _utc(claim.occurred_at)).total_seconds()) / 60
                if minutes > 120:
                    continue
                distance = _km(fix.lat, fix.lon, claim.lat, claim.lon)
                if distance > 30 + claim.uncertainty_km:
                    continue
                if nearest is None or (minutes, distance) < (nearest[1], nearest[0]):
                    nearest = (distance, minutes)
    # Contradictory AIS is not proof an attack did not occur: it may be
    # spoofed or replayed. Flag it and require human review instead.
    ais_spatial_conflict = False
    # A valid IMO match does not validate an unrelated/placeholder MMSI.
    if _valid_mmsi(subject.mmsi):
        for claim in valid:
            if claim.lat is None or claim.lon is None:
                continue
            for fix in valid_ais_fixes:
                if fix.mmsi != subject.mmsi:
                    continue
                offset = abs((_utc(fix.observed_at) - _utc(claim.occurred_at)).total_seconds()) / 60
                if offset <= 30 + claim.time_uncertainty_minutes:
                    if _km(fix.lat, fix.lon, claim.lat, claim.lon) > 100 + claim.uncertainty_km:
                        ais_spatial_conflict = True
    if ais_spatial_conflict:
        contradictions.append("ais_position_conflict_needs_review")
        status = "candidate"
        color = _COLORS["candidate"]
    if nearest is not None:
        support.append("ais_spatiotemporal_context_not_attack_proof")

    # Gap signals only add context if temporally proximate; never upgrade status.
    valid_gap_ids: set[str] = set()
    for gap in ais_gaps:
        if not _valid_mmsi(subject.mmsi) or gap.mmsi != subject.mmsi:
            continue
        try:
            gap_time = _utc(gap.observed_at)
        except (ValueError, TypeError, AttributeError):
            contradictions.append("invalid_ais_gap_timestamp:" + gap.event_id)
            continue
        if abs((gap_time - _utc(anchor.occurred_at)).total_seconds()) <= 6 * 3600:
            valid_gap_ids.add(gap.event_id)
    gap_ids = tuple(sorted(valid_gap_ids))
    if gap_ids:
        support.append("proximate_ais_gap_context_not_attack_proof")

    # A sharp speed reduction is an AIS *context signal*, not an attack
    # observation. Require two valid, same-MMSI fixes bracketing a precisely
    # timed incident; rule out long sampling gaps and implausible position
    # jumps. Port approaches, weather, spoofing and operational manoeuvres
    # remain alternative explanations. No status/group/promotion changes.
    stop_pairs: set[tuple[str, str]] = set()
    if _valid_mmsi(subject.mmsi):
        speed_fixes: list[AISFix] = []
        for fix in valid_ais_fixes:
            if fix.mmsi != subject.mmsi or fix.sog_knots is None:
                continue
            if (not isinstance(fix.sog_knots, (int, float))
                    or isinstance(fix.sog_knots, bool)
                    or not isfinite(fix.sog_knots)
                    or not 0 <= fix.sog_knots <= 70):
                contradictions.append("invalid_ais_speed")
                continue
            speed_fixes.append(fix)
        for claim in valid:
            if claim.time_uncertainty_minutes > 30:
                continue
            event_time = _utc(claim.occurred_at)
            before = [fix for fix in speed_fixes
                      if fix.sog_knots >= 5
                      and 0 < (event_time - _utc(fix.observed_at)).total_seconds() <= 30 * 60]
            after = [fix for fix in speed_fixes
                     if fix.sog_knots <= 1.5
                     and 0 < (_utc(fix.observed_at) - event_time).total_seconds() <= 90 * 60]
            if not before or not after:
                continue
            previous = max(before, key=lambda fix: _utc(fix.observed_at))
            following = min(after, key=lambda fix: _utc(fix.observed_at))
            if not 120 <= (_utc(following.observed_at) - _utc(previous.observed_at)).total_seconds() <= 90 * 60:
                continue
            if previous.sog_knots - following.sog_knots < 5:
                continue
            if _km(previous.lat, previous.lon, following.lat, following.lon) > 15:
                continue
            if claim.lat is not None and any(
                _km(fix.lat, fix.lon, claim.lat, claim.lon) > 30 + claim.uncertainty_km
                for fix in (previous, following)
            ):
                continue
            stop_pairs.add((_utc(previous.observed_at).isoformat(),
                            _utc(following.observed_at).isoformat()))
    stop_context = tuple(sorted(stop_pairs))[:8]
    if stop_context:
        support.append("ais_sudden_stop_context_not_attack_proof")
    return Correlation(
        status, anchor.kind, color,
        tuple(claim.claim_id for claim in valid), groups,
        tuple(support), tuple(contradictions),
        nearest[0] if nearest else None,
        nearest[1] if nearest else None,
        gap_ids,
        tuple({
            "claim_id": claim.claim_id,
            "source_url": claim.source_url,
            "source_group": claim.source_group,
            "origin_report_id": claim.origin_report_id,
            "lineage_root": lineage_roots.get(claim.claim_id, claim.claim_id),
            "time_uncertainty_minutes": str(claim.time_uncertainty_minutes),
            "lat": str(claim.lat) if claim.lat is not None else None,
            "lon": str(claim.lon) if claim.lon is not None else None,
            "uncertainty_km": str(claim.uncertainty_km),
            "occurred_at": _utc(claim.occurred_at).isoformat(),
            "published_at": (_utc(claim.published_at).isoformat()
                             if claim.published_at is not None else None),
            "received_at": (_utc(claim.received_at).isoformat()
                            if claim.received_at is not None else None),
        } for claim in valid),
        related_sudden_stop_fixes=stop_context,
    )
