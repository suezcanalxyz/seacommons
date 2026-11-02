# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline, opt-in source-checked bulletin batch for attack review in staging.

This is NOT a scraper, poller, scheduler, evidence authenticator or public
incident writer. It validates a small metadata-only manifest and produces
existing canonical OfficialMaritimeBulletin envelopes. A caller may explicitly
pass the returned bulletins to the existing writer in an isolated staging
transaction; this module never opens a DB or commits a row.

A source URL being accessible does not prove an independent witness, an
original ship identifier, reuse rights or a minute-precise incident clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite
from typing import Mapping
from urllib.parse import urlsplit

from core.intel.maritime_attack_correlation import _canonical_source_url
from core.intel.maritime_attack_navwarn_dtg import parse_navwarn_compact_dtg

from core.intel.official_maritime_bulletin import (
    OfficialMaritimeBulletin, prepare_official_bulletin, SOURCE_RIGHTS,
)

_ALLOWED_RIGHTS = SOURCE_RIGHTS
_ALLOWED_FIELDS = frozenset({
    "issuer", "bulletin_id", "source_url", "kind", "vessel_name", "imo",
    "mmsi", "occurred_at_utc", "event_date", "published_at_utc",
    "publication_date", "event_time_approximate",
    "reported_time_uncertainty_minutes", "source_rights",
    "lat", "lon", "location_role", "location_uncertainty_km",
    "source_document_sha256", "source_dtg",
})


@dataclass(frozen=True)
class StagingSourceRecord:
    bulletin: OfficialMaritimeBulletin
    envelope: dict
    source_rights: str
    source_checked_on_utc: date
    # Review is mandatory even if the source page was reachable.
    origin_independence_verified: bool = False
    publication_allowed: bool = False


