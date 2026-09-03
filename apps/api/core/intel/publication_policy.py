# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical publication policy layer (docs/fixes.md M9).

**Goal: one publication decision, multiple safe projections.** Six named
targets, each a pure filter over the same canonical record shape (a plain
dict, the same properties/metadata shape already used across
core.intel.store/core.live.vessel_episodes -- no new wrapper type to keep
in sync with everything else):

    analyst_private | analyst_shareable | public_humanitarian |
    public_safety | public_maritime_assessed | edge_humanitarian

"The edge must consume the same projection/policy semantics, not a copied
rule set" is satisfied structurally, not by convention: ``edge_humanitarian``
is a plain alias for ``project_public_humanitarian`` (the literal same
function object, not a re-implementation) at the bottom of this module.

This module is pure and standalone: it reads a caller-supplied record
dict and, for the Intelligence gate, an optional
``core.intel.hypothesis.InvestigationHypothesis`` (M6) -- it does not
query IntelEventDB, IntelStore, or any live source itself. Wiring this
into the actual API response / edge publisher is a separate, later PR.
"""
from __future__ import annotations

from typing import Any, Optional

from core.intel.hypothesis import InvestigationHypothesis, can_publish

# Fields that never leave the analyst_private tier under any circumstance:
# direct source identity/content an analyst needs to investigate but that
# is never appropriate to publish, shareable or not (raw caller text,
# an internal analyst-only note).
_ANALYST_ONLY_FIELDS = frozenset({"raw_private_text", "internal_note"})

# "no MMSI/IMO/tracker dossiers" (Public Humanitarian, M9 verbatim).
_VESSEL_IDENTITY_FIELDS = frozenset({"linked_mmsi", "mmsi", "imo", "tracker_dossier"})

_PUBLIC_HUMANITARIAN_ALLOWED_FIELDS = frozenset(
    {
        "id", "title", "public_summary", "category", "is_alarm_phone_red",
        "incident_lifecycle", "lat", "lon", "location_precision",
        "location_uncertainty_m", "people_reported", "people_precision",
        "source_updates", "resolution_state", "timestamp_utc",
    }
)


def _strip_to(record: dict[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k in allowed}


def project_analyst(record: dict[str, Any], *, shareable: bool) -> dict[str, Any]:
    """``analyst_private``: everything, unfiltered. ``analyst_shareable``
    (``shareable=True``): everything except _ANALYST_ONLY_FIELDS -- an
    analyst can still see MMSI/IMO/dossiers/drift/hypothesis detail, just
    not the fields that are never appropriate outside the direct
    investigating team."""
    if not shareable:
        return dict(record)
    return {k: v for k, v in record.items() if k not in _ANALYST_ONLY_FIELDS}


def project_public_humanitarian(record: dict[str, Any]) -> dict[str, Any]:
    """Public Humanitarian (M9 rules, verbatim):
    - no MMSI/IMO/tracker dossiers;
    - Alarm Phone semantic red category retained;
    - location precision/uncertainty explicit;
    - lifecycle explicit;
    - raw private caller text excluded;
    - Drift only from canonical persisted backend result.
    """
    projected = _strip_to(record, _PUBLIC_HUMANITARIAN_ALLOWED_FIELDS)
    # "Drift only from canonical persisted backend result": a drift
    # projection is included only when it carries drift_job_id -- the
    # marker that it came from an actual persisted DriftResultDB row
    # (core.db.store), never an ad-hoc/unpersisted client-side
    # computation. record's own vessel-identity/raw-text fields are
    # already excluded above by the allow-list, not by a separate
    # denylist step -- there is no path for them to leak back in.
    if record.get("drift_job_id"):
        projected["drift_job_id"] = record["drift_job_id"]
        projected["drift_geometry"] = record.get("drift_geometry")
    return projected


def project_public_safety(record: dict[str, Any]) -> dict[str, Any]:
    """Public Maritime / Safety half: "neutral Safety can publish without
    allegation" -- no hypothesis or publication gate applies to a Safety-
    lane record at all; it is observation, not an intelligence
    allegation. Still separates observation from interpretation and
    strips vessel-identity dossier fields (a Safety anomaly is about a
    behaviour, not a public dossier on the vessel)."""
    projected = {k: v for k, v in record.items() if k not in _VESSEL_IDENTITY_FIELDS | _ANALYST_ONLY_FIELDS}
    projected["observation"] = record.get("observation_text", "")
    projected["interpretation"] = record.get("interpretation_text", "")
    projected["evidence_stage"] = record.get("evidence_stage", "observed")
    projected["caveats"] = tuple(record.get("caveats") or ())
    return projected


def project_public_maritime_assessed(
    record: dict[str, Any], *, hypothesis: Optional[InvestigationHypothesis] = None,
) -> Optional[dict[str, Any]]:
    """Public Maritime / assessed-Intelligence half: "Intelligence
    hypotheses only after publication gate" -- returns None (nothing
    publishable) when a hypothesis is attached but hasn't passed
    core.intel.hypothesis.can_publish() (M6). A record with NO hypothesis
    at all (a neutral Safety-lane record) belongs to
    project_public_safety() above, not this function -- this one is
    specifically for records that ARE an intelligence allegation, which
    by definition must clear the gate.

    "Official sanctions facts cite the authoritative list" -- any
    sanctions entry missing a source_list citation is dropped rather than
    published uncited.
    """
    if hypothesis is not None:
        ok, _reason = can_publish(hypothesis)
        if not ok:
            return None

    projected = {k: v for k, v in record.items() if k not in _VESSEL_IDENTITY_FIELDS | _ANALYST_ONLY_FIELDS}
    projected["observation"] = record.get("observation_text", "")
    projected["interpretation"] = record.get("interpretation_text", "")
    projected["evidence_stage"] = record.get("evidence_stage", "observed")
    projected["caveats"] = tuple(record.get("caveats") or ())
    projected["sanctions"] = tuple(
        s for s in (record.get("sanctions") or ()) if isinstance(s, dict) and s.get("source_list")
    )
    if hypothesis is not None:
        projected["reason_codes"] = tuple(hypothesis.reason_codes)
        projected["hypothesis_type"] = hypothesis.hypothesis_type
    return projected


# "The edge must consume the same projection/policy semantics, not a
# copied rule set" -- the literal same function object, not a re-
# implementation with its own drift.
edge_humanitarian = project_public_humanitarian


_TARGETS = frozenset(
    {
        "analyst_private", "analyst_shareable", "public_humanitarian",
        "public_safety", "public_maritime_assessed", "edge_humanitarian",
    }
)


def project(
    record: dict[str, Any], *, target: str, hypothesis: Optional[InvestigationHypothesis] = None,
) -> Optional[dict[str, Any]]:
    """Single dispatch entry point across all six targets. Raises
    ValueError for an unrecognised target -- never silently falls back to
    a wrong (and possibly less restrictive) projection."""
    if target not in _TARGETS:
        raise ValueError(f"unknown publication target: {target!r}")
    if target == "analyst_private":
        return project_analyst(record, shareable=False)
    if target == "analyst_shareable":
        return project_analyst(record, shareable=True)
    if target in ("public_humanitarian", "edge_humanitarian"):
        return project_public_humanitarian(record)
    if target == "public_safety":
        return project_public_safety(record)
    return project_public_maritime_assessed(record, hypothesis=hypothesis)
