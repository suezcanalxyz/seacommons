# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging-only guard: an outcome can reference only a REAL canonical attack episode.

No new episode store, publication path, database write, migration, scheduler,
or production side effect. An operator's link ID is not evidence of existence.
The caller must provide a read-only SQLAlchemy session for the optional adapter.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from core.intel.maritime_attack_correlation import (
    Correlation, IncidentClaim, VesselRef, _utc, _valid_imo, _valid_mmsi,
)
from core.intel.maritime_attack_outcomes import (
    OutcomeAssociation, ReviewedOutcomeLink, reconcile_reported_sinking,
)

# Closed allowlist: never treat an AIS gap, distress/drift or generic safety
# episode as an already-established hostile attack.
_ATTACK_FAMILIES = frozenset({"attack_episode", "maritime_attack_episode", "maritime_attack"})


def _reject(link: ReviewedOutcomeLink, reason: str) -> OutcomeAssociation:
    return OutcomeAssociation("rejected", link.attack_episode_id, "", "", "", (reason,))


def _db_utc(value: object) -> datetime:
    """The canonical MaritimeEpisodeDB stores DateTime without timezone.

    Interpret only this *database* field as UTC. Event/report timestamps must
    remain explicitly timezone-aware in the incident claims.
    """
    if not isinstance(value, datetime):
        raise ValueError("Missing canonical episode timestamp")
    return _utc(value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value)


def _episode_vessel_matches(subject: VesselRef, raw_ids: object) -> bool:
    """Require a shared strong ship ID, and veto any contradictory strong ID."""
    if not isinstance(raw_ids, (list, tuple)) or not raw_ids:
        return False
    matches = 0
    for raw in raw_ids:
        if not isinstance(raw, str):
            return False
        token = raw.strip().lower()
        if token.startswith("imo:"):
            identifier = token[4:].strip()
            if not _valid_imo(identifier) or (subject.imo and subject.imo != identifier):
                return False
            matches += int(subject.imo == identifier)
        elif token.startswith("mmsi:"):
            identifier = token[5:].strip()
            if not _valid_mmsi(identifier) or (subject.mmsi and subject.mmsi != identifier):
                return False
            matches += int(subject.mmsi == identifier)
        # Other subject keys are not ship-identity evidence.
    return matches > 0


def reconcile_against_existing_episode(
    subject: VesselRef,
    attack: IncidentClaim,
    sinking: IncidentClaim,
    attack_correlation: Correlation,
    sinking_correlation: Correlation,
    link: ReviewedOutcomeLink,
    episode: object | None,
) -> OutcomeAssociation:
    """Validate the actual persisted episode before reconciling an outcome.

    This prevents an arbitrary operator-supplied episode ID from becoming a
    seemingly corroborated sinking update. No historical row is changed.
    """
    if episode is None:
        return _reject(link, "existing_attack_episode_not_found")
    if str(getattr(episode, "episode_id", "") or "") != link.attack_episode_id:
        return _reject(link, "canonical_episode_id_mismatch")
    if str(getattr(episode, "episode_family", "") or "") not in _ATTACK_FAMILIES:
        return _reject(link, "canonical_episode_not_attack")
    if str(getattr(episode, "status", "") or "") not in {"active", "resolved"}:
        return _reject(link, "canonical_episode_inactive")
    if not str(getattr(episode, "evidence_fingerprint", "") or "").strip():
        return _reject(link, "canonical_episode_missing_fingerprint")
    observations = getattr(episode, "observation_ids", None)
    if not isinstance(observations, (list, tuple)) or attack.claim_id not in observations:
        return _reject(link, "attack_claim_not_in_canonical_episode")
    if not _episode_vessel_matches(subject, getattr(episode, "subject_ids", None)):
        return _reject(link, "canonical_episode_vessel_mismatch")
    try:
        start = _db_utc(getattr(episode, "start_at", None))
        end = _db_utc(getattr(episode, "end_at", None))
        attack_time = _utc(attack.occurred_at)
        if end < start:
            return _reject(link, "canonical_episode_invalid_window")
        tolerance = 90 * 60 + attack.time_uncertainty_minutes * 60
        if not (start.timestamp() - tolerance <= attack_time.timestamp()
                <= end.timestamp() + tolerance):
            return _reject(link, "attack_outside_canonical_episode_window")
    except (ValueError, TypeError, OverflowError, AttributeError):
        return _reject(link, "canonical_episode_invalid_window")
    return reconcile_reported_sinking(
        subject, attack, sinking, attack_correlation, sinking_correlation, link,
    )


def reconcile_against_db_episode(
    subject: VesselRef,
    attack: IncidentClaim,
    sinking: IncidentClaim,
    attack_correlation: Correlation,
    sinking_correlation: Correlation,
    link: ReviewedOutcomeLink,
    db: object,
) -> OutcomeAssociation:
    """Opt-in bounded SELECT on MaritimeEpisodeDB using a caller-owned session.

    DB failures intentionally propagate; never substitute a synthetic episode.
    The caller must enforce a read-only transaction and suitable DB permissions.
    """
    from core.db.models import MaritimeEpisodeDB

    episode = (
        db.query(MaritimeEpisodeDB)
        .filter(MaritimeEpisodeDB.episode_id == link.attack_episode_id)
        .limit(1)
        .one_or_none()
    )
    return reconcile_against_existing_episode(
        subject, attack, sinking, attack_correlation, sinking_correlation, link, episode,
    )
