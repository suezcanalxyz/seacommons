# SPDX-License-Identifier: AGPL-3.0-or-later
"""Canonical privacy-boundary primitives for SeaCommons' public Live paths.

core/live/projection.py (VM REST/WS feed) and core/live_edge_publisher.py
(Cloudflare edge push) each decide independently whether a stored intel
event is safe to expose on the public Live map. The privacy-absolute rules
below -- an operator's explicit private mark can never be overridden, and
content that reached us over a blocked/unofficial transport can never
surface -- must never diverge between the two paths, so they live here
once instead of as two hand-maintained copies (previously two separate
frozenset literals plus two separate inline checks that had to be kept in
sync by convention).

This module has no dependency on FastAPI, SQLAlchemy, or anything else
core.live_edge_publisher avoids pulling into its low-memory process --
keep it that way.

What is deliberately NOT unified here: which additional event *types* are
eligible for public exposure without an explicit publish decision. The VM
feed and the edge feed intentionally serve different audiences (a broader
"public signals" context feed vs. an operational distress-only Live map)
and may legitimately keep different eligibility rules beyond the two
privacy-absolute checks below -- see each caller's own criterion.
"""

from __future__ import annotations

from typing import Any, Mapping

from core.domain.live_contracts import BLOCKED_SOURCE_POLICIES, PublicationStatus


def is_explicitly_private(metadata: Mapping[str, Any]) -> bool:
    """An operator's explicit private mark is absolute and can never be overridden."""
    return str(metadata.get("publication_status") or "").lower() == PublicationStatus.PRIVATE.value


def is_blocked_source(metadata: Mapping[str, Any]) -> bool:
    """Legacy scraper records / unofficial transport must never reach a public
    feed, even if publication_status or is_distress say otherwise (defense
    in depth against a bad upstream flag).
    """
    source_policy = str(metadata.get("source_policy") or "").lower()
    transport = str(metadata.get("via") or metadata.get("scrape_source") or "").lower()
    return source_policy in BLOCKED_SOURCE_POLICIES or any(
        blocked in transport for blocked in BLOCKED_SOURCE_POLICIES
    )
