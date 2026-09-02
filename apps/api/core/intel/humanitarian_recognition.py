# SPDX-License-Identifier: AGPL-3.0-or-later
"""Humanitarian Recognition V2 -- deterministic EN/IT/FR extraction (docs/prompt.md PHASE 2).

`humanitarian.humanitarian_case_metadata` is one `_PEOPLE` regex plus a chain
of `re.search` over the caption. It keeps a single head count, has an
order-fragile `_case_type`, and does not distinguish shipwreck, medical
emergency, disembarkation, arrival, death report or a retrospective/memorial
post (audit HR-1..HR-7).

This module produces a `HumanitarianAssessment`: a finite incident type, a
lifecycle that does NOT collapse "rescued" into "resolved" when the same text
says people are still missing or were denied disembarkation, per-role people
counts (each with its raw span, reusing `image_text_fields`), vessel
condition, stated needs, actors, and a traceable confidence.

Pure and deterministic. `humanitarian.py` delegates to it only when
`config.ALERT_RECOGNITION_V2` is set; otherwise nothing here runs on the live
path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from core.intel.image_text_fields import extract_needs, extract_people, extract_vessel_conditions

CLASSIFICATION_VERSION = "humanitarian_recognition/v2"

INCIDENT_TYPES = (
    "distress", "shipwreck", "missing_persons", "interception", "pushback",
    "medical_emergency", "rescue", "disembarkation", "arrival", "death_report",
    "retrospective_incident", "humanitarian_update", "advocacy",
)
LIFECYCLES = ("active", "ongoing", "needs_review", "resolved", "concluded")


def _n(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


# ── incident type keyword tables (EN | FR | IT) ─────────────────────────────
_RETROSPECTIVE = re.compile(
    r"\b(one year (?:ago|on)|years? ago|on this day|anniversary|in memor(?:y|iam)|we remember|"
    r"remembering|il y a (?:un|deux|trois) an|un an(?:née)? (?:jour pour jour)?|"
    r"un anno fa|due anni fa|ricordiamo|in memoria|anniversario)\b",
    re.I,
)
_DEATH = re.compile(
    r"\b(did not survive|didn'?t survive|drowned|bodies (?:were )?recovered|found dead|"
    r"confirmed dead|lost their lives|perished|n'?ont pas survécu|noy[ée]s?|corps (?:ont été )?"
    r"retrouvés|morts confirmés|non (?:sono|è) sopravvissut|anneg[ao]t[ei]|corpi recuperati|"
    r"morti accertat[ei]|hanno perso la vita)\b",
    re.I,
)
_SHIPWRECK = re.compile(
    r"\b(shipwreck|boat (?:sank|capsized|overturned)|capsiz(?:ed|ing)|vessel sank|"
    r"naufrage|chavir[ée]|naufragio|si (?:è|e) (?:ribaltat|rovesciat|capovolt)|imbarcazione (?:affondat|capovolt))\b",
    re.I,
)
_PUSHBACK = re.compile(
    r"\b(pushback|pushed back|forced back|forced return|forced across|refoulement|refoul[ée]s?|"
    r"respingiment|respint[ei]|riportati indietro con la forza)\b",
    re.I,
)
_INTERCEPTION = re.compile(
    r"\b(intercept(?:ed|ion)|pulled back|returned to (?:tripoli|libya|zawiya|zuwara)|"
    r"libyan coast ?guard|so-called coast ?guard|intercept[ée]s?|ramen[ée]s? (?:à|en) libye|"
    r"intercettat[ei]|riportati (?:a|in) (?:tripoli|libia))\b",
    re.I,
)
_MEDICAL = re.compile(
    r"\b(medical (?:emergency|evacuation)|medevac|urgent(?:ly)? (?:need )?(?:a )?(?:doctor|medic)|"
    r"needs? (?:urgent )?medical|pregnant woman|urgence m[ée]dicale|[ée]vacuation m[ée]dicale|"
    r"besoin (?:urgent )?d'?un m[ée]decin|femme enceinte|emergenza medica|evacuazione medica|"
    r"serve un medico|donna incinta)\b",
    re.I,
)
_MISSING = re.compile(
    r"\b(lost contact|loss of contact|no contact|overdue|unaccounted for|missing (?:boat|people|persons)|"
    r"we lost (?:contact|track)|perdu (?:le )?contact|sans nouvelles|port[ée]s? disparus?|"
    r"perso (?:il )?contatto|senza (?:più )?contatto|dispers[ei]|non risponde più)\b",
    re.I,
)
_RESCUE = re.compile(
    r"\b(rescue (?:under ?way|operation|in progress|has begun)|launching (?:its )?rhibs?|"
    r"on scene|proceeding (?:to|toward)|has reached the (?:position|boat)|beginning the rescue|"
    r"sauvetage en cours|op[ée]ration de sauvetage|a atteint la position|"
    r"soccorso in corso|operazione di soccorso|ha raggiunto (?:la posizione|la barca))\b",
    re.I,
)
_DISEMBARK = re.compile(
    r"\b(place of safety|safe port|port of safety|assigned .{0,20}as a place of safety|"
    r"disembark(?:ation)?|lieu s[ûu]r|port s[ûu]r assign|d[ée]barqu(?:ement|er)|"
    r"porto sicuro|luogo sicuro (?:assegnat)?|sbarco autorizzat)\b",
    re.I,
)
_ARRIVAL = re.compile(
    r"\b(have arrived (?:on|in|at)|arrived (?:safely )?(?:on|in|at)|reached (?:land|shore|lampedusa|crotone)|"
    r"safe in the (?:hotspot|reception)|sont arriv[ée]s? (?:à|sur)|ont d[ée]barqu[ée]|"
    r"sono arrivat[ei] (?:a|sull)|approdat[ei] a)\b",
    re.I,
)
_LAND = re.compile(
    r"\b(evros|land border|reception cent(?:re|er)|reception camp|border forest|"
    r"fronti[èe]re terrestre|centre de r[ée]ception|confine terrestre|centro di accoglienza)\b",
    re.I,
)
_ADVOCACY = re.compile(
    r"\b(annual report|press release|we demand|call on (?:the )?e[Uu]|shame on|outrageous|"
    r"donate|fund(?:ing|raiser)|support our (?:ship|mission)|read (?:it|more) on our website|"
    r"rapport annuel|communiqu[ée] de presse|faites un don|soutenez|"
    r"rapporto annuale|comunicato stampa|dona ora|sostieni)\b",
    re.I,
)
_DISTRESS_KW = re.compile(
    r"\b(in distress|urgent|sos|s\.o\.s|mayday|taking (?:on )?water|deflating|adrift|"
    r"people (?:on board|aboard) (?:in )?danger|en d[ée]tresse|prend l'?eau|à la d[ée]rive|"
    r"in pericolo|imbarca acqua|alla deriva|richiesta di aiuto)\b",
    re.I,
)

# lifecycle contradictions: text that means "rescued != resolved"
_STILL_UNRESOLVED = re.compile(
    r"\b(still missing|people still missing|denied disembarkation|no place of safety|"
    r"pushback risk|risk of pushback|still adrift|still drifting|not yet safe|"
    r"toujours port[ée]s? disparus?|d[ée]barquement refus[ée]|"
    r"ancora dispers[ei]|sbarco negato|ancora alla deriva)\b",
    re.I,
)
_ONGOING = re.compile(
    r"\b(still in contact|we are in contact|situation (?:is )?ongoing|we keep (?:pushing|monitoring)|"
    r"toujours en contact|situation en cours|"
    r"ancora in contatto|situazione in corso|continuiamo a seguire)\b",
    re.I,
)

_LCG = re.compile(
    r"\b(libyan coast ?guard|so-called (?:libyan )?coast ?guard|"
    r"garde-?c[ôo]tes? libyenne?s?|(?:sedicente )?guardia costiera libica)\b",
    re.I,
)
_HCG = re.compile(
    r"\b(hellenic coast ?guard|greek coast ?guard|frontex|"
    r"garde-?c[ôo]tes? grecque?s?|guardia costiera greca)\b",
    re.I,
)
_AUTHORITIES = re.compile(
    r"\b(alerted|informed|contacted|called) (?:the )?(authorities|coast ?guard|mrcc|"
    r"italian authorities|maltese authorities|greek authorities|rcc)\b",
    re.I,
)
_NGO_ACTORS = (
    "ocean viking", "sea-watch", "sea watch", "geo barents", "humanity 1", "aita mari",
    "open arms", "mare jonio", "louise michel", "nadir", "trotamar", "resqship",
)

_RETROSPECTIVE_PUBLICATION = {"retrospective_incident", "advocacy", "humanitarian_update"}


@dataclass(frozen=True)
class HumanitarianAssessment:
    incident_type: str
    lifecycle: str
    people: dict[str, Any] = field(default_factory=dict)
    vessel: dict[str, Any] = field(default_factory=dict)
    needs: list[str] = field(default_factory=list)
    actors: dict[str, Any] = field(default_factory=dict)
    temporal: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    publication: str = "published"
    confidence: float = 0.0
    classification_version: str = CLASSIFICATION_VERSION

    def as_metadata(self) -> dict[str, Any]:
        return {
            "humanitarian_assessment": {
                "incident_type": self.incident_type,
                "lifecycle": self.lifecycle,
                "people": self.people,
                "vessel": self.vessel,
                "needs": self.needs,
                "actors": self.actors,
                "temporal": self.temporal,
                "evidence": self.evidence,
                "publication": self.publication,
                "confidence": round(self.confidence, 3),
                "classification_version": self.classification_version,
            }
        }


def _incident_type(text: str, *, direct_distress: bool) -> str:
    t = _n(text)
    if _RETROSPECTIVE.search(t) and (_DEATH.search(t) or "drowned" in t or "victims" in t):
        return "retrospective_incident"
    if _DEATH.search(t) and not _RESCUE.search(t):
        return "death_report"
    if _SHIPWRECK.search(t):
        return "shipwreck"
    if _PUSHBACK.search(t):
        return "pushback"
    if _INTERCEPTION.search(t):
        return "interception"
    if _MEDICAL.search(t):
        return "medical_emergency"
    if _MISSING.search(t):
        return "missing_persons"
    if _DISEMBARK.search(t):
        return "disembarkation"
    if _ARRIVAL.search(t):
        return "arrival"
    if _RESCUE.search(t):
        return "rescue"
    if _LAND.search(t):
        return "land_humanitarian"
    # Advocacy before the distress fallback: an org publication ("annual
    # report", "read it on our website") can contain "SOS" in its own name or
    # quote a rescue total without being an active incident (audit HR-2).
    if _ADVOCACY.search(t) and not direct_distress:
        return "advocacy"
    if direct_distress or _DISTRESS_KW.search(t):
        return "distress"
    return "humanitarian_update"


def _lifecycle(text: str, incident_type: str) -> str:
    t = _n(text)
    if _STILL_UNRESOLVED.search(t):
        # a "rescued" / "safe" claim contradicted in the same text
        return "needs_review"
    if incident_type in {"death_report", "retrospective_incident", "pushback", "interception"}:
        return "concluded"
    if incident_type in {"arrival", "disembarkation"}:
        return "resolved"
    if incident_type in {"rescue", "humanitarian_update"}:
        return "ongoing"
    if incident_type == "advocacy":
        return "concluded"
    if _ONGOING.search(t):
        return "ongoing"
    return "active"


def _people(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {"_spans": []}
    for span in extract_people(text):
        out["_spans"].append(span.as_dict())
        if span.count is not None and span.kind not in out:
            out[span.kind] = span.count
        if span.approx:
            out["approximate"] = True
    return out


def _vessel(text: str) -> dict[str, Any]:
    conditions = [f.as_dict() for f in extract_vessel_conditions(text)]
    vessel: dict[str, Any] = {}
    for field_ in conditions:
        vessel[field_["kind"]] = True
    if conditions:
        vessel["_spans"] = conditions
    return vessel


def _actors(text: str) -> dict[str, Any]:
    t = _n(text)
    actors: dict[str, Any] = {}
    if _AUTHORITIES.search(t):
        actors["authorities_contacted"] = True
    if _LCG.search(t):
        actors["interception_actor"] = "libyan_coast_guard"
    elif _HCG.search(t):
        actors["interception_actor"] = "hellenic_coast_guard"
    for name in _NGO_ACTORS:
        if name in t:
            actors["rescue_actor"] = name.replace(" ", "_").replace("-", "_")
            break
    return actors


def _temporal(text: str, incident_type: str) -> dict[str, Any]:
    t = _n(text)
    temporal: dict[str, Any] = {"retrospective": incident_type == "retrospective_incident"}
    m = re.search(r"\b(\d+)\s*(day|days|jours?|giorni?)\s*ago\b", t) or re.search(
        r"\bil y a\s*(\d+)\s*(jours?)\b", t
    )
    if m:
        temporal["last_contact_time"] = f"relative:-{m.group(1)}d"
    return temporal


def _confidence(text: str, incident_type: str, people: dict[str, Any], source: str) -> float:
    score = 0.3
    if str(source).lower().lstrip("@") in {"alarm_phone", "sos_mediterranee", "msf_sea"}:
        score += 0.25
    if incident_type not in {"humanitarian_update", "advocacy"}:
        score += 0.15
    if any(k for k in people if k not in {"_spans", "approximate"}):
        score += 0.1
    if re.search(r"\d{1,2}[°º]\s?\d", text or ""):
        score += 0.1
    if incident_type in {"advocacy", "retrospective_incident"}:
        score = min(score, 0.25)
    return max(0.0, min(1.0, score))


def recognize(
    text: str,
    *,
    source: str = "",
    direct_distress: bool = False,
    corroborating_sources: int = 0,
) -> HumanitarianAssessment:
    incident_type = _incident_type(text, direct_distress=direct_distress)
    lifecycle = _lifecycle(text, incident_type)
    people = _people(text)
    vessel = _vessel(text)
    needs = sorted({f.kind for f in extract_needs(text)})
    actors = _actors(text)
    actors["reporting_source"] = str(source or "").lower().lstrip("@") or "unknown"
    temporal = _temporal(text, incident_type)
    publication = "internal" if incident_type in _RETROSPECTIVE_PUBLICATION else "published"
    confidence = _confidence(text, incident_type, people, source)
    evidence = {
        "source_type": "humanitarian_public_source",
        "direct_report": bool(direct_distress),
        "corroborating_sources": int(corroborating_sources),
        "confidence": round(confidence, 3),
        "uncertainty_reasons": (
            ["single public source"] if corroborating_sources == 0 else []
        ),
    }
    return HumanitarianAssessment(
        incident_type=incident_type,
        lifecycle=lifecycle,
        people=people,
        vessel=vessel,
        needs=needs,
        actors=actors,
        temporal=temporal,
        evidence=evidence,
        publication=publication,
        confidence=confidence,
    )
