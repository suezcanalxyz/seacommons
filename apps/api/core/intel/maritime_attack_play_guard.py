# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging-only, conservative verification label for maritime attack episodes.

This is a presentation guard, not an incident promotion or a substitute for
lineage verification. The canonical fusion classifier must establish the
verification status. AIS gaps and counts of URLs are never independent proof.
"""
from __future__ import annotations

import re

_ATTACK_FAMILIES = frozenset({
    "attack_episode", "maritime_attack_episode", "maritime_attack",
})


def _canonical_authority_key(value: str) -> str:
    """Collapse cosmetic separators in source-authority labels, not report IDs.

    Conservative alias merging can withhold corroboration, but cannot create
    additional supposedly independent origins from formatting differences.
    """
    return re.sub(r"[\\s_-]+", " ", value.strip().casefold())


def has_distinct_independence_groups(groups: object) -> bool:
    """At least two nonempty, case-normalized source lineages.

    Distinct labels alone cannot establish real-world independence. That
    determination belongs to the canonical lineage/circularity checks.
    """
    if not isinstance(groups, (list, tuple)) or not groups:
        return False
    if any(not isinstance(group, str) or not group.strip() for group in groups):
        return False
    return len({_canonical_authority_key(group) for group in groups}) >= 2


def episode_corroborated_for_play(episode: object | None, *, independence_verified: bool = False) -> bool:
    """Fail closed for attack episodes; preserve legacy non-attack behavior.

    An attack is never labelled corroborated merely because it has two rows
    or two unverified lineage labels. Explicit verification must come from the
    bounded canonical provenance audit, not caller-supplied source labels.
    A positive label does NOT authorize PLAY -> LIVE promotion or publication.
    """
    if episode is None:
        return False
    status = str(getattr(episode, "verification_status", "") or "")
    groups = getattr(episode, "independence_groups", None)
    family = str(getattr(episode, "episode_family", "") or "")
    if family in _ATTACK_FAMILIES:
        return (
            status == "multi_source_corroborated"
            and has_distinct_independence_groups(groups)
            and independence_verified is True
        )
    # Outside the attack family this staging change must not silently
    # reclassify existing humanitarian or other maritime evidence.
    return status == "multi_source_corroborated" or (
        isinstance(groups, (list, tuple)) and len(groups) >= 2
    )
