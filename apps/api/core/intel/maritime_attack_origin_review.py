# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed, offline review of source-origin independence for maritime incidents.

This module neither ingests sources nor writes to production. A report is not
an independent corroboration merely because a second publisher repeats it.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from hashlib import sha256
import json
from urllib.parse import urlsplit


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("invalid_utc_timestamp")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid_utc_timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone_required")
    return dt.astimezone(timezone.utc)


def prepare_origin_review(
    reports: Sequence[Mapping[str, object]],
    *,
    reviewed_at_utc: str,
) -> dict[str, object]:
    """Return immutable-style staging metadata, never a publication decision.

    origin_key identifies the actual original observer/authority, NOT publisher.
    When the reporting chain is unknown, origin_key MUST be null. Multiple
    reports of the same underlying relay must share a key if established.
    """
    checked = _utc(reviewed_at_utc)
    if not isinstance(reports, (tuple, list)) or not 1 <= len(reports) <= 64:
        raise ValueError("invalid_review_batch")
    seen: set[tuple[str, str]] = set()
    seen_urls: set[tuple[str, str]] = set()
    groups: dict[str, list[str]] = {}
    unresolved: list[str] = []
    normalized: list[dict[str, object]] = []
    for item in reports:
        if not isinstance(item, Mapping) or set(item) != {
            "publisher", "publisher_item_id", "source_url", "origin_key",
            "origin_verified", "retrieved_at_utc", "evidence_kind",
        }:
            raise ValueError("invalid_report_schema")
        publisher, identifier = item["publisher"], item["publisher_item_id"]
        if not isinstance(publisher, str) or not publisher.strip() or not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("invalid_report_identity")
        identity = (publisher.casefold().strip(), identifier.casefold().strip())
        if identity in seen:
            raise ValueError("duplicate_publisher_report")
        seen.add(identity)
        url = item["source_url"]
        if not isinstance(url, str) or any(c.isspace() for c in url):
            raise ValueError("invalid_source_url")
        try:
            parsed = urlsplit(url)
            if (parsed.scheme != "https" or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.port not in (None, 443) or parsed.fragment):
                raise ValueError("invalid_source_url")
        except ValueError as exc:
            raise ValueError("invalid_source_url") from exc
        url_identity = (publisher.casefold().strip(), url.rstrip("/").casefold())
        if url_identity in seen_urls:
            raise ValueError("duplicate_publisher_source_url")
        seen_urls.add(url_identity)
        retrieved = _utc(item["retrieved_at_utc"])
        if retrieved > checked:
            raise ValueError("future_retrieval")
        origin = item["origin_key"]
        verified = item["origin_verified"]
        if type(verified) is not bool or (origin is not None and (not isinstance(origin, str) or not origin.strip())):
            raise ValueError("invalid_origin_claim")
        if verified and origin is None:
            raise ValueError("verified_origin_missing")
        kind = item["evidence_kind"]
        if kind not in {"first_hand", "authority", "relay", "press", "ais_signal", "imagery"}:
            raise ValueError("invalid_evidence_kind")
        if verified and kind == "ais_signal":
            raise ValueError("ais_is_not_witness")
        label = publisher.strip() + ":" + identifier.strip()
        if verified:
            groups.setdefault(origin.strip(), []).append(label)
        else:
            unresolved.append(label)
        normalized.append({
            "publisher": publisher.strip(), "publisher_item_id": identifier.strip(),
            "source_url": url, "origin_key": origin.strip() if origin is not None else None,
            "origin_verified": verified, "retrieved_at_utc": retrieved.isoformat(),
            "evidence_kind": kind,
        })
    # Count independent human/authority origins only. Image and AIS evidence
    # can support a review but cannot impersonate separate testimonies.
    qualifying = set()
    for item in normalized:
        if item["origin_verified"] and item["evidence_kind"] in {"first_hand", "authority"}:
            qualifying.add(item["origin_key"])
    result: dict[str, object] = {
        "staging_only": True,
        "publication_allowed": False,
        "reviewed_at_utc": checked.isoformat(),
        "independent_testimonial_origins": len(qualifying),
        "origin_groups": {key: sorted(value) for key, value in sorted(groups.items())},
        "unresolved_reports": sorted(unresolved),
        "reports": normalized,
        "attacker_attribution": None,
    }
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    result["review_snapshot_sha256"] = sha256(encoded.encode("utf-8")).hexdigest()
    return result
