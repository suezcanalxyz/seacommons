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

import os
from typing import Any, Mapping

from core.domain.live_contracts import (
    BLOCKED_SOURCE_POLICIES,
    DEFAULT_PUBLIC_MARITIME_DOMAINS,
    MaritimeDomain,
    PublicationStatus,
)


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


def public_maritime_domains() -> frozenset[str]:
    """Which maritime compartments the operator has allow-listed for the public
    Live map. ``PUBLIC_MARITIME_DOMAINS`` (comma-separated) overrides the
    default; ``sar`` is implicitly always included.
    """
    raw = os.environ.get("PUBLIC_MARITIME_DOMAINS", "").strip()
    if not raw:
        return DEFAULT_PUBLIC_MARITIME_DOMAINS
    return frozenset(
        {MaritimeDomain.SAR.value}
        | {part.strip().lower() for part in raw.split(",") if part.strip()}
    )


def is_public_domain(domain: str | None) -> bool:
    """True when a maritime compartment may appear on the public Live map without
    a per-event publish decision. Unknown / unset -> treated as ``sar``.
    """
    resolved = (domain or MaritimeDomain.SAR.value).strip().lower()
    return resolved in public_maritime_domains()


# The humanitarian allow-list (public_maritime_domains(), env-configurable)
# deliberately never includes these -- that's what makes them Security
# content instead of default-public. Fixed, not env-configurable: unlike the
# humanitarian allow-list (which an operator may legitimately want to widen,
# e.g. adding "environmental"), Security's scope is a fixed complement so a
# stray env var can't accidentally leak sanctions data into the default feed.
SECURITY_MARITIME_DOMAINS = frozenset(
    {
        MaritimeDomain.SANCTIONS.value,
        MaritimeDomain.GREY_ZONE.value,
        MaritimeDomain.IUU_FISHING.value,
        MaritimeDomain.SMUGGLING.value,
    }
)

# SeaCommons Drift is a humanitarian SAR model only (docs/deep-research-
# report.md #17 hard requirement; docs/deep-research-report (2).md's follow-up
# audit on top of the fix that first narrowed drift eligibility -- "not
# security" is not the same test as "is humanitarian"). public_maritime_
# domains() is env-widenable and includes "piracy" by default, so gating
# drift on domains_for_mode("humanitarian") would still let a piracy-domain
# event carry a drift cone. Deliberately its own fixed, non-env-configurable
# single-value set -- same reasoning as SECURITY_MARITIME_DOMAINS above, just
# a positive allow-list instead of a negative one.
HUMANITARIAN_DRIFT_DOMAINS = frozenset({MaritimeDomain.SAR.value})


def domains_for_mode(mode: str) -> frozenset[str]:
    """Maritime compartments eligible for a Live feed `mode`.

    'humanitarian' (default) is the existing public allow-list, unchanged --
    every caller that doesn't pass a mode keeps today's exact behaviour.
    'security' is content the humanitarian allow-list deliberately excludes.
    'all' is the union, for a caller that wants everything eligible for
    public projection at once (still gated by every other check in
    _public_intel_feature -- this only widens which domain is acceptable).
    """
    mode = (mode or "humanitarian").strip().lower()
    if mode == "security":
        return SECURITY_MARITIME_DOMAINS
    if mode == "all":
        return public_maritime_domains() | SECURITY_MARITIME_DOMAINS
    return public_maritime_domains()
