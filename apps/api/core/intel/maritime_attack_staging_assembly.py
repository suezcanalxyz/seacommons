# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline staging composition for maritime attack review.

The returned objects are non-public review proposals. This module does not
access the network, query databases or modify LIVE/PLAY endpoints.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from core.intel.maritime_attack_origin_review import prepare_origin_review
from core.intel.maritime_attack_staging_preview import build_staging_attack_previews
from core.intel.maritime_attack_staging_routing import route_staging_incident


def assemble_staging_review(records: Sequence[object],
                            observations: Sequence[object],
                            reports: Mapping[str, Sequence[Mapping[str, object]]],
                            *, now_utc: str) -> tuple[dict[str, object], ...]:
    previews = build_staging_attack_previews(records, observations)
    if not isinstance(reports, Mapping):
        raise ValueError("invalid_reports_mapping")
    identifiers = {item["canonical_observation_id"] for item in previews}
    if set(reports) - identifiers:
        raise ValueError("foreign_review_report")
    result = []
    for item in previews:
        report_set = reports.get(item["canonical_observation_id"])
        review = prepare_origin_review(report_set, reviewed_at_utc=now_utc) if report_set else None
        route = route_staging_incident(item, now_utc=now_utc)
        result.append({"preview": item, "origin_review": review, "routing": route,
                       "staging_only": True, "publication_allowed": False})
    return tuple(result)
