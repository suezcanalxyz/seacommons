# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live Observation → persisted Episode → InvestigationHypothesis wiring.

V1 persists only meaningful maritime episodes before hypothesis evaluation.
Single-observation detector wrappers remain durable as IntelEvent /
SourceObservation until corroboration or aggregation promotes them.
Low-specificity hypotheses require the episode-level independent-evidence
gate; detector count never substitutes for source independence. High-
specificity spoofing may remain a candidate on one lineage but cannot
advance to collecting without corroboration.

Legacy hypothesis rows are never relinked. New rows use a versioned ID
(`hyp:v1:...`) and always carry a non-null episode_id.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_INDEPENDENT_HUMANITARIAN_SOURCES = (
    "alarm phone",
    "alarm_phone",
    "sosmedintl",
    "msf_sea",
    "seawatchcrew",
    "sea watch",
    "sos méditerranée",
    "sos mediterranee",
)

from core.intel.episode_store import save_episode
from core.intel.hypothesis import (
    InvestigationHypothesis,
    can_publish,
    new_hypothesis,
    transition,
)
from core.intel.hypothesis_eligibility import evaluate_hypothesis_eligibility
from core.intel.hypothesis_store import get_hypothesis, list_hypotheses, save_hypothesis
from core.intel.store import IntelEvent, intel_store


def _normalize_independence_group(value: Any) -> str:
    text = str(value or "").strip()
    aliases = {
        "ais_sensor_lineage": "modality:ais",
        "ais": "modality:ais",
        "gfw_sar": "source:satellite:gfw",
        "satellite:gfw": "source:satellite:gfw",
        "radio:dsc": "source:radio:dsc",
        "radio_transmission": "source:radio:dsc",
    }
    return aliases.get(text, text)


def _canonical_verification(independence_groups: list[str] | tuple[str, ...], evidence_count: int) -> str:
    """Verification invariant: corroborated always means >=2 independent lineages."""
    group_count = len({
        _normalize_independence_group(value)
        for value in independence_groups
        if _normalize_independence_group(value)
    })
    if group_count >= 2:
        return "multi_source_corroborated"
    if int(evidence_count) >= 2:
        return "single_source_multi_indicator"
    return "single_source_observed"


def _event_mmsis(event: IntelEvent) -> tuple[str, ...]:
    metadata = event.metadata or {}
    candidates: list[Any] = [event.linked_mmsi, metadata.get("mmsi")]
    for vessel in metadata.get("vessels") or ():
        if isinstance(vessel, dict):
            candidates.extend((vessel.get("mmsi"), vessel.get("ssvid")))
        else:
            candidates.append(vessel)
    return tuple(dict.fromkeys(
        text for value in candidates
        if len((text := str(value or "").strip())) == 9 and text.isdigit()
    ))


