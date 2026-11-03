# SPDX-License-Identifier: AGPL-3.0-or-later
"""Immutable, staging-only lifecycle evidence for an existing maritime incident.

A closure or liberation notice is a status claim about an existing case,
not a second attack, an independent witness or authorization to publish.
No database, network, scheduler or production side effects.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit


_UPDATE_ID = re.compile(r"UPDATE[0-9]{2}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ISSUER_HOSTS = {
    "MSCIO": frozenset({"mscio.eu", "www.mscio.eu"}),
    "UKMTO": frozenset({"ukmto.org", "www.ukmto.org"}),
}


def _clock(value: object, *, required: bool) -> datetime | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("lifecycle_utc_clock_required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("lifecycle_invalid_clock") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("lifecycle_timezone_required")
    return parsed.astimezone(timezone.utc)


def _source_key(url: object, issuer: str) -> tuple[str, str]:
    if not isinstance(url, str) or any(c.isspace() for c in url):
        raise ValueError("lifecycle_invalid_source_url")
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in _ISSUER_HOSTS[issuer]
            or parsed.port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
        ):
            raise ValueError("lifecycle_invalid_source_url")
    except (ValueError, KeyError) as exc:
        raise ValueError("lifecycle_invalid_source_url") from exc
    host = parsed.hostname[4:] if parsed.hostname.startswith("www.") else parsed.hostname
    return host, parsed.path.rstrip("/")


def prepare_staging_lifecycle_update(
    original: Mapping[str, object],
    update: Mapping[str, object],
) -> dict[str, object]:
    """Produce an append-only review record; never mutate the original event.

    The operator supplies checked source metadata. The source's *current page*
    timestamp is not the time a vessel was freed; an unknown effective clock
    must remain null. A later status is not new attack corroboration.
    """
    if not isinstance(original, Mapping) or not isinstance(update, Mapping):
        raise ValueError("lifecycle_mapping_required")
    if (
        original.get("staging_only") is not True
        or original.get("publication_allowed") is not False
        or original.get("source_kind") not in {"attack", "piracy"}
        or type(original.get("independent_origins_verified")) is not int
        or original["independent_origins_verified"] != 0
    ):
        raise ValueError("lifecycle_untrusted_original")
    issuer = update.get("issuer")
    if issuer not in _ISSUER_HOSTS:
        raise ValueError("lifecycle_unapproved_issuer")
    report_id = original.get("original_report_id")
    observation_id = original.get("canonical_observation_id")
    if (
        not isinstance(report_id, str) or not report_id
        or not isinstance(observation_id, str) or not observation_id
        or not report_id.startswith(issuer + ":")
        or update.get("original_report_id") != report_id
    ):
        raise ValueError("lifecycle_original_identity_conflict")
    if _source_key(original.get("source_url"), issuer) != _source_key(
        update.get("source_url"), issuer
    ):
        raise ValueError("lifecycle_source_document_conflict")
    update_id = update.get("source_update_id")
    if not isinstance(update_id, str) or not _UPDATE_ID.fullmatch(update_id):
        raise ValueError("lifecycle_update_id_required")
    if update.get("status") not in {"closed", "investigating", "ongoing"}:
        raise ValueError("lifecycle_status_not_supported")
    if update.get("source_rights") not in {
        "restricted_republication", "public_with_attribution", "unknown"
    }:
        raise ValueError("lifecycle_source_rights_required")
    if (
        update.get("staging_only") is not True
        or update.get("publication_allowed") is not False
        or update.get("independent_origins_verified") != 0
        or type(update.get("independent_origins_verified")) is not int
    ):
        raise ValueError("lifecycle_publication_boundary")
    if set(update) - {
        "issuer", "original_report_id", "source_update_id", "source_url",
        "source_checked_at_utc", "source_published_at_utc",
        "status_effective_at_utc", "status", "source_rights",
        "source_document_sha256", "staging_only", "publication_allowed",
        "independent_origins_verified",
    }:
        raise ValueError("lifecycle_unreviewed_fields")
    checked = _clock(update.get("source_checked_at_utc"), required=True)
    published = _clock(update.get("source_published_at_utc"), required=False)
    effective = _clock(update.get("status_effective_at_utc"), required=False)
    assert checked is not None
    if (published is not None and published > checked) or (
        effective is not None and effective > checked
    ):
        raise ValueError("lifecycle_future_source_claim")
    event_at = _clock(original.get("occurred_at_utc"), required=False)
    event_day = original.get("event_date")
    if event_at is None:
        if not isinstance(event_day, str):
            raise ValueError("lifecycle_original_event_date_required")
        try:
            event_day_parsed = date.fromisoformat(event_day)
        except ValueError as exc:
            raise ValueError("lifecycle_original_event_date_invalid") from exc
        if event_day_parsed.isoformat() != event_day:
            raise ValueError("lifecycle_original_event_date_invalid")
    else:
        event_day_parsed = event_at.date()
        if event_day is not None:
            if not isinstance(event_day, str) or event_day != event_day_parsed.isoformat():
                raise ValueError("lifecycle_original_event_date_conflict")
    if checked.date() < event_day_parsed or (event_at is not None and checked < event_at):
        raise ValueError("lifecycle_update_before_original")
    if published is not None and (
        published.date() < event_day_parsed
        or (event_at is not None and published < event_at)
    ):
        raise ValueError("lifecycle_publication_before_original")
    if effective is not None and (
        (event_at is not None and effective < event_at)
        or effective.date() < event_day_parsed
    ):
        raise ValueError("lifecycle_effective_before_original")
    if published is not None and effective is not None and published < effective:
        raise ValueError("lifecycle_published_before_effective")
    digest = update.get("source_document_sha256")
    if digest is not None and (
        not isinstance(digest, str) or not _DIGEST.fullmatch(digest)
    ):
        raise ValueError("lifecycle_invalid_source_digest")
    payload: dict[str, object] = {
        "case_observation_id": observation_id,
        "original_report_id": report_id,
        "original_source_kind": original["source_kind"],
        "original_event_date": event_day_parsed.isoformat(),
        "source_update_id": update_id,
        "lifecycle_evidence_id": report_id + ":" + update_id,
        "source_url": update["source_url"],
        "source_checked_at_utc": checked.isoformat(),
        "source_published_at_utc": published.isoformat() if published else None,
        "status_effective_at_utc": effective.isoformat() if effective else None,
        "source_document_sha256": digest,
        "source_rights": update["source_rights"],
        "reported_status": update["status"],
        "status_is_a_source_claim": True,
        "new_incident": False,
        "independent_origins_verified": 0,
        "attack_corroboration_allowed": False,
        "publication_allowed": False,
        "staging_only": True,
        "attacker_attribution": None,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    payload["lifecycle_snapshot_sha256"] = sha256(canonical.encode()).hexdigest()
    return payload
