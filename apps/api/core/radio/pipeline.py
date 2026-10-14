# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evidence-accurate overview of the first-class maritime radio pipeline."""
from __future__ import annotations

from collections.abc import Mapping


def public_radio_pipeline(*, radio_state: str, structured_state: str,
                          active_receivers: int, decoder: Mapping[str, object],
                          structured: Mapping[str, object],
                          correlations: Mapping[str, int]) -> dict[str, object]:
    """A signal is NOT a distress report until a validated DSC is persisted.

    Counters are since this process started, never fabricated historical
    totals. Each stage is independently identifiable without revealing MMSI,
    receiver lineages, decoded payloads, or private endpoints.
    """
    def count(data: Mapping[str, object], name: str) -> int:
        value = data.get(name)
        return value if type(value) is int and value >= 0 else 0

    frames = count(decoder, "frames")
    verified = count(decoder, "dsc_accepted")
    persisted = count(structured, "dsc_persisted")
    review = count(structured, "projected")
    matches = count(correlations, "ais_strong_matches")
    linked = count(correlations, "episodes_linked")
    return {
        "name": "Maritime radio evidence",
        "count_scope": "since_process_start",
        "stages": [
            {"id": "reception", "label": "Radio reception", "state": radio_state,
             "count": max(0, int(active_receivers))},
            {"id": "demodulation", "label": "DSC signal processing",
             "state": structured_state, "count": frames},
            {"id": "validation", "label": "Verified DSC messages",
             "state": "verified" if verified else "awaiting_message", "count": verified},
            {"id": "evidence", "label": "Persisted DSC evidence",
             "state": "recorded" if persisted else "awaiting_message", "count": persisted},
            {"id": "safety_review", "label": "Distress candidates requiring review",
             "state": "review_required" if review else "none_verified", "count": review},
            {"id": "ais_correlation", "label": "Strong AIS correlations",
             "state": "correlated" if matches else "awaiting_match", "count": matches},
            {"id": "episode", "label": "Linked investigations",
             "state": "linked" if linked else "awaiting_match", "count": linked},
        ],
    }