def _attach_cross_modal_evidence(
    episode: dict[str, Any], events: list[IntelEvent],
) -> dict[str, Any]:
    """Attach independent sensor evidence without turning it into a verdict.

    A dark-ship cue can move a case into investigation only when an AIS
    lineage and a physically independent satellite detection are both present.
    An unmatched SAR detection remains a candidate, never corroborated identity.
    """
    from copy import deepcopy
    from datetime import datetime, timedelta, timezone

    from core.evidence.cross_modal import CrossModalEvidencePacket, EvidenceReference
    from core.evidence.cross_modal_analysis import evaluate_independence
    from core.intel.lifecycle import parse_utc

    refs: list[EvidenceReference] = []
    context_ids: list[str] = []
    reason_codes: set[str] = set()
    episode_props = episode.get("properties") or {}
    canonical_episode_id = str(episode_props.get("episode_id") or "").strip() or None
    for event in events:
        observed = parse_utc(event.timestamp_utc) or datetime.now(timezone.utc)
        if event.type in {"ais_anomaly", "ais_rendezvous", "ais_spike"}:
            confidence = float(((event.metadata or {}).get("gap_reason") or {}).get("confidence") or 0.5)
            refs.append(EvidenceReference(
                evidence_id=f"ais:{event.id}", evidence_class="ais_observation",
                source_lineage="ais_sensor_lineage", modality="ais",
                observed_at=observed, confidence=max(0.0, min(1.0, confidence)),
            ))
        cue = (event.metadata or {}).get("darkship_cue") or {}
        if not isinstance(cue, dict) or not (
            cue.get("gfw_sar_detections") or cue.get("gfw_unmatched_in_area")
        ):
            continue
        from core.intel.satellite_observation import (
            materialize_sar_detections,
            persist_observations,
        )

        satellite_observations = materialize_sar_detections(
            incident_id=event.id,
            cue=cue,
            expected_mmsi=event.linked_mmsi,
            episode_id=canonical_episode_id,
        )
        if satellite_observations:
            persist_observations(satellite_observations)
        for satellite in satellite_observations:
            det_at = parse_utc(satellite.acquisition_time) or observed
            if satellite.association_status == "strong" and satellite.episode_id:
                refs.append(EvidenceReference(
                    evidence_id=satellite.observation_id,
                    evidence_class="satellite_observation",
                    source_lineage="gfw_sar",
                    modality="satellite",
                    observed_at=det_at,
                    confidence=0.95,
                ))
                reason_codes.add("SATELLITE_DETECTION_ASSOCIATED_EXACT_MMSI")
            else:
                context_ids.append(satellite.observation_id)
                if satellite.association_status == "unmatched_candidate":
                    reason_codes.add("SATELLITE_CANDIDATE_IN_REACHABLE_AREA")

    # Close the loop with already-persisted independent evidence. Satellite
    # and radio associations can be created after the detector event that first
    # opened the episode; exact-MMSI humanitarian reports can arrive later too.
    # Only strong/identity-explicit associations enter the evidence packet.
    if canonical_episode_id:
        from sqlalchemy import func
        from core.db.models import (
            IntelEventDB, RadioAISAssociationDB, SatelliteObservationDB,
        )
        from core.db.session import session_scope

        linked_mmsis = sorted({
            value
            for item in events
            for value in _event_mmsis(item)
            if value
        })
        strong_satellite: list[dict[str, Any]] = []
        strong_radio: list[dict[str, Any]] = []
        humanitarian_rows: list[dict[str, Any]] = []
        try:
            with session_scope() as db:
                strong_satellite = [
                    {
                        "observation_id": row.observation_id,
                        "acquisition_time": row.acquisition_time,
                        "provider": row.provider,
                    }
                    for row in (
                        db.query(SatelliteObservationDB)
                        .filter(
                            SatelliteObservationDB.episode_id == canonical_episode_id,
                            SatelliteObservationDB.association_status == "strong",
                            SatelliteObservationDB.evidence_status == "associated",
                        )
                        .all()
                    )
                ]
                strong_radio = [
                    {
                        "observation_id": row.observation_id,
                        "ais_observed_at": row.ais_observed_at,
                        "confidence": row.confidence,
                    }
                    for row in (
                        db.query(RadioAISAssociationDB)
                        .filter(
                            RadioAISAssociationDB.episode_id == canonical_episode_id,
                            RadioAISAssociationDB.match_status == "strong",
                            RadioAISAssociationDB.episode_eligible.is_(True),
                        )
                        .all()
                    )
                ]
                if linked_mmsis:
                    humanitarian_rows = [
                        {
                            "id": row.id,
                            "source": row.source,
                            "timestamp_utc": row.timestamp_utc,
                        }
                        for row in (
                            db.query(IntelEventDB)
                            .filter(
                                IntelEventDB.linked_mmsi.in_(linked_mmsis),
                                IntelEventDB.maritime_domain == "sar",
                                IntelEventDB.source.isnot(None),
                                IntelEventDB.source != "",
                                func.lower(IntelEventDB.source).in_(_INDEPENDENT_HUMANITARIAN_SOURCES),
                            )
                            .order_by(IntelEventDB.created_at.desc())
                            .limit(100)
                            .all()
                        )
                    ]
        except Exception as exc:
            # Cross-modal closure is additive. A temporary DB/provider issue
            # must never suppress the underlying canonical episode.
            logger.debug("cross-modal persisted evidence lookup failed for %s: %s", canonical_episode_id, exc)

        for satellite in strong_satellite:
            det_at = parse_utc(satellite.get("acquisition_time")) or datetime.now(timezone.utc)
            refs.append(EvidenceReference(
                evidence_id=str(satellite["observation_id"]),
                evidence_class="satellite_observation",
                source_lineage=f"satellite:{satellite.get('provider') or 'unknown'}",
                modality="satellite",
                observed_at=det_at,
                confidence=0.95,
            ))
            reason_codes.add("SATELLITE_DETECTION_ASSOCIATED_EXACT_MMSI")

        for association in strong_radio:
            observed_at = parse_utc(association.get("ais_observed_at")) or datetime.now(timezone.utc)
            refs.append(EvidenceReference(
                evidence_id=f"radio:{association['observation_id']}",
                evidence_class="dsc_message",
                source_lineage="radio:dsc",
                modality="radio",
                observed_at=observed_at,
                confidence=max(0.0, min(1.0, float(association.get("confidence") or 0.0))),
            ))
            reason_codes.add("RADIO_DSC_ASSOCIATED_EXACT_MMSI")

        episode_start = parse_utc(episode_props.get("first_observed_at"))
        episode_end = parse_utc(episode_props.get("last_observed_at")) or episode_start
        for row in humanitarian_rows:
            source = str(row.get("source") or "").strip()
            if source.lower().startswith("ais") or source.lower().startswith("seacommons"):
                continue
            observed_at = parse_utc(row.get("timestamp_utc"))
            if observed_at is None:
                continue
            if episode_start is not None and observed_at < episode_start - timedelta(hours=6):
                continue
            if episode_end is not None and observed_at > episode_end + timedelta(hours=6):
                continue
            lineage = source.lower().replace(" ", "_") or "unknown"
            refs.append(EvidenceReference(
                evidence_id=f"humanitarian:{row['id']}",
                evidence_class="operational_claim",
                source_lineage=f"humanitarian:{lineage}",
                modality="humanitarian",
                observed_at=observed_at,
                confidence=0.8,
            ))
            reason_codes.add("HUMANITARIAN_REPORT_ASSOCIATED_EXACT_MMSI")

    if not refs:
        return episode
    subject_ids = tuple(str(v) for v in ((episode.get("properties") or {}).get("subject_ids") or ()) if v)
    if not subject_ids:
        return episode
    packet = CrossModalEvidencePacket(subject_id=subject_ids[0], evidence=tuple(refs))
    assessment = evaluate_independence(packet)
    updated = deepcopy(episode)
    props = updated.setdefault("properties", {})
    props["cross_modal_packet_id"] = packet.packet_id
    props["cross_modal_evidence_ids"] = [ref.evidence_id for ref in packet.evidence]
    props["cross_modal_context_ids"] = list(dict.fromkeys(context_ids))
    props["cross_modal_modalities"] = list(assessment.modalities)
    props["cross_modal_independence_groups"] = list(assessment.independence_groups)
    props["cross_modal_reason_codes"] = sorted(reason_codes)

    # Canonical closure: independent evidence must update the episode fields
    # that persistence, hypothesis eligibility and Live/Play actually read.
    # Detector count never substitutes for independent lineage count.
    existing_groups = {
        _normalize_independence_group(value)
        for value in (
            props.get("independence_groups")
            or props.get("contributing_independence_groups")
            or ()
        )
        if _normalize_independence_group(value)
    }
    canonical_groups = sorted(
        existing_groups
        | {
            _normalize_independence_group(value)
            for value in assessment.independence_groups
            if _normalize_independence_group(value)
        }
    )
    evidence_count = max(
        int(props.get("evidence_count") or 0),
        len(packet.evidence),
    )
    verification_status = _canonical_verification(canonical_groups, evidence_count)
    if verification_status == "multi_source_corroborated":
        props["analysis_state"] = "evidence"
        props["evidence_stage"] = "corroborated"
    props["independence_groups"] = canonical_groups
    props["independent_source_count"] = len(canonical_groups)
    props["evidence_count"] = evidence_count
    props["verification_status"] = verification_status
    props["cross_modal_investigation_ready"] = (
        len(canonical_groups) >= 2
        and "ais" in set(assessment.modalities)
        and bool({"satellite", "radio", "humanitarian"} & set(assessment.modalities))
    )
    return updated


