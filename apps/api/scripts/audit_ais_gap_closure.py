"""Read-only aggregate audit of AIS gap closure provenance.

Run: PYTHONPATH=apps/api python apps/api/scripts/audit_ais_gap_closure.py
No rows, MMSIs, coordinates or identifying track data are printed.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select

from core.db.models import IntelEventDB
from core.db.session import session_scope


AUDIT_FIELDS = (
    "gap_events", "open", "closed", "missing_attestation",
    "attestation_fields_complete", "attestation_fields_incomplete",
    "closed_without_attestation", "closed_with_incomplete_attestation",
)


def _valid_utc_observation(value: object) -> bool:
    """Require a parseable timezone-aware observation, not just a nonempty field."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def summarize_gap_attestations(events: list[tuple[str, dict]]) -> dict:
    """Aggregate states without exposing vessel identities or positions."""
    counts: Counter[str] = Counter()
    for _, meta in events:
        if meta.get("anomaly_type") not in ("gap", "long_gap"):
            continue
        counts["gap_events"] += 1
        closed = meta.get("resolution_state") == "resolved" or meta.get("incident_lifecycle") == "resolved"
        if closed:
            counts["closed"] += 1
        else:
            counts["open"] += 1
        attestation = meta.get("reappearance_validation")
        if not isinstance(attestation, dict):
            counts["missing_attestation"] += 1
            if closed:
                counts["closed_without_attestation"] += 1
            continue
        bound = all((
            attestation.get("identity_validated") is True,
            attestation.get("source_validated") is True,
            bool(str(attestation.get("track_id") or "")),
            bool(str(attestation.get("mmsi") or "")),
            bool(str(attestation.get("source") or "")),
            _valid_utc_observation(attestation.get("observed_at")),
        ))
        counts["attestation_fields_complete" if bound else "attestation_fields_incomplete"] += 1
        if closed and not bound:
            counts["closed_with_incomplete_attestation"] += 1
    return {key: counts[key] for key in AUDIT_FIELDS}


def main() -> None:
    with session_scope() as db:
        # Bounded streaming, no mutations; metadata remains internal.
        rows = db.execute(
            select(IntelEventDB.id, IntelEventDB.meta)
            .where(IntelEventDB.type == "ais_anomaly")
            .execution_options(yield_per=500)
        )
        counts: Counter[str] = Counter()
        scanned = 0
        for event_id, metadata in rows:
            scanned += 1
            summary = summarize_gap_attestations([(event_id, metadata or {})])
            counts.update(summary)
    print(json.dumps({
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "stored ais_anomaly metadata; field presence only, not independent authentication",
        "scanned_anomaly_events": scanned,
        **{key: counts[key] for key in AUDIT_FIELDS},
    }, sort_keys=True))


if __name__ == "__main__":
    main()
