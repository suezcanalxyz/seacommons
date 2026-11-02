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
from core.intel.maritime_attack_navwarn_dtg import parse_navwarn_compact_dtg

# Exact host allowlist: never accept a user-supplied lookalike or URL redirect.
_ISSUERS = {
    "BG_MOD": ("Bulgarian Ministry of Defence", frozenset({"mod.bg", "www.mod.bg"})),
    "BG_PROSECUTOR": ("Bulgarian Prosecutor Office", frozenset({"prb.bg", "www.prb.bg"})),
    "BG_TRANSPORT": ("Bulgarian Ministry of Transport", frozenset({"mtc.government.bg", "www.mtc.government.bg"})),
    "BG_VTMIS": ("Bulgarian Varna Radio VTMIS", frozenset({"vtmis.bg", "www.vtmis.bg"})),
    "MSCIO": ("MSCIO", frozenset({"mscio.eu", "www.mscio.eu"})),
    "UKMTO": ("UKMTO", frozenset({"ukmto.org", "www.ukmto.org"})),
    "NAVAREA_IX": ("Pakistan NAVAREA IX", frozenset({"hydrography.paknavy.gov.pk"})),
}
_KINDS = frozenset({
    "attack", "sinking", "explosion", "collision", "piracy",
    "suspicious_activity", "navigational_hazard", "investigation", "rescue",
    "damage_assessment",
})
_LOCATION_ROLES = frozenset({"unknown", "incident_site", "anchorage", "last_reported_position", "hazard_position"})
_REPORT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 /._-]{0,79}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
SOURCE_RIGHTS = frozenset({"public_with_attribution", "restricted_republication", "unknown"})


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
    # The exact compact DDHHMM UTC MON YY clock printed by Varna Radio.
    original_dtg: str = ""
    # Explicit operator source-check metadata; never implies reuse permission.
    # Optional for backwards-compatible source IDs of older direct callers.
    source_rights: str | None = None
    source_checked_on_utc: date | None = None
    # The source may say "approximately 22:12 UTC": retain the reported
    # clock without treating it as a minute-exact observation.
    event_time_approximate: bool = False
    # Only if the original document specifies a defensible numeric bound.
    reported_time_uncertainty_minutes: float | None = None


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
        raise ValueError("Choose reported event time OR day-only event date")
    if type(bulletin.event_time_approximate) is not bool:
        raise ValueError("Invalid approximate event-time flag")
    if bulletin.event_time_approximate and bulletin.occurred_at is None:
        raise ValueError("Approximate clock requires reported event time")
    bound = bulletin.reported_time_uncertainty_minutes
    if bound is not None and (
        not bulletin.event_time_approximate
        or isinstance(bound, bool) or not isinstance(bound, (int, float))
        or not isfinite(bound) or not 0 < bound <= 1440
    ):
        raise ValueError("Invalid reported time uncertainty")
    if bulletin.published_at is not None and bulletin.publication_date is not None:
        raise ValueError("Choose exact publication time OR day-only publication date")
    if bulletin.event_date is not None and type(bulletin.event_date) is not date:
        raise ValueError("Invalid event date")
    if bulletin.publication_date is not None and type(bulletin.publication_date) is not date:
        raise ValueError("Invalid publication date")
    event_at = _utc(bulletin.occurred_at) if bulletin.occurred_at else None
    if bulletin.issuer == "BG_VTMIS":
        if (not bulletin.original_dtg or bulletin.occurred_at is None
                or parse_navwarn_compact_dtg(bulletin.original_dtg)
                    != bulletin.occurred_at.astimezone(timezone.utc)):
            raise ValueError("VTMIS_NAVWARN_event_clock_mismatch")
    elif bulletin.original_dtg:
        raise ValueError("original_dtg_only_allowed_for_BG_VTMIS")
    published_at = _utc(bulletin.published_at) if bulletin.published_at else None
    # The direct adapter must enforce chronology too: callers can invoke it
    # without passing through the stricter manual staging manifest.
    if event_at is not None and published_at is not None:
        tolerance_seconds = float(bound or 0) * 60
        if (bulletin.occurred_at - bulletin.published_at).total_seconds() > tolerance_seconds:
            raise ValueError("Bulletin publication precedes reported incident")
    # Publisher-local day-only dates can differ from UTC by one calendar
    # day. A publication two or more days before the event is impossible,
    # even with that generous time-zone allowance.
    event_day = (
        bulletin.occurred_at.astimezone(timezone.utc).date()
        if bulletin.occurred_at else bulletin.event_date
    )
    publication_day = (
        bulletin.published_at.astimezone(timezone.utc).date()
        if bulletin.published_at else bulletin.publication_date
    )
    if (event_day is not None and publication_day is not None
            and (event_day - publication_day).days > 1):
        raise ValueError("Bulletin publication day precedes reported incident")
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
    if bulletin.source_rights is not None and (
        not isinstance(bulletin.source_rights, str)
        or bulletin.source_rights not in SOURCE_RIGHTS
    ):
        raise ValueError("Invalid source rights classification")
    checked = bulletin.source_checked_on_utc
    if checked is not None:
        if type(checked) is not date:
            raise ValueError("Invalid source check date")
        for source_day in (
            bulletin.occurred_at.astimezone(timezone.utc).date() if bulletin.occurred_at else bulletin.event_date,
            bulletin.published_at.astimezone(timezone.utc).date() if bulletin.published_at else bulletin.publication_date,
        ):
            if source_day is not None and source_day > checked:
                raise ValueError("Source date after source check date")
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
    # Preserve the exact source date-time group in the immutable canonical
    # payload. The hash of this structured payload is NOT a source PDF hash.
    if bulletin.original_dtg:
        facts["original_dtg"] = bulletin.original_dtg
    # Rights classification can justify a new immutable reviewed revision.
    # The check date is NOT source content: repeating the same check tomorrow
    # must not mint a second observation of the same bulletin.
    if bulletin.source_rights is not None:
        facts["source_rights"] = bulletin.source_rights
    # Do not change immutable source IDs for existing exact/day-only records.
    # Add extra payload keys only for newly represented approximate clocks.
    if bulletin.event_time_approximate:
        facts["event_time_approximate"] = True
        facts["reported_time_uncertainty_minutes"] = bound
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
        "source_policy": "official_metadata_unverified",
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
            "event_time_precision": (
                "approximate" if bulletin.event_time_approximate else
                "exact" if event_at else
                "day" if bulletin.event_date else "unknown"
            ),
            "reported_time_uncertainty_minutes": (
                bound if bulletin.event_time_approximate else None
            ),
            "observed_at_semantics": ("event" if event_at or bulletin.event_date else
                                      "publication" if observed else "unknown"),
            "original_document_sha256": facts["source_document_sha256"],
            **({"original_dtg": bulletin.original_dtg} if bulletin.original_dtg else {}),
            "reuse_rights_verified": False,
            "source_rights": bulletin.source_rights or "unknown",
            "source_checked_on_utc": checked.isoformat() if checked else None,
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