def event_to_episode_input_feature(event: IntelEvent) -> Optional[dict[str, Any]]:
    """Build the internal feature used by the bounded episode builder."""
    from core.intel.analysis_state import annotate_event_analysis

    annotate_event_analysis(event)
    metadata = event.metadata or {}
    # Legacy AIS integrity gaps are short reappearance telemetry. Keep them
    # durable for audit/Play, but do not let them duplicate the canonical
    # MdaWatch dark-gap signal inside investigation episodes.
    if (
        event.id.startswith("aisanom:")
        and str(event.source or "").lower() == "ais"
        and str(metadata.get("anomaly_type") or "") == "gap"
    ):
        return None

    mmsis = _event_mmsis(event)
    if not mmsis:
        return None
    mmsi = mmsis[0]
    from core.mda.vessel_subject import subject_id_for

    # Use the same vessel identity enrichment as Public Live. Without this,
    # Live can canonicalize a vessel as subj:imo:* while the investigation
    # engine persists the same hull as subj:mmsi:*, splitting one case into
    # two episode IDs. IMO remains the preferred hull identity; MMSI is the
    # fallback when the registry has not learned an IMO yet.
    try:
        from core.vessels.registry import registry
        registry_cache = getattr(registry, "_cache", {}) or {}
    except Exception:  # pragma: no cover - registry enrichment is best effort
        registry_cache = {}
    vessel_rows = {value: (registry_cache.get(value, {}) or {}) for value in mmsis}
    subject_ids = tuple(
        subject_id_for(imo=vessel_rows[value].get("imo"), mmsi=value)
        or f"subj:mmsi:{value}"
        for value in mmsis
    )
    coordinates = [event.lon, event.lat] if event.lat is not None and event.lon is not None else []
    metadata = event.metadata or {}
    parent_ids = tuple(str(v) for v in (metadata.get("contributing") or ()) if v)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": coordinates},
        "properties": {
            "id": event.id,
            "timestamp_utc": event.timestamp_utc,
            "linked_mmsi": mmsi,
            "imo": vessel_rows.get(mmsi, {}).get("imo"),
            "subject_ids": list(subject_ids),
            "anomaly_type": metadata.get("anomaly_type"),
            "ais_nav_status_kind": metadata.get("ais_nav_status_kind"),
            "episode_family": metadata.get("episode_family"),
            "severity": event.severity,
            "source": event.source,
            "maritime_domain": event.maritime_domain(),
            "verification_status": metadata.get("verification_status"),
            "sanctions_matched": metadata.get("sanctions_matched"),
            "sanctions": metadata.get("sanctions"),
            "port_call": metadata.get("port_call"),
            "contributing_independence_groups": metadata.get(
                "contributing_independence_groups"
            ),
            "observation_ids": list(parent_ids or (event.id,)),
            "feature_ids": [event.id] if parent_ids else [],
            "incident_lifecycle": metadata.get("incident_lifecycle"),
            "behaviour_context": metadata.get("behaviour_context"),
            "alternative_explanations": metadata.get("alternative_explanations"),
            "analysis_state": metadata.get("analysis_state"),
            "publication_state": metadata.get("publication_state"),
            "resolution_state": metadata.get("resolution_state"),
            "lineage_ids": metadata.get("lineage_ids"),
            "gap_still_open": metadata.get("gap_still_open"),
            "current_silent_seconds": metadata.get("current_silent_seconds"),
        },
    }




