# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured non-coordinate fields from OCR text (docs/prompt.md §9).

A text-card image ("60 personnes, moteur en panne, prennent l'eau") or the
annotations on a map screenshot carry the head count, the vessel condition
and the stated needs. `_easyocr_image` already produced that text; the
pipeline parsed it for a coordinate and threw the rest away (audit EX-1).

This module extracts *candidates* only -- each with the raw OCR span that
produced it -- in English, Italian and French (audit HR-5). The humanitarian
classifier decides what they mean; nothing here is a semantic decision.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_NUM = r"(?P<count>\d{1,4})"
_APPROX = r"(?P<approx>~|≈|about|around|approx(?:imately|\.)?|ca\.?|environ|circa|env\.?|almeno|au moins)"

# kind -> the noun/keyword that identifies it (EN | FR | IT), lower-case.
# A bare count + a generic "people" noun, no role word -- people on a boat in
# a distress report are aboard unless another role says otherwise.
_GENERIC_PEOPLE = (
    r"people|persons|passengers|migrants|souls"
    r"|personnes?|passagers?|personas?"
    r"|persone|passeggeri|menschen|personen"
)

_PEOPLE_KINDS: dict[str, str] = {
    "aboard": r"(?:on ?board|aboard|on the boat|à bord|a bordo|sulla barca)",
    "rescued": r"(?:rescued|survivors?|secouru(?:e?s)?|rescap[ée]e?s?|soccors[ei]|tratt[ei] in salvo|salvat[ei])",
    "missing": r"(?:missing|unaccounted|disparu(?:e?s)?|dispers[ei]|scompars[ei])",
    "dead": r"(?:dead|deceased|bodies|corpses|drowned|mort(?:e?s)?|d[ée]c[ée]d[ée]e?s?|mort[ei]|annegat[ei]|cadaver[ei])",
    "injured": r"(?:injured|wounded|hurt|bless[ée]e?s?|ferit[ei])",
    "children": r"(?:children|kids|minors|enfants?|mineurs?|bambin[ei]|minor[ei]|bimb[ei])",
    "women": r"(?:women|pregnant|femmes?|enceintes?|donne|incinte|gestanti)",
}

_VESSEL_CONDITIONS: dict[str, str] = {
    "engine_failure": (
        r"engine (?:failure|is dead|has stopped|stopped|broke(?:n)?|not working)"
        r"|(?:panne|arr[êe]t) (?:de |du )?moteur|moteur (?:en panne|hs|arr[êe]t[ée])"
        r"|motore (?:in avaria|rotto|fermo|ko)|senza motore|no engine"
    ),
    "taking_water": (
        r"taking (?:on )?water|water (?:is )?coming in|water inside"
        r"|prend(?:re|ent)? l['’ ]?eau|embarque(?:nt)? (?:de )?l['’ ]?eau"
        r"|imbarca(?:no)? acqua|fa acqua|acqua a bordo"
    ),
    "capsized": r"capsized|overturned|chavir[ée]|capovolt[ao]|ribaltat[ao]|si è rovesciat",
    "overcrowded": (
        r"overcrowded|too many people|surcharg[ée]|surpeupl[ée]"
        r"|sovraccaric[ao]|troppe persone|stipat"
    ),
    "adrift": r"adrift|drifting|à la d[ée]rive|alla deriva|senza controllo",
    "deflating": r"deflating|losing air|se d[ée]gonfle|si sgonfia|perde aria",
    "rubber_boat": r"rubber boat|dinghy|inflatable|canot pneumatique|zodiac|gommone|gommato",
}

_NEEDS: dict[str, str] = {
    "rescue": (
        r"need(?:s)? (?:immediate )?rescue|rescue needed|request rescue|require assistance"
        r"|besoin (?:urgent )?de secours|demande(?:nt)? de l['’]aide"
        r"|hanno bisogno di soccorso|chiedono soccorso|serve soccorso"
    ),
    "medical": (
        r"medical (?:help|emergency|assistance)|urgently need a doctor|injured need"
        r"|besoin (?:d['’]un )?m[ée]decin|assistance m[ée]dicale|urgence m[ée]dicale"
        r"|emergenza medica|serve un medico|assistenza medica"
    ),
    "food_water": (
        r"no (?:food|water|drinking water)|without (?:food|water)|out of water"
        r"|sans (?:eau|nourriture|vivres)|plus d['’]eau"
        r"|senza (?:acqua|cibo|viveri)|niente acqua"
    ),
    "fuel": (
        r"no fuel|out of fuel|ran out of fuel|sans carburant|plus d['’]essence|panne s[èe]che"
        r"|senza carburante|senza benzina|finito il carburante"
    ),
    "disembarkation": (
        r"disembark(?:ation)?|place of safety|safe port|port of safety"
        r"|d[ée]barqu(?:ement|er)|lieu s[ûu]r|port s[ûu]r"
        r"|sbarco|porto sicuro|luogo sicuro"
    ),
}


@dataclass(frozen=True)
class PeopleSpan:
    kind: str
    count: int | None
    approx: bool
    raw: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TextField:
    kind: str
    raw: str

    def as_dict(self) -> dict:
        return asdict(self)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()


def extract_people(text: str) -> list[PeopleSpan]:
    """People counts by role. A number next to (either side of) a role noun,
    within a short window, so "45 aboard, 12 rescued, 3 missing" yields three
    distinct spans rather than one `people_reported = 45` (audit HR-1)."""
    flat = _clean(text)
    out: list[PeopleSpan] = []
    seen: set[tuple[str, int | None, str]] = set()
    for kind, noun in _PEOPLE_KINDS.items():
        patterns = (
            rf"(?:{_APPROX}\s*)?{_NUM}\s*(?:\w+\s+){{0,3}}?(?:{noun})",
            rf"(?:{noun})\s*[:\-]?\s*(?:\w+\s+){{0,2}}?(?:{_APPROX}\s*)?{_NUM}",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, flat, re.I):
                count = int(match.group("count")) if match.groupdict().get("count") else None
                raw = _clean(match.group(0))[:120]
                key = (kind, count, raw.lower())
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    PeopleSpan(kind, count, bool(match.groupdict().get("approx")), raw)
                )

    covered = {span.count for span in out if span.count is not None}
    for match in re.finditer(rf"(?:{_APPROX}\s*)?{_NUM}\s*(?:{_GENERIC_PEOPLE})\b", flat, re.I):
        count = int(match.group("count"))
        if count in covered:
            continue
        covered.add(count)
        out.append(
            PeopleSpan("aboard", count, bool(match.groupdict().get("approx")), _clean(match.group(0))[:120])
        )
    return out


def _keyword_fields(text: str, table: dict[str, str]) -> list[TextField]:
    flat = _clean(text)
    out: list[TextField] = []
    seen: set[tuple[str, str]] = set()
    for kind, pattern in table.items():
        for match in re.finditer(pattern, flat, re.I):
            raw = _clean(match.group(0))[:120]
            key = (kind, raw.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(TextField(kind, raw))
    return out


def extract_vessel_conditions(text: str) -> list[TextField]:
    return _keyword_fields(text, _VESSEL_CONDITIONS)


def extract_needs(text: str) -> list[TextField]:
    return _keyword_fields(text, _NEEDS)
