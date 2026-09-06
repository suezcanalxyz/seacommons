from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.intel.source_identity import SourceIdentityPolicy
from core.intel.store import IntelEvent

METHOD_VERSION = "humanitarian-claim-v1"


@dataclass(frozen=True)
class ExtractedHumanitarianClaim:
    claim_type: str
    value: dict[str, Any]
    extraction_confidence: float
    method_version: str = METHOD_VERSION


_PATTERNS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    ("contradictory_update", re.compile(r"\b(contrary to|correction|we correct|no rescue took place)\b", re.I), 0.95),
    ("rescue_started", re.compile(r"\b(started|began|commenced|starting)\b.{0,30}\brescue\b|\brescue\b.{0,20}\b(started|began|underway)\b", re.I), 0.9),
    ("rescue_completed", re.compile(r"\b(rescued|saved)\b\s+(?:approximately\s+|about\s+)?\d+\s+(?:people|persons|survivors|migrants)|\brescue\b.{0,25}\b(completed|concluded)\b", re.I), 0.95),
    ("disembarkation_reported", re.compile(r"\b(disembarked|disembarkation|disembarking)\b", re.I), 0.95),
    ("fatality_reported", re.compile(r"\b(died|dead|death|deaths|fatalit(?:y|ies))\b", re.I), 0.9),
    ("asset_dispatched", re.compile(r"\b(dispatched|deployed|sent)\b.{0,40}\b(distress|rescue|position|scene)\b", re.I), 0.9),
    ("asset_on_scene", re.compile(r"\b(on scene|on-scene|arrived at (?:the )?(?:scene|distress position))\b", re.I), 0.9),
    ("case_resolved_statement", re.compile(r"\b(case|distress|situation)\b.{0,20}\b(resolved|closed)\b", re.I), 0.95),
)

_RESCUED_COUNT = re.compile(r"\b(?:rescued|saved)\s+(\d{1,4})\s+(?:people|persons|survivors|migrants)\b", re.I)


def _known_asset_name(text: str) -> str | None:
    from core.intel.ngo_registry import NGO_VESSELS

    names = sorted(
        {str(info.get("name") or "").strip() for info in NGO_VESSELS.values() if info.get("name")},
        key=len, reverse=True,
    )
    folded = text.casefold()
    for name in names:
        if name.casefold() in folded:
            return name
    return None


def extract_humanitarian_claims(
    event: IntelEvent,
    source_policy: SourceIdentityPolicy,
) -> tuple[ExtractedHumanitarianClaim, ...]:
    if source_policy.source_role not in {"operational_origin", "verification"}:
        return ()
    if event.type in {"ais_spike", "ais_anomaly", "vessel_status"}:
        return ()

    text = " ".join(part for part in (event.title, event.text) if part).strip()
    if not text:
        return ()

    claims: list[ExtractedHumanitarianClaim] = []
    seen: set[str] = set()
    asset_name = _known_asset_name(text)
    base_value: dict[str, Any] = {"source_identity": source_policy.identity_id}
    if asset_name is not None:
        base_value["asset_name"] = asset_name
    for claim_type, pattern, confidence in _PATTERNS:
        if pattern.search(text) and claim_type not in seen:
            claims.append(ExtractedHumanitarianClaim(
                claim_type=claim_type,
                value=dict(base_value),
                extraction_confidence=confidence,
            ))
            seen.add(claim_type)

    rescued = _RESCUED_COUNT.search(text)
    if rescued:
        claims.append(ExtractedHumanitarianClaim(
            claim_type="people_rescued",
            value={**base_value, "count": int(rescued.group(1))},
            extraction_confidence=0.98,
        ))
    return tuple(claims)


def persist_associated_claims(
    incident_id: str,
    event: IntelEvent,
    claims: tuple[ExtractedHumanitarianClaim, ...] | list[ExtractedHumanitarianClaim],
) -> list[str]:
    from core.db.models import ClaimDB
    from core.db.session import session_scope
    from core.intel.claims import claim_id

    recorded: list[str] = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with session_scope() as db:
        for claim in claims:
            cid = claim_id(incident_id, claim.claim_type, event.id)
            if db.get(ClaimDB, cid) is None:
                db.add(ClaimDB(
                    claim_id=cid, incident_id=incident_id, claim_type=claim.claim_type,
                    value=claim.value, observation_id=event.id, source_id=event.source,
                    claimed_at=event.timestamp_utc, observed_at=event.timestamp_utc,
                    extraction_method=claim.method_version,
                    verification_status="unverified", created_at=now,
                ))
            recorded.append(cid)
    return recorded
