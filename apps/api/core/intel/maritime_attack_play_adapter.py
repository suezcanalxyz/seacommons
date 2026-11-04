# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure read-only PLAY projection for maritime-attack analyst review.

Callers supply already-authorized SELECT results; this module never connects to
PostgreSQL, writes records, or treats an AIS anomaly as proof of an attack.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Mapping

from core.intel.maritime_attack_gate import AttackEvidence
from core.intel.maritime_attack_review import build_attack_review_dossier

SIGNAL_KINDS = frozenset({"ais_gap", "sudden_stop", "ais_anomaly"})


def project_play_attack_review(
    *, case_id: str, source_records: list[Mapping[str, Any]],
    ais_records: list[Mapping[str, Any]] | None = None,
    target_mmsi: str | None = None, event_at: str | None = None,
    max_ais_offset_hours: float = 24.0,
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
    if ais_records:
        if target_mmsi is None or event_at is None:
            raise ValueError("ais_context_requires_target_identity_and_event_time")
        if not isinstance(target_mmsi, str) or len(target_mmsi) != 9 or not target_mmsi.isascii() or not target_mmsi.isdigit():
            raise ValueError("invalid_target_mmsi")
        if isinstance(max_ais_offset_hours, bool) or not isinstance(max_ais_offset_hours, (int, float)) or not isfinite(max_ais_offset_hours) or max_ais_offset_hours < 0:
            raise ValueError("invalid_ais_time_window")
    signals: list[dict[str, Any]] = []
    # Fail closed on malformed AIS context; these are never attack proofs.
    def _utc_timestamp(value: Any) -> datetime:
        if not isinstance(value, str):
            raise ValueError("invalid_ais_timestamp")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid_ais_timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("invalid_ais_timestamp")
        return parsed.astimezone(timezone.utc)

    def _position(value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise ValueError("invalid_ais_position")
        lat, lon = value
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x) for x in (lat, lon)):
            raise ValueError("invalid_ais_position")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("invalid_ais_position")

    anchor = _utc_timestamp(event_at) if ais_records else None
    for row in ais_records or []:
        if row.get("kind") not in SIGNAL_KINDS:
            raise ValueError("unsupported_ais_signal")
        observed = _utc_timestamp(row.get("observed_at"))
        if abs((observed - anchor).total_seconds()) > max_ais_offset_hours * 3600:
            raise ValueError("ais_outside_event_window")
        _position(row.get("position"))
        mmsi = row.get("mmsi")
        if mmsi is not None and (not isinstance(mmsi, str) or len(mmsi) != 9 or not mmsi.isascii() or not mmsi.isdigit()):
            raise ValueError("invalid_ais_mmsi")
        if mmsi != target_mmsi:
            raise ValueError("ais_vessel_identity_mismatch")
        signals.append({key: row.get(key) for key in
                        ("kind", "mmsi", "observed_at", "source", "position")})
    dossier = build_attack_review_dossier(evidence, ais_observations=signals, case_id=case_id)
    dossier["projection_only"] = True
    dossier["source_record_count"] = len(source_records)
    dossier["ais_record_count"] = len(signals)
    return dossier
