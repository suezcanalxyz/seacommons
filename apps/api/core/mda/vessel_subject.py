# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stable vessel-subject identity layer (docs/fixes.md M5.1).

**Goal (M5): stop equating one MMSI with one lifelong episode.** An MMSI is
a broadcast radio identity, not the vessel itself -- it can be reused,
spoofed, or (rarely, legitimately) reassigned. Everything in this
codebase so far (core.mda.watch.scan_identity, core.intel.ngo_registry,
SourceObservation.subject_refs) keys directly on MMSI. This module adds
the layer above that: a ``VesselSubject`` resolved from a chronological
list of raw sightings, carrying dated aliases (a vessel's name/flag/MMSI
across time, each with when it was observed and by what source) instead
of one mutable "current" name/flag pair.

Identity conflicts (a name or flag that changed between two sightings of
the same MMSI within a window too short for a legitimate re-flagging/
re-naming) become explicit ``IdentityConflict`` records on the subject --
never a silent overwrite of the previous alias. "Official sanctions match
is a fact linked to a subject/identity record, not an automatic behaviour
hypothesis" (M5.1) is ``sanctions_fact_for()``: it packages a sanctions
hit as a fact attached to the subject, and returns exactly that -- a
fact, never a hypothesis object, never a behaviour label.

v0 scope: pure, in-memory resolution over a caller-supplied observation
list -- no persistence yet (no ``VesselSubjectDB`` table). ``subject_id``
is IMO-based when an IMO is known (the closest thing to a genuine
persistent hull identity in the maritime domain -- IMO numbers are not
reassigned during a vessel's life), falling back to an MMSI-based id
otherwise. The MMSI-based fallback is a known, documented limitation: it
cannot itself detect or survive an MMSI reassignment between two
different real vessels -- closing that gap needs cross-referencing
callsign/name/flag continuity across the reassignment boundary, which is
M5.2 (bounded episode builder) territory, not this module.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.mda.identity import imo_check_digit_ok


def _clean_imo(imo: Any) -> Optional[str]:
    digits = re.sub(r"\D", "", str(imo or ""))
    return digits if len(digits) == 7 and imo_check_digit_ok(digits) else None


def _clean_mmsi(mmsi: Any) -> Optional[str]:
    digits = re.sub(r"\D", "", str(mmsi or ""))
    return digits if len(digits) == 9 else None


def subject_id_for(*, imo: Any = None, mmsi: Any = None) -> Optional[str]:
    """Deterministic subject id -- the same (imo, mmsi) input always
    resolves to the same id. IMO wins when present and check-digit valid;
    MMSI is the fallback. None when neither identifier is usable."""
    imo_clean = _clean_imo(imo)
    if imo_clean:
        return f"subj:imo:{imo_clean}"
    mmsi_clean = _clean_mmsi(mmsi)
    if mmsi_clean:
        return f"subj:mmsi:{mmsi_clean}"
    return None


@dataclass(frozen=True)
class IdentityAlias:
    mmsi: Optional[str]
    name: str
    flag: str
    observed_at: datetime
    source: str


@dataclass(frozen=True)
class IdentityConflict:
    field: str  # "name" | "flag" | "mmsi"
    previous_value: str
    new_value: str
    previous_observed_at: datetime
    new_observed_at: datetime
    source: str


@dataclass(frozen=True)
class VesselSubject:
    subject_id: str
    primary_mmsi: Optional[str]
    primary_imo: Optional[str]
    aliases: list[IdentityAlias] = field(default_factory=list)
    conflicts: list[IdentityConflict] = field(default_factory=list)


# A name/flag genuinely does change (sale, re-flagging, renaming) -- only
# a change observed faster than any real paperwork process moves is
# treated as a conflict worth flagging rather than an ordinary alias
# transition. Deliberately conservative (days, not hours): a false
# "conflict" on routine re-flagging is worse noise than missing a fast
# spoofed transition, which core.mda.watch's duplicate-MMSI/spoofing scans
# already cover from the AIS-message-pattern side independently.
_MIN_LEGITIMATE_CHANGE_GAP_S = 3 * 24 * 3600


def _detect_conflict(
    previous: IdentityAlias, current: IdentityAlias,
) -> Optional[IdentityConflict]:
    gap_s = (current.observed_at - previous.observed_at).total_seconds()
    if gap_s < 0:
        gap_s = -gap_s
    if gap_s >= _MIN_LEGITIMATE_CHANGE_GAP_S:
        return None
    for field_name, prev_value, new_value in (
        ("name", previous.name, current.name),
        ("flag", previous.flag, current.flag),
    ):
        if prev_value and new_value and prev_value != new_value:
            return IdentityConflict(
                field=field_name,
                previous_value=prev_value,
                new_value=new_value,
                previous_observed_at=previous.observed_at,
                new_observed_at=current.observed_at,
                source=current.source,
            )
    return None


def resolve_subject(observations: list[dict[str, Any]]) -> Optional[VesselSubject]:
    """Build a VesselSubject from a chronological list of raw sightings.

    Each observation: ``{mmsi, imo?, name, flag, observed_at, source}``.
    Returns None for an empty list or one where no observation carries a
    usable identifier. Callers own sorting the input chronologically --
    this never reorders, so a pre-sorted DB query result passes through
    unchanged.
    """
    if not observations:
        return None

    primary_imo = None
    aliases: list[IdentityAlias] = []
    conflicts: list[IdentityConflict] = []

    for obs in observations:
        imo_clean = _clean_imo(obs.get("imo"))
        mmsi_clean = _clean_mmsi(obs.get("mmsi"))
        if imo_clean and primary_imo is None:
            primary_imo = imo_clean

        alias = IdentityAlias(
            mmsi=mmsi_clean,
            name=str(obs.get("name") or ""),
            flag=str(obs.get("flag") or ""),
            observed_at=obs["observed_at"],
            source=str(obs.get("source") or ""),
        )
        if aliases:
            conflict = _detect_conflict(aliases[-1], alias)
            if conflict:
                conflicts.append(conflict)
        aliases.append(alias)

    primary_mmsi = next((a.mmsi for a in reversed(aliases) if a.mmsi), None)
    subject_id = subject_id_for(imo=primary_imo, mmsi=primary_mmsi)
    if subject_id is None:
        return None

    return VesselSubject(
        subject_id=subject_id,
        primary_mmsi=primary_mmsi,
        primary_imo=primary_imo,
        aliases=aliases,
        conflicts=conflicts,
    )


def sanctions_fact_for(subject: VesselSubject, sanctions_hits: list[dict[str, Any]]) -> dict[str, Any]:
    """docs/fixes.md M5.1: "Official sanctions match is a fact linked to a
    subject/identity record, not an automatic behaviour hypothesis." This
    packages the match as exactly that -- a fact dict with a subject
    reference -- and returns it unconditionally when hits are present;
    it never labels, scores, or infers a behaviour from the match. A
    caller that wants to reason about sanctions-evasion BEHAVIOUR needs
    independent corroborating evidence (docs/fixes.md M6
    sanctions_evasion_pattern gate) -- this function has no opinion on
    that at all.
    """
    return {
        "fact_type": "sanctions_list_match",
        "subject_id": subject.subject_id,
        "matches": list(sanctions_hits),
    }
