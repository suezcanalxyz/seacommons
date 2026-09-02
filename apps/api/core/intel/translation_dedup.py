# SPDX-License-Identifier: AGPL-3.0-or-later
"""Detect a translated / near-duplicate re-post of the same incident.

docs/fixes.md section 2 ("translated/near-duplicate posts") and section 7
(open item: "translated/duplicate posts do not create duplicate incidents").

Alarm Phone routinely publishes the same distress alert twice within a few
minutes -- an English version and a French one (sometimes a same-language
text-only post followed by one carrying the map screenshot). The content
hash is different every time, so both became separate markers on the live
map for a single boat.

This is deterministic, language-invariant matching only (no model): the
reported head-count and the place names, which Alarm Phone keeps close to
their original spelling across languages ("Banjul", "Oran", "Cherchell" /
"Cherchel", "Algeria" / "Algérie"). A 5-character prefix of the
accent-folded token absorbs the small spelling drift.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

# The two posts are minutes apart in practice; keep the window tight so a
# genuine later update with a coincidentally-similar signature is not folded in.
TRANSLATION_WINDOW = timedelta(minutes=45)

_PERSON_COUNT = re.compile(
    r"(?<![\d.])(\d{1,4})\s*"
    r"(?:\+\s*)?"
    r"(?:people|persons?|passengers?|migrants?|survivors?|souls?|ppl|pax"
    r"|personnes?|personas?|persone|menschen|personen"
    r"|rescued|disparu[es]?|vermisst)\b",
    re.I,
)
# "~30", "about 30", "ca. 30" immediately before a person noun is already
# covered above; this catches the bare leading "🆘 ~30 lives at risk".
_APPROX_LEAD = re.compile(r"[~≈]\s*(\d{1,4})\s+(?:lives|people|persons?)\b", re.I)

# Normalised (accent-folded, lower-cased) tokens that name no specific place --
# every incident in this feed mentions the sea, the month, a boat. Matched by
# 5-char prefix, same as the place tokens themselves.
_GENERIC_PREFIXES = frozenset(
    {
        "medit", "centr", "weste", "easte", "aegea", "ocean", "coast", "guard",
        "alarm", "phone", "europ", "fortr", "rescu", "distr", "shipw", "naufr",
        "inter", "pushb", "augus", "septe", "octob", "novem", "decem", "janua",
        "febru", "march", "april", "monda", "tuesd", "wedne", "thurs", "frida",
        "satur", "sunda", "yeste", "today", "tonig", "night", "morni", "eveni",
        "minor", "mineu", "child", "women", "woman", "boats", "batea", "rubbe",
        "group", "autho", "autor", "urgen", "since", "sever", "relat",
        "famil", "peopl", "perso", "surviv", "libya", "libye",
        "salva", "mrcc", "hcoas", "hella", "greec", "grece", "italy", "itali",
        "spain", "espag", "malta",
        # common non-place words that survive the token filter
        "close", "near", "aroun", "about", "leave", "left", "quitt", "parti",
        "board", "aboar", "drift", "water", "engin", "broke", "sinki", "waves",
        "weath", "conta", "alert", "days", "hours", "today", "still", "fear",
        "help", "many", "their", "them", "with", "that", "this", "have", "were",
        "been", "from", "urgent", "immed", "witho", "food", "medic", "assis",
    }
)

_TOKEN = re.compile(r"[#@]?([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’\-]{3,})")


def _fold(word: str) -> str:
    stripped = unicodedata.normalize("NFKD", word)
    ascii_only = stripped.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", ascii_only.lower())


def _person_count(text: str) -> int | None:
    counts = [int(m.group(1)) for m in _PERSON_COUNT.finditer(text or "")]
    counts += [int(m.group(1)) for m in _APPROX_LEAD.finditer(text or "")]
    # The first count in an Alarm Phone alert is the headline group size
    # ("~30 people in distress ... among them 4 children"); later numbers are
    # sub-counts. Two posts about one incident lead with the same number.
    return counts[0] if counts else None


def _place_prefixes(text: str) -> set[str]:
    out: set[str] = set()
    for match in _TOKEN.finditer(text or ""):
        folded = _fold(match.group(1))
        if len(folded) < 5:
            continue
        prefix = folded[:5]
        if prefix in _GENERIC_PREFIXES:
            continue
        out.add(prefix)
    return out


@dataclass(frozen=True)
class IncidentSignature:
    person_count: int | None
    place_prefixes: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_usable(self) -> bool:
        # A head-count plus at least one place name is the minimum to claim a
        # duplicate. A count alone ("30 people") or a place alone is too weak.
        return self.person_count is not None and len(self.place_prefixes) >= 1


def incident_signature(text: str) -> IncidentSignature:
    return IncidentSignature(
        person_count=_person_count(text),
        place_prefixes=frozenset(_place_prefixes(text)),
    )


def signatures_match(a: IncidentSignature, b: IncidentSignature) -> bool:
    """Whether two posts describe the same incident (conservative).

    Same reported head-count from the same account minutes apart, plus at
    least one shared place name. A differing count means different incidents.
    """
    if not (a.is_usable and b.is_usable):
        return False
    if a.person_count != b.person_count:
        return False
    return len(a.place_prefixes & b.place_prefixes) >= 1


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def find_translation_twin(
    text: str,
    *,
    handle: str,
    distress: bool,
    now: datetime,
    candidates: Iterable[Any],
) -> Any | None:
    """The already-stored incident this post is a translated re-issue of.

    ``candidates`` are recent events from the same tracked account. Returns
    the earliest matching one (the canonical incident) or None.
    """
    signature = incident_signature(text)
    if not signature.is_usable:
        return None
    window_start = now - TRANSLATION_WINDOW
    matches: list[tuple[datetime, Any]] = []
    for event in candidates:
        meta = getattr(event, "metadata", {}) or {}
        if str(meta.get("tracked_account") or "").lower() != handle.lower():
            continue
        if bool(meta.get("is_distress")) != distress:
            continue
        observed = _parse_ts(getattr(event, "timestamp_utc", None))
        if observed is None or observed < window_start or observed > now:
            continue
        other = incident_signature(f"{getattr(event, 'title', '')} {getattr(event, 'text', '')}")
        if signatures_match(signature, other):
            matches.append((observed, event))
    if not matches:
        return None
    matches.sort(key=lambda pair: pair[0])
    return matches[0][1]