def _case_opening_decision(
    props: dict[str, Any], events: list[IntelEvent],
) -> tuple[bool, tuple[str, ...]]:
    """Decide whether an episode deserves a public dossier, not a finding.

    Opening a dossier means the behaviour is specific enough to investigate
    and update over time. It does not change verification_status and does not
    imply independent corroboration, intent, illegality, or casualty.
    """
    family = str(props.get("episode_family") or "")
    if family == "gap_episode" and (
        props.get("gap_still_open") is False
        or str(props.get("resolution_state") or "") == "resolved"
        or any(
            (event.metadata or {}).get("gap_still_open") is False
            or (event.metadata or {}).get("resolution_state") == "resolved"
            for event in events
        )
    ):
        return False, ("AIS_GAP_REAPPEARED_RESOLVED",)

    analysis_state = str(props.get("analysis_state") or "")
    publication_state = str(props.get("publication_state") or "")
    if (
        publication_state == "published"
        and analysis_state in {"evidence_candidate", "evidence"}
    ):
        return True, ("PRODUCER_PUBLICATION_DECISION",)

    if family == "rendezvous_episode":
        from core.mda.offshore_context import build_offshore_context

        for event in events:
            meta = event.metadata or {}
            if str(meta.get("anomaly_type") or "") not in {
                "ais_rendezvous", "rendezvous", "sts",
            }:
                continue
            duration = float(meta.get("duration_min") or 0.0)
            dark = bool(meta.get("dark"))
            tanker = bool(meta.get("tanker"))
            if duration < 120.0 or not (dark or tanker):
                continue
            if event.lat is None or event.lon is None:
                continue
            context = build_offshore_context(
                float(event.lat), float(event.lon), include_ais_coverage=False
            )
            if not context.get("open_sea") or context.get("in_port_or_anchorage"):
                continue
            # A known STS/bunkering zone is routine context by itself. Require
            # a dark-party irregularity there before opening a public dossier.
            if context.get("sts_zone") and not dark:
                continue
            reasons = ["SUSTAINED_OPEN_SEA_RENDEZVOUS"]
            if tanker:
                reasons.append("TANKER_PARTICIPANT")
            if dark:
                reasons.append("AIS_GAP_CONTEXT_ON_PARTY")
            return True, tuple(reasons)

    if family == "spoofing_episode":
        from core.mda.offshore_context import build_offshore_context

        for event in events:
            meta = event.metadata or {}
            if str(meta.get("anomaly_type") or "") != "position_jump":
                continue
            classification = meta.get("ais_integrity_classification")
            if not isinstance(classification, dict):
                continue
            if (
                classification.get("label") != "position_anomaly"
                or float(classification.get("confidence") or 0.0) < 0.8
                or meta.get("teleport_pattern") != "sustained_relocation"
                or bool(meta.get("coincident_teleport_peers"))
                or event.lat is None
                or event.lon is None
            ):
                continue
            context = build_offshore_context(
                float(event.lat), float(event.lon), include_ais_coverage=False
            )
            if not context.get("open_sea") or context.get("in_port_or_anchorage"):
                continue
            return True, (
                "SUSTAINED_POSITION_RELOCATION",
                "HIGH_CONFIDENCE_POSITION_INTEGRITY_ANOMALY",
                "NO_COINCIDENT_MULTI_VESSEL_GLITCH",
                "OPEN_SEA_CONTEXT",
            )

    if family == "infrastructure_proximity_episode":
        from core.mda.offshore_context import build_offshore_context

        for event in events:
            meta = event.metadata or {}
            anomaly = str(meta.get("anomaly_type") or "")
            loiter_min = float(meta.get("loiter_minutes") or 0.0)
            if anomaly == "sanctions_bunkering_loiter" and loiter_min >= 90.0:
                strong_hits = [
                    hit for hit in (meta.get("sanctions") or ())
                    if isinstance(hit, dict)
                    and set(hit.get("matched_on") or ()) & {"imo", "mmsi"}
                ]
                if strong_hits:
                    return True, (
                        "STRONG_SANCTIONS_IDENTITY_MATCH",
                        "SUSTAINED_STS_ZONE_DWELL",
                    )
            infra = meta.get("infrastructure")
            if (
                anomaly not in {"cable_proximity", "loiter"}
                or not isinstance(infra, dict)
                or str(infra.get("kind") or "") not in {"cable", "pipeline"}
                or float(infra.get("distance_km") or 999.0) > 2.0
                or loiter_min < 120.0
                or event.lat is None
                or event.lon is None
            ):
                continue
            behaviour = meta.get("behaviour_context") or {}
            if isinstance(behaviour, dict) and behaviour.get("status") == "expected":
                continue
            context = build_offshore_context(
                float(event.lat), float(event.lon), include_ais_coverage=False
            )
            if context.get("open_sea") and not context.get("in_port_or_anchorage"):
                return True, (
                    "SUSTAINED_INFRASTRUCTURE_PROXIMITY",
                    "OPEN_SEA_CONTEXT",
                )

    if family == "safety_episode":
        from core.mda.offshore_context import build_offshore_context
        from core.mda.reference import reference

        for event in events:
            meta = event.metadata or {}
            nav_kind = str(
                meta.get("ais_nav_status_kind")
                or meta.get("anomaly_type")
                or ""
            )
            if event.lat is None or event.lon is None:
                continue
            lat, lon = float(event.lat), float(event.lon)
            if reference.in_port_or_anchorage(lat, lon) or reference.is_land(lat, lon):
                continue
            updates = int(meta.get("episode_update_count") or 0)
            if (
                nav_kind == "distress_beacon"
                and event.type == "distress"
                and (bool(meta.get("beacon_repeat_confirmed")) or updates >= 2)
            ):
                return True, (
                    "REPEATED_AIS_DISTRESS_BEACON",
                    "OUTSIDE_PORT_AND_LAND_CONTEXT",
                )
            if (
                nav_kind == "not_under_command"
                and event.type == "vessel_incident"
                and updates >= 3
            ):
                context = build_offshore_context(
                    lat, lon, include_ais_coverage=False
                )
                if context.get("open_sea"):
                    return True, (
                        "PERSISTENT_AIS_REPORTED_SAFETY_STATE",
                        "OPEN_SEA_CONTEXT",
                    )

    return False, ()


