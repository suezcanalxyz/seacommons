# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one canonical Live-mode eligibility policy (docs/prompt.md PHASE 5).

Which Live *mode* an event belongs to -- and whether it is humanitarian
*primary* content or *safety context* -- was decided in three places by hand:
`public_policy.compartment_for_domain`, `feed.py`'s bucket logic, and
`live_edge_publisher._edge_humanitarian_eligible`. F-06 unified the
privacy-absolute checks; this unifies the compartment + safety-context
decision so the VM feed and the Cloudflare edge can never disagree on what
"Humanitarian Live" means.

Humanitarian mode = humanitarian primary signals + relevant maritime safety
context (a vessel's own AIS self-report: not under command, aground, distress
beacon). It never includes sanctions / grey-zone / IUU / smuggling / piracy
by default -- those are the security compartment.
"""
from __future__ import annotations

from typing import Any

from core.domain.live_contracts import MaritimeDomain
from core.intel.public_policy import compartment_for_domain

# A vessel self-reporting a manoeuvring limitation over AIS. Context in the
# humanitarian feed, never a security signal and never a pulsing distress
# marker on its own (docs/prompt.md PHASE 4, audit NUC-1..NUC-3).
SAFETY_CONTEXT_DOMAINS = frozenset({MaritimeDomain.SAFETY.value})

_MODES = ("humanitarian", "security")


def _domain(event: Any) -> str:
    getter = getattr(event, "maritime_domain", None)
    value = getter() if callable(getter) else getter
    return str(value or "").strip().lower()


def is_safety_context(event: Any) -> bool:
    """True for a maritime-safety self-report that rides in the humanitarian
    feed as non-distress context."""
    return _domain(event) in SAFETY_CONTEXT_DOMAINS


def mode_for_event(event: Any) -> str | None:
    """The Live mode this event may appear in: 'humanitarian', 'security', or
    None (no public mode). Positive decision only -- never humanitarian by
    complement (F-07)."""
    compartment = compartment_for_domain(_domain(event))
    if compartment in _MODES:
        return compartment
    if is_safety_context(event):
        return "humanitarian"
    return None


def eligible_for_mode(event: Any, mode: str) -> bool:
    """Whether `event` is eligible for Live `mode`. The single check the VM
    feed and the edge publisher both call."""
    return mode_for_event(event) == (mode or "humanitarian").strip().lower()
