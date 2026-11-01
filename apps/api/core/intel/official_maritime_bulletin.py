# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opt-in, staging-only official maritime bulletin -> canonical SourceObservation.

This is an ingestion *adapter*, not a new database, poller, scheduler, public
feed, or attack classifier. Callers must already have legally obtained and
reviewed structured facts. No network requests or automatic PLAY promotion.
The originating reporting authority is deliberately UNVERIFIED: an issuing
NAVAREA/MSCIO authority may merely relay the same upstream report.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite
from urllib.parse import urlsplit

from core.intel.maritime_attack_correlation import _valid_imo, _valid_mmsi

# Exact host allowlist: never accept a user-supplied lookalike or URL redirect.
_ISSUERS = {
    "BG_MOD": ("Bulgarian Ministry of Defence", frozenset({"mod.bg", "www.mod.bg"})),
    "MSCIO": ("MSCIO", frozenset({"mscio.eu", "www.mscio.eu"})),
    "UKMTO": ("UKMTO", frozenset({"ukmto.org", "www.ukmto.org"})),
    "NAVAREA_IX": ("Pakistan NAVAREA IX", frozenset({"hydrography.paknavy.gov.pk"})),
}
_KINDS = frozenset({
    "attack", "sinking", "explosion", "collision", "piracy",
    "suspicious_activity", "navigational_hazard",
})
_LOCATION_ROLES = frozenset({"unknown", "incident_site", "anchorage", "last_reported_position", "hazard_position"})
_REPORT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 /._-]{0,79}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class OfficialMaritimeBulletin:
    issuer: str
    bulletin_id: str
    source_url: str
    kind: str
    vessel_name: str = ""
    imo: str = ""
    mmsi: str = ""
    occurred_at: datetime | None = None
    event_date: date | None = None
    published_at: datetime | None = None
    publication_date: date | None = None
    lat: float | None = None
    lon: float | None = None
    location_uncertainty_km: float | None = None
    location_role: str = "unknown"
    source_document_sha256: str = ""


def _utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Exact bulletin timestamps must include timezone")
    return value.astimezone(timezone.utc).isoformat()