def _apply_case_opening(
    episode: dict[str, Any], events: list[IntelEvent],
) -> dict[str, Any]:
    props = episode.setdefault("properties", {})
    opened, reason_codes = _case_opening_decision(props, events)
    if not opened:
        return episode
    props["publication_state"] = "published"
    if str(props.get("analysis_state") or "") not in {
        "evidence_candidate", "evidence",
    }:
        props["analysis_state"] = "evidence_candidate"
    props.setdefault("resolution_state", "open")
    behaviour = dict(props.get("behaviour_context") or {})
    behaviour["case_opening"] = {
        "reason_codes": list(reason_codes),
        "scope": "investigation_dossier_not_finding",
    }
    props["behaviour_context"] = behaviour
    return episode


def _should_persist_episode(props: dict[str, Any]) -> bool:
    """Persist aggregation, not one-detector wrappers. Raw signals stay durable."""
    family = str(props.get("episode_family") or "unclassified_episode")
    if family == "unclassified_episode":
        # Unknown analytical semantics stay in the durable event/archive layer.
        # Persisting them as episodes makes telemetry look like intelligence.
        return False
    signal_count = int(props.get("signal_count") or 0)
    evidence_count = int(props.get("evidence_count") or 0)
    independent = int(props.get("independent_source_count") or 0)
    verification = str(props.get("verification_status") or "")
    analysis_state = str(props.get("analysis_state") or "")
    publication_state = str(props.get("publication_state") or "")
    if family in {"safety_episode", "port_call_episode"} and analysis_state in {"signal", "evidence"}:
        return True
    # Live/Play must share one canonical case object. If a qualified episode is
    # explicitly publishable as evidence_candidate/evidence, persist that
    # episode even when it currently has only one child observation. Raw
    # detector events remain separate durable evidence.
    if (
        publication_state == "published"
        and analysis_state in {"evidence_candidate", "evidence"}
    ):
        return True
    if bool(props.get("cross_modal_investigation_ready")):
        return True
    if verification == "multi_source_corroborated" or independent >= 2:
        return True
    if signal_count >= 2 and evidence_count >= 2:
        return True
    return False

