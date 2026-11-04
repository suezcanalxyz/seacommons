# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure read-only PLAY projection for maritime-attack analyst review.

Callers supply already-authorized SELECT results; this module never connects to
PostgreSQL, writes records, or treats an AIS anomaly as proof of an attack.
"""
from __future__ import annotations

from typing import Any, Mapping

from core.intel.maritime_attack_gate import AttackEvidence
from core.intel.maritime_attack_review import build_attack_review_dossier

SIGNAL_KINDS = frozenset({"ais_gap", "sudden_stop", "ais_anomaly"})


def project_play_attack_review(
    *, case_id: str, source_records: list[Mapping[str, Any]],
    ais_records: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Prepare an immutable review projection from explicitly mapped source rows.

    Source rows must be analyst-vetted, with an explicit attack claim and a
    documented upstream origin; no free-text headline is converted into proof.
    Unmapped/malformed records fail closed rather than silently disappearing.
    """
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case_id_required")
    evidence: list[AttackEvidence] = []
    required = ("source_id", "independent_group", "source_url",
                "event_at", "published_at", "received_at")
    for row in source_records:
        if any(key not in row for key in required):
            raise ValueError("incomplete_source_provenance")
        if row.get("explicit_attack_claim") is not True:
            raise ValueError("source_not_explicitly_vetted")
        if not isinstance(row.get("primary_origin_id"), str) or not row["primary_origin_id"].strip():
            raise ValueError("missing_primary_origin")
        evidence.append(AttackEvidence(
            **{key: row[key] for key in required},
            imo=row.get("imo"), mmsi=row.get("mmsi"),
            position=tuple(row["position"]) if row.get("position") is not None else None,
            uncertainty_km=row.get("uncertainty_km", 0),
            explicit_attack_claim=True, signal_only=False,
            primary_origin_id=row["primary_origin_id"],
        ))
    signals: list[dict[str, Any]] = []
    for row in ais_records or []:
        if row.get("kind") not in SIGNAL_KINDS:
            raise ValueError("unsupported_ais_signal")
        signals.append({key: row.get(key) for key in
                        ("kind", "mmsi", "observed_at", "source", "position")})
    dossier = build_attack_review_dossier(evidence, ais_observations=signals, case_id=case_id)
    dossier["projection_only"] = True
    dossier["source_record_count"] = len(source_records)
    dossier["ais_record_count"] = len(signals)
    return dossier