def _day(value: object, field: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Invalid " + field)
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid " + field) from exc
    if result.isoformat() != value:
        raise ValueError("Invalid " + field)
    return result


def _clock(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or "T" not in value or ":" not in value:
        raise ValueError("Invalid " + field)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid " + field) from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timezone required for " + field)
    return result.astimezone(timezone.utc)


def prepare_staging_bulletin_manifest(manifest: Mapping[str, object]) -> tuple[StagingSourceRecord, ...]:
    """Validate metadata for a bounded, manual, review-only source batch.

    Only exact official source hosts accepted by the existing adapter are
    allowed. An approximate source clock remains approximate in provenance.
    Duplicate bulletin IDs cannot masquerade as independent observations.
    """
    if not isinstance(manifest, Mapping) or set(manifest) != {
        "schema_version", "source_checked_on_utc", "records"
    } or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("Invalid staging manifest schema")
    checked = _day(manifest["source_checked_on_utc"], "source_checked_on_utc")
    if checked is None:
        raise ValueError("Missing source check date")
    records = manifest["records"]
    if not isinstance(records, list) or not 1 <= len(records) <= 32:
        raise ValueError("Invalid staging source batch size")

    prepared: list[StagingSourceRecord] = []
    seen_report_ids: set[str] = set()
    seen_urls: set[str] = set()
    for entry in records:
        if not isinstance(entry, Mapping) or set(entry) - _ALLOWED_FIELDS:
            raise ValueError("Unexpected source manifest field")
        rights = entry.get("source_rights")
        if not isinstance(rights, str) or rights not in _ALLOWED_RIGHTS:
            raise ValueError("Source rights must be explicitly classified")
        for key in ("issuer", "bulletin_id", "source_url", "kind", "vessel_name"):
            if not isinstance(entry.get(key), str):
                raise ValueError("Missing or invalid " + key)
        for optional in ("imo", "mmsi", "source_document_sha256"):
            if optional in entry and not isinstance(entry[optional], str):
                raise ValueError("Invalid " + optional)
        for optional in ("lat", "lon", "location_uncertainty_km"):
            if optional in entry and (
                isinstance(entry[optional], bool)
                or not isinstance(entry[optional], (int, float))
            ):
                raise ValueError("Invalid " + optional)
        event_at = _clock(entry.get("occurred_at_utc"), "occurred_at_utc")
        event_day = _day(entry.get("event_date"), "event_date")
        publication_at = _clock(entry.get("published_at_utc"), "published_at_utc")
        publication_day = _day(entry.get("publication_date"), "publication_date")
        # Both clocks are UTC instants: a published report cannot describe an
        # event that has not yet occurred. Day-only publication metadata is
        # deliberately excluded because publisher-local dates may differ.
        # A documented approximate clock denotes an interval, not an exact
        # point. An unknown bound contributes zero allowance; never infer it.
        bound = entry.get("reported_time_uncertainty_minutes")
        margin = 0.0
        if bound is not None:
            if (entry.get("event_time_approximate") is not True
                    or type(bound) not in (int, float) or not isfinite(bound)
                    or not 0 < bound <= 1440):
                raise ValueError("Invalid reported time uncertainty")
            margin = float(bound)
        if (event_at is not None and publication_at is not None
                and (event_at - publication_at).total_seconds() > margin * 60):
            raise ValueError("Source publication precedes reported incident")
        if (event_at is None and event_day is None
                and publication_at is None and publication_day is None):
            raise ValueError("Missing source event/publication clock")
        # A page checked on a given UTC day cannot already document an event
        # or publication dated later than that day.
        for day in (event_at.date() if event_at else event_day,
                    publication_at.date() if publication_at else publication_day):
            if day is not None and day > checked:
                raise ValueError("Source date after check date")

        issuer = entry["issuer"]
        # Only Bulgarian VTMIS NAVWARN records may carry this compact
        # DDHHMM UTC MON YY clock. The final two digits are the YEAR,
        # not the day: 282030 UTC OCT 26 = 28 Oct 2026 20:30 UTC.
        if issuer == "BG_VTMIS":
            dtg = entry.get("source_dtg")
            if not isinstance(dtg, str) or event_at != parse_navwarn_compact_dtg(dtg):
                raise ValueError("VTMIS_NAVWARN_event_clock_mismatch")
        elif "source_dtg" in entry:
            raise ValueError("source_dtg_only_allowed_for_BG_VTMIS")
        report_id = entry["bulletin_id"]
        # The actual 28 Oct Bulgarian Ministry report names CONTSHIP JET but
        # does not print either identifier. This known regression must never
        # silently borrow IMO/MMSI from a separate registry.
        if issuer == "BG_MOD" and (
            report_id.strip().casefold() == "news9664"
            or urlsplit(entry["source_url"]).path.rstrip("/").casefold() == "/news9664"
        ) and (entry.get("imo") or entry.get("mmsi")):
            raise ValueError("CONTSHIP JET identifiers absent from primary source")
        bulletin = OfficialMaritimeBulletin(
            issuer=issuer, bulletin_id=report_id,
            source_url=entry["source_url"], kind=entry["kind"],
            vessel_name=entry["vessel_name"],
            imo=entry.get("imo", ""), mmsi=entry.get("mmsi", ""),
            occurred_at=event_at, event_date=event_day,
            published_at=publication_at, publication_date=publication_day,
            event_time_approximate=entry.get("event_time_approximate", False),
            reported_time_uncertainty_minutes=entry.get("reported_time_uncertainty_minutes"),
            lat=entry.get("lat"), lon=entry.get("lon"),
            location_role=entry.get("location_role", "unknown"),
            location_uncertainty_km=entry.get("location_uncertainty_km"),
            source_document_sha256=entry.get("source_document_sha256", ""),
            original_dtg=entry.get("source_dtg", ""),
            source_rights=rights,
            source_checked_on_utc=checked,
        )
        envelope = prepare_official_bulletin(bulletin)
        report_key = envelope["provenance"]["original_report_id"].casefold()
        url_key = _canonical_source_url(envelope["source_url"])
        if not url_key:
            raise ValueError("Invalid canonical source URL")
        if report_key in seen_report_ids or url_key in seen_urls:
            raise ValueError("Duplicate original bulletin or source URL")
        seen_report_ids.add(report_key)
        seen_urls.add(url_key)
        if envelope["provenance"]["origin_authority_verified"] is not False:
            raise ValueError("Unexpected verified origin")
        if envelope["provenance"]["attack_corroboration_allowed"] is not False:
            raise ValueError("Unexpected attack corroboration permission")
        prepared.append(StagingSourceRecord(
            bulletin=bulletin, envelope=envelope,
            source_rights=rights, source_checked_on_utc=checked,
        ))
    return tuple(prepared)