def evaluate_episode(episode: dict[str, Any]) -> Optional[InvestigationHypothesis]:
    """Persist the episode, then create/update a v1 hypothesis only when eligible."""
    props = episode.get("properties") or {}
    episode_id = str(props.get("episode_id") or "")
    subject_ids = tuple(str(s) for s in (props.get("subject_ids") or ()) if s)
    if not episode_id or not subject_ids:
        return None

    signal_ids = tuple(str(s) for s in (props.get("related_signal_ids") or ()) if s)
    events = [e for e in (intel_store.get_durable(sid) for sid in signal_ids) if e is not None]
    if events:
        episode = _attach_cross_modal_evidence(episode, events)
        episode = _apply_case_opening(episode, events)
        props = episode.get("properties") or {}

    # SourceObservation/IntelEvent are the durable anomaly archive. An episode
    # is materialised only when it adds aggregation or corroboration.
    if not _should_persist_episode(props):
        return None
    save_episode(episode)
    from core.observability import record_maritime_episode_evaluation

    record_maritime_episode_evaluation(
        str(props.get("episode_family") or "unclassified_episode"),
        str(props.get("verification_status") or "single_source_observed"),
    )
    if not events:
        return None

    decision = evaluate_hypothesis_eligibility(episode, events)
    from core.observability import record_v1_hypothesis_decision

    record_v1_hypothesis_decision(
        str(decision.hypothesis_type or "none"),
        "eligible" if decision.eligible else "ineligible",
    )
    if not decision.eligible or decision.hypothesis_type is None:
        return None

    hypothesis_type = decision.hypothesis_type
    base_hypothesis_id = f"hyp:v1:{hypothesis_type}:{episode_id}"
    existing = get_hypothesis(base_hypothesis_id)

    evidence_links = tuple(dict.fromkeys((
        *signal_ids,
        *(str(v) for v in (props.get("cross_modal_evidence_ids") or ()) if v),
    )))
    episode_groups = {
        str(value) for value in (
            props.get("contributing_independence_groups")
            or props.get("independence_groups")
            or ()
        ) if value
    }
    independently_corroborated = (
        str(props.get("verification_status") or "") == "multi_source_corroborated"
        or len(episode_groups) >= 2
        or int(props.get("independent_source_count") or 0) >= 2
    )

    reopened_from: str | None = None
    if existing is not None and existing.state == "expired" and independently_corroborated:
        # Expired is intentionally terminal. New independent evidence creates
        # a new investigation generation instead of rewriting history.
        digest = hashlib.blake2s(
            f"{hypothesis_type}|{episode_id}".encode(), digest_size=8
        ).hexdigest()
        hypothesis_id = f"hyp:v2:{hypothesis_type}:{digest}"
        reopened_from = existing.hypothesis_id
        reopened = get_hypothesis(hypothesis_id)
        hyp = reopened or new_hypothesis(
            hypothesis_id,
            hypothesis_type,
            subject_ids,
            episode_id=episode_id,
        )
    elif existing is None:
        hypothesis_id = base_hypothesis_id
        hyp = new_hypothesis(
            hypothesis_id,
            hypothesis_type,
            subject_ids,
            episode_id=episode_id,
        )
    else:
        hypothesis_id = base_hypothesis_id
        if existing.episode_id != episode_id:
            raise ValueError("v1 hypothesis episode identity mismatch")
        hyp = existing
    reason_codes = tuple(decision.reason_codes)
    if reopened_from:
        reason_codes = tuple(dict.fromkeys((*reason_codes, "REOPENED_AFTER_INDEPENDENT_CORROBORATION")))
    hyp = replace(
        hyp,
        reason_codes=reason_codes,
        counter_indicators=decision.counter_indicators,
        evidence_links=evidence_links,
        evidence_stage=decision.evidence_stage,
    )
    transition_actor = (
        f"hypothesis_engine_v2_reopen:{reopened_from}"
        if reopened_from else "hypothesis_engine_v1"
    )

    if hyp.state == "candidate" and decision.may_advance_collecting:
        from core.observability import record_hypothesis_transition

        hyp = transition(hyp, "collecting", actor=transition_actor)
        record_hypothesis_transition(hyp.hypothesis_type, hyp.state)

    # Crossing into review_ready is deliberately narrower than entering
    # collection. High-specificity single-lineage AIS cues and unmatched SAR
    # candidates may justify investigation, but only independently
    # corroborated evidence can become a reviewable public case.
    distinct_evidence = {str(value) for value in hyp.evidence_links if value}
    if (
        hyp.state == "collecting"
        and independently_corroborated
        and decision.evidence_stage in {"corroborated", "assessed", "confirmed"}
        and len(distinct_evidence) >= 2
        and bool(hyp.reason_codes)
    ):
        from core.observability import record_hypothesis_transition

        hyp = transition(hyp, "review_ready", actor=transition_actor)
        record_hypothesis_transition(hyp.hypothesis_type, hyp.state)

    # Reopened historical investigations stop at review_ready. This preserves
    # auditability and prevents an old case from re-entering Live merely
    # because a backfill discovered independent evidence later.
    if reopened_from and hyp.state == "review_ready":
        save_hypothesis(hyp)
        return hyp

    # Automatic publication (product decision, 2026-09-21 -- see
    # docs/current_work.md and docs/superpowers/plans/2026-09-21-live-
    # pipeline-funnel-audit.md): this replaces the human analyst
    # `transition(hyp, "assessed"/"published", actor="analyst:...")` step
    # docs/fixes.md M14.6 originally required as "the only path past
    # candidate/collecting". It does NOT relax any evidence requirement --
    # review_ready was already gated on the same independent-corroboration/
    # evidence_stage/reason_codes bar can_publish() re-verifies below, and
    # every gate above (per-hypothesis-type evidence gates, the low-
    # specificity independent-corroboration gate, docs/fixes.md M6's own
    # six gate functions) still requires >=2 independent evidence lineages
    # before a hypothesis is even eligible to reach this point. What
    # changes is only who/what performs the review_ready -> assessed ->
    # published transition: the same system actor
    # ("hypothesis_engine_v1") that already performs every earlier
    # transition, recorded honestly in audit_history rather than
    # attributed to a human. has_unresolved_blocking_identity_conflict and
    # allegation_shaped_wording are never set true by this engine today
    # (both stay at their False default), so can_publish() cannot yet
    # block on either -- if a future hypothesis_type sets
    # allegation_shaped_wording, can_publish() will correctly stop this
    # automatic path at "assessed" and require a human explicit_review_done
    # without any change needed here.
    if hyp.state == "review_ready":
        from core.observability import record_hypothesis_transition

        hyp = transition(hyp, "assessed", actor="hypothesis_engine_v1")
        record_hypothesis_transition(hyp.hypothesis_type, hyp.state)

    if hyp.state == "assessed":
        publishable, _reason = can_publish(hyp)
        if publishable:
            from core.observability import record_hypothesis_transition

            hyp = transition(hyp, "published", actor="hypothesis_engine_v1")
            record_hypothesis_transition(hyp.hypothesis_type, hyp.state)

    save_hypothesis(hyp)
    return hyp




