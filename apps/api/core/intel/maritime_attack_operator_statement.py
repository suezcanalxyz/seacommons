# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging-only metadata for an operator's reported witness account.

A manager relaying the Master's statement is NOT the Master's original
attestation. No network, database writes, scheduler, or publication.
The operator statement may identify a vessel and report an incident, but
cannot establish an independent witness lineage without source-level review.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from json import dumps
from urllib.parse import urlsplit
import re

from core.intel.maritime_attack_correlation import _valid_imo, _valid_mmsi


_REPORT_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{1,127}$")
_OPERATOR_HOSTS = frozenset({"contships-management.com", "www.contships-management.com"})


@dataclass(frozen=True)
class OperatorIncidentStatement:
    report_id: str
    source_url: str
    vessel_name: str
    event_date: date
    publication_date: date
    imo: str = ""
    mmsi: str = ""
    reported_witness_role: str = "master"
    received_at: datetime | None = None


def prepare_operator_statement(statement: OperatorIncidentStatement) -> dict:
    """Build a source-faithful, non-promotable observation envelope.

    Date-only fields remain dates. In particular the publisher's dateline
    cannot be converted into a fabricated exact event or publication clock.
    The manager's relay is not proof that the Master's original account has
    been obtained or that it is independent of the military report.
    """
    if not _REPORT_ID.fullmatch(statement.report_id):
        raise ValueError("Invalid operator report identifier")
    try:
        url = urlsplit(statement.source_url)
        if (url.scheme != "https" or url.hostname not in _OPERATOR_HOSTS
                or url.username is not None or url.password is not None
                or url.port not in (None, 443) or not url.path.startswith("/2026/")):
            raise ValueError("Unapproved operator document origin")
    except (ValueError, AttributeError) as exc:
        raise ValueError("Unapproved operator document origin") from exc
    if not statement.vessel_name.strip():
        raise ValueError("Missing vessel name")
    if statement.imo and not _valid_imo(statement.imo):
        raise ValueError("Invalid vessel IMO")
    if statement.mmsi and not _valid_mmsi(statement.mmsi):
        raise ValueError("Invalid vessel MMSI")
    if (type(statement.event_date) is not date
            or type(statement.publication_date) is not date
            or statement.event_date > statement.publication_date):
        raise ValueError("Invalid day-only event/publication chronology")
    if statement.reported_witness_role not in {"master", "crew", "operator"}:
        raise ValueError("Unsupported reported witness role")
    received = None
    if statement.received_at is not None:
        received = statement.received_at
        if (not isinstance(received, datetime) or received.tzinfo is None
                or received.utcoffset() is None):
            raise ValueError("Receipt timestamp must be timezone-aware")
        received = received.astimezone(timezone.utc)
        if received.date() < statement.publication_date:
            raise ValueError("Receipt predates publication date")
    report_id = "CONTSHIPS:" + statement.report_id
    facts = {
        "original_report_id": report_id,
        "source_url": statement.source_url,
        "vessel_name": statement.vessel_name.strip(),
        "vessel_imo": statement.imo,
        "vessel_mmsi": statement.mmsi,
        "event_date": statement.event_date.isoformat(),
        "publication_date": statement.publication_date.isoformat(),
        "reported_witness_role": statement.reported_witness_role,
    }
    payload = dumps(facts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    revision = sha256(payload.encode("utf-8")).hexdigest()[:24]
    return {
        "service": "maritime",
        "lane": "safety",
        "observation_type": "operator_incident_statement",
        "source_name": "Contships Management (reported witness relay)",
        "source_policy": "operator_metadata_manual_review",
        "source_id": report_id + ":" + revision,
        "source_url": statement.source_url,
        "observed_at": statement.publication_date.isoformat(),
        "raw_payload": payload,
        "subject_refs": ([f"imo:{statement.imo}"] if statement.imo else []) +
                        ([f"mmsi:{statement.mmsi}"] if statement.mmsi else []),
        "lat": None,
        "lon": None,
        "uncertainty_m": None,
        "provenance": {
            **facts,
            "bulletin_kind": "attack",
            "event_time_precision": "day",
            "occurred_at_utc": None,
            "published_at_utc": None,
            "received_at_utc": received.isoformat() if received else None,
            "observed_at_semantics": "publication",
            "location_role": "unknown",
            "originating_authority_id": "CONTSHIPS",
            "origin_authority_verified": False,
            "original_witness_artifact_verified": False,
            "reported_witness_is_independent": False,
            "attack_corroboration_allowed": False,
            "reuse_rights_verified": False,
            "extraction_review_required": True,
        },
    }
