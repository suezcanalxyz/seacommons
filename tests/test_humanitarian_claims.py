from __future__ import annotations

from datetime import datetime, timezone

from core.intel.source_identity import resolve_source_identity
from core.intel.store import IntelEvent


def _event(text: str, *, event_id: str = "ngo-claim-1", source: str = "SOS Méditerranée", event_type: str = "news") -> IntelEvent:
    return IntelEvent(
        id=event_id, type=event_type, severity="high", title=text[:80], text=text,
        source=source, timestamp_utc=datetime.now(timezone.utc).isoformat(),
        metadata={"service": "humanitarian", "lane": "resolution", "transport": "rss"},
    )


def _types(text: str, **kwargs) -> set[str]:
    from core.intel.humanitarian_claims import extract_humanitarian_claims

    event = _event(text, **kwargs)
    policy = resolve_source_identity(event.source, event.metadata)
    return {claim.claim_type for claim in extract_humanitarian_claims(event, policy)}


def test_explicit_rescue_completion_and_people_count_are_structured_claims():
    types = _types("Ocean Viking rescued 42 people from a boat in distress.")
    assert "rescue_completed" in types
    assert "people_rescued" in types


def test_explicit_action_and_outcome_claim_vocabulary():
    cases = {
        "We have started a rescue operation.": "rescue_started",
        "The 42 survivors disembarked safely in Ancona.": "disembarkation_reported",
        "Three people died before rescue arrived.": "fatality_reported",
        "Ocean Viking was dispatched to the distress position.": "asset_dispatched",
        "Ocean Viking is now on scene.": "asset_on_scene",
        "The distress case is resolved.": "case_resolved_statement",
        "Contrary to our earlier report, no rescue took place.": "contradictory_update",
    }
    for text, expected in cases.items():
        assert expected in _types(text), (text, expected)


def test_generic_advocacy_does_not_become_rescue_claim():
    assert _types("Europe must protect lives at sea and defend the right to rescue.") == set()


def test_ais_motion_never_becomes_textual_rescue_claim():
    assert _types(
        "rescue cluster detected near distress position",
        source="AISStream", event_type="ais_spike",
    ) == set()


def test_extraction_confidence_is_not_incident_truth_confidence():
    from core.intel.humanitarian_claims import extract_humanitarian_claims

    event = _event("Ocean Viking rescued 42 people from a boat in distress.")
    claims = extract_humanitarian_claims(event, resolve_source_identity(event.source, event.metadata))
    assert claims
    assert all(claim.extraction_confidence <= 1.0 for claim in claims)
    assert all(claim.method_version.startswith("humanitarian-claim-") for claim in claims)


def test_persist_associated_claims_is_idempotent():
    from core.db.models import ClaimDB
    from core.db.session import session_scope
    from core.intel.humanitarian_claims import extract_humanitarian_claims, persist_associated_claims

    event = _event("Ocean Viking rescued 42 people from a boat in distress.", event_id="ngo-persist-1")
    policy = resolve_source_identity(event.source, event.metadata)
    claims = extract_humanitarian_claims(event, policy)
    first = persist_associated_claims("incident-1", event, claims)
    second = persist_associated_claims("incident-1", event, claims)
    assert first == second
    with session_scope() as db:
        rows = db.query(ClaimDB).filter(ClaimDB.incident_id == "incident-1").all()
        assert len(rows) == len(first)


def test_known_sar_asset_name_is_attached_to_explicit_claims():
    from core.intel.humanitarian_claims import extract_humanitarian_claims

    event = _event("Ocean Viking rescued 42 people from a boat in distress.")
    claims = extract_humanitarian_claims(event, resolve_source_identity(event.source, event.metadata))
    rescue = next(claim for claim in claims if claim.claim_type == "rescue_completed")
    assert rescue.value["asset_name"] == "Ocean Viking"