def prepare_official_bulletin(bulletin: OfficialMaritimeBulletin) -> dict:
    """Validate source identity and create a metadata-only, replayable envelope.

    A day-only date is NEVER transformed into midnight with false precision.
    Unknown event time is never inferred from publication or receipt time.
    """
    if bulletin.issuer not in _ISSUERS:
        raise ValueError("Unknown official bulletin issuer")
    label, hosts = _ISSUERS[bulletin.issuer]
    if not _REPORT_ID.fullmatch(bulletin.bulletin_id.strip()):
        raise ValueError("Invalid original bulletin identifier")
    if bulletin.kind not in _KINDS:
        raise ValueError("Unsupported bulletin category")
    try:
        url = urlsplit(bulletin.source_url)
        if (url.scheme != "https" or url.hostname not in hosts or
                url.username is not None or url.password is not None or
                url.port not in (None, 443) or not url.path.startswith("/")):
            raise ValueError("Bulletin URL is not an approved official HTTPS origin")
    except (ValueError, AttributeError) as exc:
        raise ValueError("Invalid official bulletin URL") from exc
    if bulletin.imo and not _valid_imo(bulletin.imo):
        raise ValueError("Invalid IMO")
    if bulletin.mmsi and not _valid_mmsi(bulletin.mmsi):
        raise ValueError("Invalid MMSI")
    if bulletin.occurred_at is not None and bulletin.event_date is not None:
        raise ValueError("Choose exact event time OR day-only event date")
    if bulletin.published_at is not None and bulletin.publication_date is not None:
        raise ValueError("Choose exact publication time OR day-only publication date")
    if bulletin.event_date is not None and type(bulletin.event_date) is not date:
        raise ValueError("Invalid event date")
    if bulletin.publication_date is not None and type(bulletin.publication_date) is not date:
        raise ValueError("Invalid publication date")
    event_at = _utc(bulletin.occurred_at) if bulletin.occurred_at else None
    published_at = _utc(bulletin.published_at) if bulletin.published_at else None
    if (bulletin.lat is None) != (bulletin.lon is None):
        raise ValueError("Coordinates must be supplied together")
    if bulletin.lat is not None and (
        not isfinite(bulletin.lat) or not isfinite(bulletin.lon)
        or not -90 <= bulletin.lat <= 90 or not -180 <= bulletin.lon <= 180
    ):
        raise ValueError("Invalid coordinates")
    uncertainty = bulletin.location_uncertainty_km
    if uncertainty is not None and (not isfinite(uncertainty) or uncertainty < 0):
        raise ValueError("Invalid location uncertainty")
    if uncertainty is not None and bulletin.lat is None:
        raise ValueError("Uncertainty without a position")
    if bulletin.location_role not in _LOCATION_ROLES:
        raise ValueError("Invalid reported location role")
    if bulletin.lat is not None and bulletin.location_role == "unknown":
        raise ValueError("Coordinates require a documented location role")
    if bulletin.lat is None and bulletin.location_role != "unknown":
        raise ValueError("Location role without coordinates")
    if bulletin.source_document_sha256 and not _SHA256.fullmatch(bulletin.source_document_sha256):
        raise ValueError("Invalid original-document SHA256")
    facts = {
        "issuer": bulletin.issuer,
        "original_report_id": bulletin.issuer + ":" + bulletin.bulletin_id.strip(),
        "source_url": bulletin.source_url,
        "kind": bulletin.kind,
        "vessel_name": bulletin.vessel_name.strip(),
        "imo": bulletin.imo,
        "mmsi": bulletin.mmsi,
        "occurred_at_utc": event_at,
        "event_date": bulletin.event_date.isoformat() if bulletin.event_date else None,
        "published_at_utc": published_at,
        "publication_date": bulletin.publication_date.isoformat() if bulletin.publication_date else None,
        "lat": bulletin.lat,
        "lon": bulletin.lon,
        "location_uncertainty_km": uncertainty,
        "location_role": bulletin.location_role,
        "source_document_sha256": bulletin.source_document_sha256.lower() or None,
    }
    payload = json.dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    revision = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    # The canonical DB requires observed_at. A missing event clock stays
    # explicitly labelled; use a known publication clock/date if available.
    observed = (event_at or facts["event_date"] or published_at or
                facts["publication_date"])
    return {
        "service": "maritime",
        "lane": "safety",
        "observation_type": "official_maritime_bulletin",
        "source_name": label,
        "source_policy": "official_bulletin_metadata_only_reuse_unverified",
        "source_id": facts["original_report_id"] + ":" + revision,
        "source_url": bulletin.source_url,
        "observed_at": observed,
        "raw_payload": payload,
        "lat": bulletin.lat,
        "lon": bulletin.lon,
        "uncertainty_m": uncertainty * 1000 if uncertainty is not None else None,
        "subject_refs": ([f"imo:{bulletin.imo}"] if bulletin.imo else []) +
                        ([f"mmsi:{bulletin.mmsi}"] if bulletin.mmsi else []),
        "provenance": {
            "original_report_id": facts["original_report_id"],
            # Immutable identity extracted from the reviewed original bulletin.
            # Later model extraction must not invent or replace IMO/MMSI/name.
            "vessel_imo": bulletin.imo,
            "vessel_mmsi": bulletin.mmsi,
            "vessel_name": bulletin.vessel_name.strip(),
            "bulletin_kind": bulletin.kind,
            "occurred_at_utc": event_at,
            "location_role": bulletin.location_role,
            "originating_authority_id": bulletin.issuer,
            "origin_authority_verified": False,
            "publication_date": facts["publication_date"],
            "published_at_utc": published_at,
            "event_date": facts["event_date"],
            "event_time_precision": ("exact" if event_at else
                                     "day" if bulletin.event_date else "unknown"),
            "observed_at_semantics": ("event" if event_at or bulletin.event_date else
                                      "publication" if observed else "unknown"),
            "original_document_sha256": facts["source_document_sha256"],
            "reuse_rights_verified": False,
            "extraction_review_required": True,
            "attack_corroboration_allowed": False,
        },
    }


def ingest_official_bulletin(db: object, bulletin: OfficialMaritimeBulletin):
    """Explicit staging-only call, in the caller's transaction; no commit.

    If neither an event date nor a publication date is known, reject rather
    than invent an observation timestamp. A reviewed, newer document revision
    becomes a new immutable SourceObservation, never an overwrite.
    """
    prepared = prepare_official_bulletin(bulletin)
    if prepared["observed_at"] is None:
        raise ValueError("No reliable event or publication date for observation")
    from core.intel.source_observation import record_observation
    return record_observation(db, **prepared)
