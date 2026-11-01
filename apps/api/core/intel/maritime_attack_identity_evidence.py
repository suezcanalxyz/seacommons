# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging-only vessel identity linkage without contaminating original reports.

An authority's incident report may name a ship without printing its IMO/MMSI.
An independently sourced registry identity is a *separate* reviewed assertion,
not a correction to the report and never an independent attack witness.
Pure functions: no database, network, scheduling or publication side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from core.intel.maritime_attack_correlation import (
    VesselRef, _canonical_source_url, _name, _utc, _valid_imo, _valid_mmsi,
)
from core.intel.official_maritime_bulletin import (
    OfficialMaritimeBulletin, prepare_official_bulletin,
)


@dataclass(frozen=True)
class ExternalVesselIdentity:
    """A separately reviewed registry/ship-identity record, not an attack report."""
    source_record_id: str
    source_url: str
    vessel_name: str
    imo: str = ""
    mmsi: str = ""
    published_at: datetime | None = None
    received_at: datetime | None = None
    reviewed_by: str = ""


@dataclass(frozen=True)
class VesselIdentityLink:
    status: str  # linked_for_review | blocked
    original_report_id: str
    vessel: VesselRef
    evidence_record_ids: tuple[str, ...] = ()
    evidence_urls: tuple[str, ...] = ()
    reason: str = ""
    # Identity metadata cannot corroborate an attack or authorize publication.
    attack_corroboration_allowed: bool = False
    publication_allowed: bool = False


def link_external_vessel_identity(
    bulletin: OfficialMaritimeBulletin,
    evidence: Sequence[ExternalVesselIdentity],
) -> VesselIdentityLink:
    """Link ship IDs to a named bulletin only when all reviewed records agree.

    The original bulletin is NEVER rewritten, and its provenance remains
    exactly as extracted from the primary document. A verified vessel identity
    does not verify the incident, origin independence, or the alleged attacker.
    """
    original = prepare_official_bulletin(bulletin)
    report_id = original["provenance"]["original_report_id"]
    source_name = bulletin.vessel_name.strip()
    original_ref = VesselRef(bulletin.imo, bulletin.mmsi, source_name)

    def blocked(reason: str) -> VesselIdentityLink:
        return VesselIdentityLink("blocked", report_id, original_ref, reason=reason)

    if not source_name:
        return blocked("bulletin_has_no_vessel_name")
    if not evidence or len(evidence) > 8:
        return blocked("invalid_identity_evidence_batch")

    original_url = _canonical_source_url(bulletin.source_url)
    records: dict[str, ExternalVesselIdentity] = {}
    seen_urls: set[str] = set()
    for record in evidence:
        if not isinstance(record, ExternalVesselIdentity):
            return blocked("invalid_identity_evidence")
        key = record.source_record_id.strip()
        url = _canonical_source_url(record.source_url)
        if (not key or len(key) > 128 or key in records
                or not url or url == original_url or url in seen_urls):
            return blocked("invalid_or_duplicate_identity_provenance")
        if not record.reviewed_by.strip():
            return blocked("identity_evidence_not_reviewed")
        if not record.vessel_name.strip() or _name(record.vessel_name) != _name(source_name):
            return blocked("vessel_name_mismatch")
        if (not (record.imo or record.mmsi)
                or record.imo and not _valid_imo(record.imo)
                or record.mmsi and not _valid_mmsi(record.mmsi)):
            return blocked("invalid_identity_identifier")
        if record.received_at is None:
            return blocked("identity_receipt_clock_missing")
        try:
            received = _utc(record.received_at)
            if record.published_at is not None and (
                _utc(record.published_at) - received > timedelta(minutes=5)
            ):
                return blocked("identity_publication_after_receipt")
        except (TypeError, ValueError, AttributeError):
            return blocked("invalid_identity_timestamp")
        if bulletin.imo and record.imo and bulletin.imo != record.imo:
            return blocked("original_imo_conflict")
        if bulletin.mmsi and record.mmsi and bulletin.mmsi != record.mmsi:
            return blocked("original_mmsi_conflict")
        records[key] = record
        seen_urls.add(url)

    imos = {r.imo for r in records.values() if r.imo}
    mmsis = {r.mmsi for r in records.values() if r.mmsi}
    if len(imos) > 1 or len(mmsis) > 1:
        return blocked("conflicting_external_identifiers")
    resolved_imo = bulletin.imo or next(iter(imos), "")
    resolved_mmsi = bulletin.mmsi or next(iter(mmsis), "")
    if not resolved_imo and not resolved_mmsi:
        return blocked("no_resolved_identifier")
    ordered = sorted(records.items())
    return VesselIdentityLink(
        status="linked_for_review",
        original_report_id=report_id,
        vessel=VesselRef(resolved_imo, resolved_mmsi, source_name),
        evidence_record_ids=tuple(key for key, _ in ordered),
        evidence_urls=tuple(_canonical_source_url(record.source_url)
                            for _, record in ordered),
    )
