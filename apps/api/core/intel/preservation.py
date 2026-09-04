# SPDX-License-Identifier: AGPL-3.0-or-later
"""Preservation and evidentiary provenance (docs/updates.md Section 6).

**Goal:** "For public web/social evidence, preserve enough to verify
what the platform observed at collection time where terms/law/privacy
permit" -- and "Preservation and public publication are separate
policies", with Humanitarian material specifically requiring
segregation ("minimize retained personal identifiers; segregate
restricted artifacts; make retention policy explicit").

v0 scope, honestly bounded: ``core.intel.source_observation.
SourceObservationDB`` already *is* the codebase's one canonical,
immutable, lossless raw-observation record (docs/fixes.md M1.1) --
Section 6's field list (canonical URL/platform id, publisher id,
publication timestamp, retrieved_at, raw text, thread/parent relations
via ``subject_refs``, HTTP/source metadata via ``provenance``) is
already substantially covered by it; this module does not duplicate
that with a second parallel table (docs/updates.md invariant #17: "one
authoritative path per concept").

What was genuinely missing is an explicit, queryable preservation
POLICY classification per observation -- this module adds exactly
that: ``classify_preservation_status`` is a pure function of
(service, has_archive_ref), wired into ``record_observation()`` at
write time and stored once, immutably, alongside the row it classifies
(SourceObservationDB.preservation_status). Humanitarian-service
observations are always classified "restricted" regardless of whether
an archive reference exists -- the segregation Section 6 asks for,
enforced structurally rather than left to a caller's discretion.

Known non-goal, named explicitly rather than silently skipped: this
packet does NOT build an actual archiver (fetching and durably storing
raw media/text bytes, computing content hashes, producing an archive
URI). No adapter in this codebase populates ``raw_payload_ref`` today,
so every real observation classifies as "not_applicable" in practice
until a future packet adds real archival capture -- a genuinely bigger
undertaking needing a storage backend and an explicit legal/retention
review this module does not invent.
"""
from __future__ import annotations

STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_PRESERVED = "preserved"
STATUS_RESTRICTED = "restricted"


def classify_preservation_status(service: str, has_archive_ref: bool) -> str:
    """Deterministic preservation-policy classification for one
    observation, computed once at write time:
      - no archive reference at all -> not_applicable (nothing was
        preserved for this observation; most observations today, since
        no adapter populates raw_payload_ref yet).
      - service == "humanitarian" -> restricted, regardless of whether
        an archive reference exists -- sensitive Humanitarian material
        is always segregated, never defaulted to the general
        "preserved" bucket (docs/updates.md Section 6: "segregate
        restricted artifacts").
      - otherwise, with an archive reference -> preserved.
    """
    if not has_archive_ref:
        return STATUS_NOT_APPLICABLE
    if service == "humanitarian":
        return STATUS_RESTRICTED
    return STATUS_PRESERVED


def summarize_preservation_status(limit: int = 5000) -> dict[str, int]:
    """Real counts per preservation_status across recent
    SourceObservationDB rows -- the operator-facing answer to "what is
    actually preserved vs not" this packet's route exposes."""
    from core.db.models import SourceObservationDB
    from core.db.session import session_scope

    counts: dict[str, int] = {
        STATUS_NOT_APPLICABLE: 0, STATUS_PRESERVED: 0, STATUS_RESTRICTED: 0, "unclassified": 0,
    }
    with session_scope() as db:
        rows = (
            db.query(SourceObservationDB.preservation_status)
            .order_by(SourceObservationDB.received_at.desc())
            .limit(limit)
            .all()
        )
        for (status,) in rows:
            key = status if status in counts else "unclassified"
            counts[key] += 1
    return counts