def reconcile_cross_modal_episodes(*, hours: int = 168, limit: int = 500) -> dict[str, int]:
    """Re-evaluate canonical episodes after independent evidence arrives later.

    ``hours <= 0`` enables an explicit historical backfill over all persisted
    strong associations. The scheduler keeps using the bounded seven-day mode.
    Expired hypotheses are never mutated back into an active state: qualifying
    independent evidence opens an auditable v2 investigation generation.
    """
    from datetime import datetime, timedelta, timezone

    from core.db.models import (
        IntelEventDB,
        MaritimeEpisodeDB,
        RadioAISAssociationDB,
        SatelliteObservationDB,
    )
    from core.db.session import session_scope
    from core.mda.vessel_subject import subject_id_for

    cutoff = (
        (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(tzinfo=None)
        if hours > 0 else None
    )
    candidate_ids: set[str] = set()
    humanitarian_subjects: set[str] = set()

    with session_scope() as db:
        satellite_query = db.query(SatelliteObservationDB.episode_id).filter(
            SatelliteObservationDB.episode_id.isnot(None),
            SatelliteObservationDB.association_status == "strong",
            SatelliteObservationDB.evidence_status == "associated",
        )
        if cutoff is not None:
            satellite_query = satellite_query.filter(SatelliteObservationDB.created_at >= cutoff)
        candidate_ids.update(
            str(value)
            for (value,) in satellite_query.distinct().limit(limit).all()
            if value
        )

        radio_query = db.query(RadioAISAssociationDB.episode_id).filter(
            RadioAISAssociationDB.episode_id.isnot(None),
            RadioAISAssociationDB.match_status == "strong",
            RadioAISAssociationDB.episode_eligible.is_(True),
        )
        if cutoff is not None:
            radio_query = radio_query.filter(RadioAISAssociationDB.created_at >= cutoff)
        candidate_ids.update(
            str(value)
            for (value,) in radio_query.distinct().limit(limit).all()
            if value
        )

        from sqlalchemy import func

        humanitarian_query = db.query(IntelEventDB.linked_mmsi).filter(
            IntelEventDB.maritime_domain == "sar",
            IntelEventDB.linked_mmsi.isnot(None),
            IntelEventDB.linked_mmsi != "",
            IntelEventDB.source.isnot(None),
            IntelEventDB.source != "",
            func.lower(IntelEventDB.source).in_(_INDEPENDENT_HUMANITARIAN_SOURCES),
        )
        if cutoff is not None:
            humanitarian_query = humanitarian_query.filter(IntelEventDB.created_at >= cutoff)
        humanitarian_mmsis = {
            str(value)
            for (value,) in humanitarian_query.distinct().all()
            if value
        }

    if humanitarian_mmsis:
        try:
            from core.vessels.registry import registry

            cache = getattr(registry, "_cache", {}) or {}
        except Exception:
            cache = {}
        for mmsi in humanitarian_mmsis:
            humanitarian_subjects.add(f"subj:mmsi:{mmsi}")
            subject = subject_id_for(imo=(cache.get(mmsi, {}) or {}).get("imo"), mmsi=mmsi)
            if subject:
                humanitarian_subjects.add(subject)

    with session_scope() as db:
        rows_by_id: dict[str, Any] = {}

        # Strong satellite/radio associations already carry an exact episode
        # id, so load those rows directly even when they are old.
        if candidate_ids:
            for row in (
                db.query(MaritimeEpisodeDB)
                .filter(
                    MaritimeEpisodeDB.episode_id.in_(sorted(candidate_ids)),
                    MaritimeEpisodeDB.status == "active",
                )
                .all()
            ):
                rows_by_id[str(row.episode_id)] = row

        # Humanitarian exact-MMSI closure is subject-based rather than episode-id
        # based. Keep the scheduler bounded by updated_at; explicit historical
        # backfill may scan the durable episode table once.
        if humanitarian_subjects and len(rows_by_id) < limit:
            humanitarian_query = db.query(MaritimeEpisodeDB).filter(
                MaritimeEpisodeDB.status == "active",
            )
            if cutoff is not None:
                humanitarian_query = humanitarian_query.filter(MaritimeEpisodeDB.updated_at >= cutoff)
                scan_limit = max(limit * 4, 500)
            else:
                scan_limit = max(limit * 20, 50000)
            for row in humanitarian_query.order_by(MaritimeEpisodeDB.updated_at.desc()).limit(scan_limit):
                subjects = {str(value) for value in (row.subject_ids or ()) if value}
                if subjects & humanitarian_subjects:
                    rows_by_id.setdefault(str(row.episode_id), row)
                    if len(rows_by_id) >= limit:
                        break

        episode_rows: list[dict[str, Any]] = []
        for row in sorted(
            rows_by_id.values(),
            key=lambda value: value.updated_at or value.created_at,
            reverse=True,
        )[:limit]:
            episode_rows.append({
                "episode_id": row.episode_id,
                "episode_family": row.episode_family,
                "subject_ids": list(row.subject_ids or ()),
                "start_at": row.start_at,
                "end_at": row.end_at,
                "geometry": row.geometry,
                "observation_ids": list(row.observation_ids or ()),
                "feature_ids": list(row.feature_ids or ()),
                "independence_groups": list(row.independence_groups or ()),
                "verification_status": row.verification_status,
                "behaviour_context": dict(row.behaviour_context or {}),
                "alternative_explanations": list(row.alternative_explanations or ()),
                "status": row.status,
            })

    evaluated = updated = skipped = failed = reopened = 0
    for row in episode_rows:
        evidence_ids = list(dict.fromkeys([
            *row["observation_ids"],
            *row["feature_ids"],
        ]))
        durable_event_ids = [
            value for value in evidence_ids if intel_store.get_durable(str(value)) is not None
        ]
        if not durable_event_ids:
            skipped += 1
            continue
        start_at = row["start_at"]
        end_at = row["end_at"] or start_at
        start_iso = start_at.replace(tzinfo=timezone.utc).isoformat() if start_at and start_at.tzinfo is None else start_at.isoformat()
        end_iso = end_at.replace(tzinfo=timezone.utc).isoformat() if end_at and end_at.tzinfo is None else end_at.isoformat()
        analysis = (row["behaviour_context"].get("analysis") or {})
        feature = {
            "type": "Feature",
            "geometry": row["geometry"],
            "properties": {
                "episode_id": row["episode_id"],
                "episode_family": row["episode_family"],
                "subject_ids": row["subject_ids"],
                "related_signal_ids": durable_event_ids,
                "observation_ids": durable_event_ids,
                "feature_ids": row["feature_ids"],
                "first_observed_at": start_iso,
                "last_observed_at": end_iso,
                "verification_status": row["verification_status"],
                "independence_groups": row["independence_groups"],
                "independent_source_count": len(set(row["independence_groups"])),
                "signal_count": len(durable_event_ids),
                "evidence_count": max(1, len(durable_event_ids)),
                "analysis_state": analysis.get("analysis_state") or "evidence_candidate",
                "publication_state": analysis.get("publication_state") or "internal",
                "resolution_state": analysis.get("resolution_state") or "open",
                "behaviour_context": row["behaviour_context"],
                "alternative_explanations": row["alternative_explanations"],
                "episode_status": row["status"],
            },
        }
        try:
            before = row["verification_status"]
            hypothesis = evaluate_episode(feature)
            evaluated += 1
            with session_scope() as db:
                refreshed = db.get(MaritimeEpisodeDB, row["episode_id"])
                after = refreshed.verification_status if refreshed is not None else before
            if hypothesis is not None and hypothesis.hypothesis_id.startswith("hyp:v2:"):
                reopened += 1
            if after != before or hypothesis is not None:
                updated += 1
        except Exception:
            failed += 1

    return {
        "candidates": len(episode_rows),
        "evaluated": evaluated,
        "updated": updated,
        "reopened": reopened,
        "skipped": skipped,
        "failed": failed,
    }


def expire_stale_hypotheses(
    *, now: Optional[Any] = None, stale_after: Optional[Any] = None,
) -> int:
    """Transition candidate/collecting hypotheses whose evidence has gone
    quiet for 24h into "expired" (docs section 4: the 24h Live window is an
    investigation decision window, not an indefinite hold).

    Uses episode/evidence time, never updated_at: updated_at bumps on every
    no-op re-evaluation (the same episode being re-scanned without new
    evidence), which would make a truly stale hypothesis look perpetually
    fresh. The expired hypothesis remains durable (for audit) but drops out
    of both Live and Play once its state is no longer candidate/collecting.
    """
    from datetime import datetime, timedelta, timezone

    from core.db.models import IntelEventDB, MaritimeEpisodeDB
    from core.db.session import session_scope
    from core.intel.lifecycle import parse_utc

    now = now or datetime.now(timezone.utc)
    stale_after = stale_after or timedelta(hours=24)
    expired_count = 0
    with session_scope() as db:
        for state in ("candidate", "collecting"):
            for hyp in list_hypotheses(state=state, limit=5000):
                last_evidence_at = None
                if hyp.episode_id:
                    episode = db.get(MaritimeEpisodeDB, hyp.episode_id)
                    if episode is not None and episode.end_at is not None:
                        last_evidence_at = episode.end_at
                if last_evidence_at is None and hyp.evidence_links:
                    rows = (
                        db.query(IntelEventDB)
                        .filter(IntelEventDB.id.in_(list(hyp.evidence_links)))
                        .all()
                    )
                    timestamps = [t for t in (parse_utc(r.timestamp_utc) for r in rows) if t is not None]
                    if timestamps:
                        last_evidence_at = max(timestamps)
                if last_evidence_at is None:
                    continue
                if last_evidence_at.tzinfo is None:
                    last_evidence_at = last_evidence_at.replace(tzinfo=timezone.utc)
                if now - last_evidence_at < stale_after:
                    continue
                expired = transition(hyp, "expired", actor="hypothesis_engine_v1_expiry")
                save_hypothesis(expired)
                expired_count += 1
    return expired_count
