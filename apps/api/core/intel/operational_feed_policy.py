# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed operational feed policies; historical reports remain in archive."""
from __future__ import annotations
import re
from datetime import datetime, timezone

_RETROSPECTIVE = re.compile(
    r'\b(?:lost (?:contact|track|trace)|traces? (?:were|have been) lost|'
    r'went missing|have been missing|missing since|disappeared on|'
    r'no (?:news|contact) since|(?:there (?:is|are) )?no news from (?:them|the boat|the people)|'
    r'since then.{0,100}no news|whereabouts (?:remain|are) unknown|'
    r'(?:unable|not able|cannot|can[’\x27]t|could not|couldn[’\x27]t) to (?:reach|contact) (?:them|the boat|the group)|'
    r'neither.{0,80}(?:able to|can) (?:reach|contact) (?:them|the boat|the group)|'
    r'last (?:heard from|seen) on)\b', re.I)
_CURRENT_EMERGENCY = re.compile(
    r'\b(?:mayday|currently in distress|urgent rescue (?:needed|required)|'
    r'rescue (?:is )?(?:underway|ongoing)|immediate assistance (?:needed|required))\b',re.I)

def humanitarian_live_eligible(*, text: str, timestamp: str, is_distress: bool,
                              now: datetime | None = None, max_age_hours: int = 24) -> bool:
    if not is_distress:
        return False
    try:
        observed=datetime.fromisoformat(timestamp.replace('Z','+00:00'))
        if observed.tzinfo is None:
            return False
        current=now or datetime.now(timezone.utc)
        age=(current.astimezone(timezone.utc)-observed.astimezone(timezone.utc)).total_seconds()/3600
    except (ValueError, TypeError, AttributeError):
        return False
    if age < -0.25 or age > max_age_hours:
        return False
    if _RETROSPECTIVE.search(text or '') and not _CURRENT_EMERGENCY.search(text or ''):
        return False
    return True


def withhold_humanitarian_live(event, *, now: datetime | None = None) -> bool:
    """One policy for VM Live, edge Live and public drift, not historical archive."""
    domain = str(event.maritime_domain() or '').lower()
    if domain not in {'sar', 'humanitarian'}:
        return False
    if event.type not in {'distress', 'twitter', 'mastodon', 'bluesky', 'news'}:
        return False
    return not humanitarian_live_eligible(
        text=f'{event.title or ""} {event.text or ""}',
        timestamp=event.timestamp_utc,
        is_distress=bool((event.metadata or {}).get('is_distress')),
        now=now,
    )
