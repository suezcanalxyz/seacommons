# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded read-only proof of independent origins for staged attack episodes.

A persisted 'multi_source_corroborated' label and two group names are not
independent evidence. Reconcile actual SourceObservation provenance and
verified lineage before allowing PLAY to display an attack as corroborated.
No collectors, writes, migrations, publication or scheduler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable
from core.intel.maritime_attack_correlation import (
    _canonical_source_url, _lineage_components,
)
from core.intel.maritime_attack_lineage_readonly import load_verified_lineage
from core.intel.maritime_attack_play_guard import (
    _ATTACK_FAMILIES, has_distinct_independence_groups,
)


@dataclass(frozen=True)
class IndependenceAudit:
    verified: bool
    groups: tuple[str, ...] = ()
    reason: str = ""
    observations_checked: int = 0


def _source_url_key(value: object) -> str:
    """Use the same canonical URL rules as incident-claim deduplication.

    Retain report-identifying query parameters (e.g. ?id=123), but remove
    known tracking parameters and fragments. Dropping the entire query
    would incorrectly merge unrelated official reports served at one path.
    """
    return _canonical_source_url(str(value or ""))



def _utc_observation_time(value: object) -> datetime:
    """Parse canonical source times, treating legacy naive DB timestamps as UTC."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        raise ValueError("Missing or invalid observation timestamp")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _observation_chronology_issue(row: object) -> str:
    """Reject impossible event/publication/receipt ordering without DB writes.

    Legacy test fixtures may omit timestamps; canonical persisted observations
    carry observed_at and received_at. A five-minute clock-skew allowance
    avoids treating minor upstream clock drift as fabricated evidence.
    """
    observed_raw = getattr(row, "observed_at", None)
    received_raw = getattr(row, "received_at", None)
    if observed_raw is None and received_raw is None:
        return ""
    try:
        observed = _utc_observation_time(observed_raw)
        received = _utc_observation_time(received_raw)
    except (ValueError, TypeError, OverflowError):
        return "invalid_observation_chronology"
    tolerance = timedelta(minutes=5)
    if observed > received + tolerance:
        return "observation_after_receipt"
    provenance = getattr(row, "provenance", None)
    if isinstance(provenance, dict):
        published_raw = provenance.get("published_at_utc")
        if published_raw is None:
            published_raw = provenance.get("published_at")
        if published_raw is not None:
            try:
                published = _utc_observation_time(published_raw)
            except (ValueError, TypeError, OverflowError):
                return "invalid_publication_timestamp"
            if published > received + tolerance:
                return "publication_after_receipt"
    return ""


def audit_attack_episode_independence(
    episode: object,
    fetch_observations: Callable[[tuple[str, ...]], Iterable[object]],
    fetch_lineage: Callable[[tuple[str, ...]], Iterable[object]],
    *,
    max_observations: int = 32,
) -> IndependenceAudit:
    """Verify a selected episode's independent original reports, fail closed.

    Requires explicit, operator-verified origin metadata on every observation.
    The graph is read only from the supplied bounded fetchers. Different
    publishers of one original report or a verified derivation count once.
    """
    if str(getattr(episode, "episode_family", "") or "") not in _ATTACK_FAMILIES:
        return IndependenceAudit(False, reason="not_attack_episode")
    if (str(getattr(episode, "verification_status", "") or "") != "multi_source_corroborated"
            or not has_distinct_independence_groups(getattr(episode, "independence_groups", None))):
        return IndependenceAudit(False, reason="canonical_verification_incomplete")
    raw_ids = getattr(episode, "observation_ids", None)
    if not isinstance(raw_ids, (list, tuple)) or not 2 <= len(raw_ids) <= max_observations:
        return IndependenceAudit(False, reason="invalid_observation_count")
    if any(not isinstance(x, str) or not x.strip() for x in raw_ids):
        return IndependenceAudit(False, reason="invalid_observation_ids")
    ids = tuple(x.strip() for x in raw_ids)
    if len(set(ids)) != len(ids):
        return IndependenceAudit(False, reason="duplicate_observation_ids")
    rows = list(fetch_observations(ids))
    if len(rows) != len(ids):
        return IndependenceAudit(False, reason="missing_or_duplicate_observations", observations_checked=len(rows))
    by_id: dict[str, object] = {}
    for row in rows:
        key = str(getattr(row, "observation_id", "") or "").strip()
        if key not in ids or key in by_id:
            return IndependenceAudit(False, reason="unexpected_observation", observations_checked=len(rows))
        by_id[key] = row

    lineage = load_verified_lineage(ids, fetch_lineage)
    if not lineage.complete:
        return IndependenceAudit(False, reason=lineage.reason, observations_checked=len(rows))
    roots = _lineage_components(lineage.edges)
    parent = {key: key for key in ids}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    seen: dict[tuple[str, str], str] = {}
    for identifier in ids:
        row = by_id[identifier]
        chronology_issue = _observation_chronology_issue(row)
        if chronology_issue:
            return IndependenceAudit(False, reason=chronology_issue, observations_checked=len(rows))
        if str(getattr(row, "service", "") or "").casefold() == "humanitarian":
            return IndependenceAudit(False, reason="humanitarian_domain_excluded", observations_checked=len(rows))
        provenance = getattr(row, "provenance", None)
        if not isinstance(provenance, dict) or provenance.get("origin_authority_verified") is not True:
            return IndependenceAudit(False, reason="origin_not_verified", observations_checked=len(rows))
        authority = str(provenance.get("originating_authority_id") or "").strip().casefold()
        document = str(provenance.get("original_report_id") or "").strip().casefold()
        url = _source_url_key(getattr(row, "source_url", None))
        if not authority or not document or not url:
            return IndependenceAudit(False, reason="missing_original_provenance", observations_checked=len(rows))
        for key in (("authority", authority), ("document", document),
                    ("url", url), ("lineage", roots.get(identifier, identifier))):
            previous = seen.setdefault(key, identifier)
            union(identifier, previous)
    groups = tuple(sorted({find(identifier) for identifier in ids}))
    if len(groups) < 2:
        return IndependenceAudit(False, groups, "shared_original_source", len(rows))
    return IndependenceAudit(True, groups, observations_checked=len(rows))


def audit_attack_episode_independence_db(episode: object, db: object) -> IndependenceAudit:
    """Opt-in SQLAlchemy SELECTs, caller-owned read-only transaction only."""
    from core.db.models import LineageEdgeDB, SourceObservationDB

    def observations(ids: tuple[str, ...]) -> Iterable[object]:
        return (db.query(SourceObservationDB)
                .filter(SourceObservationDB.observation_id.in_(ids))
                .order_by(SourceObservationDB.observation_id)
                .limit(33).all())

    def lineage(frontier: tuple[str, ...]) -> Iterable[object]:
        return (db.query(LineageEdgeDB)
                .filter(LineageEdgeDB.from_observation_id.in_(frontier))
                .order_by(LineageEdgeDB.from_observation_id, LineageEdgeDB.to_observation_id)
                .limit(1025).all())

    return audit_attack_episode_independence(episode, observations, lineage)
