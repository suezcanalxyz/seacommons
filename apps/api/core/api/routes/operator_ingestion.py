# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private operator view of the canonical ingestion pipeline.

This surface is deliberately separate from public Live/Play. It exposes the
durable source-observation envelope, inbound connector payloads and normalized
IntelEvent output so an operator can inspect parsing/ingestion end to end.

The route is authenticated by a gateway secret injected server-side by the
operator reverse proxy. The browser never receives that secret.
"""
from __future__ import annotations

import hmac
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, or_, text

from core.config import config
from core.db.models import (
    IngestedSignalDB,
    IntelEventDB,
    InvestigationHypothesisDB,
    MaritimeEpisodeDB,
    RadioBurstDB,
    RadioEventDB,
    SatelliteObservationDB,
    SourceObservationDB,
    VesselTrackDB,
    VesselBehaviouralBaselineDB,
)
from core.db.session import session_scope
from core.api.routes.operator_pipeline import (
    event_chain_id,
    hypothesis_semantics,
    observation_chain_id,
    pipeline_chains,
)

router = APIRouter(prefix="/api/v1/operator/ingestion", tags=["operator-ingestion"])

_OVERALL_CACHE_TTL_S = 300.0
_OPERATOR_FAST_CACHE_TTL_S = 10.0
_overall_cache_lock = threading.Lock()
_overall_cache: tuple[float, dict[str, Any]] | None = None
_fast_cache_lock = threading.Lock()
_fast_cache: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}


def _fast_cache_get(kind: str, hours: int) -> dict[str, Any] | None:
    now_mono = time.monotonic()
    with _fast_cache_lock:
        cached = _fast_cache.get((kind, hours))
        if cached and now_mono - cached[0] < (_OVERALL_CACHE_TTL_S if kind == "overall_metrics" else _OPERATOR_FAST_CACHE_TTL_S):
            return cached[1]
    return None


def _fast_cache_put(kind: str, hours: int, payload: dict[str, Any]) -> dict[str, Any]:
    with _fast_cache_lock:
        _fast_cache[(kind, hours)] = (time.monotonic(), payload)
    return payload


def _fast_table_count(db, model) -> tuple[int, bool]:
    """Fast row count for dashboard capacity metrics.

    PostgreSQL exact COUNT(*) over the multi-million-row AIS track table can
    exceed the API statement timeout. Planner/statistics estimates are adequate
    for a capacity counter and are explicitly labelled as estimated. SQLite and
    other test backends keep exact semantics.
    """
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        table = str(model.__tablename__)
        estimate = db.execute(
            text(
                """
                SELECT COALESCE(NULLIF(s.n_live_tup, 0), c.reltuples, 0)::bigint
                FROM pg_class c
                LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
                WHERE c.relname = :table
                  AND c.relnamespace = current_schema()::regnamespace
                LIMIT 1
                """
            ),
            {"table": table},
        ).scalar()
        if estimate is not None:
            return max(0, int(estimate)), True
    return int(db.query(func.count(model.id)).scalar() or 0), False


def _require_gateway(request: Request) -> None:
    # The same verified Futures session grants access to Intelligence.
    # Preserve the legacy gateway only for internal compatibility.
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        from core.security import require_futures_identity
        require_futures_identity(request)
        return
    expected = str(config.OPERATOR_GATEWAY_SECRET or "")
    if not expected:
        raise HTTPException(status_code=503, detail="Operator ingestion gateway is not configured")
    supplied = request.headers.get("x-seacommons-operator-gateway", "")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Operator gateway authentication required")


def _dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _since(hours: int) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)


@router.get("/sar-fleet")
def operator_sar_fleet(request: Request) -> dict[str, Any]:
    """Authenticated operational inventory for civil + state SAR assets.

    Fleet presence and AIS freshness belong to the operator surface, not the
    public Live case feed. Stale coordinates are withheld by ngo_vessel_geojson.
    """
    _require_gateway(request)
    from core.intel.ngo_registry import ngo_vessel_geojson

    return ngo_vessel_geojson()


def _source_observation(row: SourceObservationDB) -> dict[str, Any]:
    semantic_label = (
        "AIS reappearance after sampled silence"
        if row.observation_type == "ais_gap"
        else row.observation_type
    )
    return {
        "kind": "source_observation",
        "pipeline_role": "raw_observation",
        "parser_chain_id": observation_chain_id(row.source_name, row.observation_type),
        "semantic_label": semantic_label,
        "observation_id": row.observation_id,
        "service": row.service,
        "lane": row.lane,
        "observation_type": row.observation_type,
        "source_name": row.source_name,
        "source_policy": row.source_policy,
        "source_id": row.source_id,
        "source_url": row.source_url or "",
        "observed_at": row.observed_at,
        "received_at": _dt(row.received_at),
        "raw_payload_hash": row.raw_payload_hash,
        "raw_payload_ref": row.raw_payload_ref or "",
        "lat": row.lat,
        "lon": row.lon,
        "location_precision": row.location_precision,
        "uncertainty_m": row.uncertainty_m,
        "subject_refs": list(row.subject_refs or []),
        "provenance": dict(row.provenance or {}),
        "schema_version": row.schema_version,
        "preservation_status": row.preservation_status,
    }


def _intel_event(row: IntelEventDB) -> dict[str, Any]:
    metadata = dict(row.meta or {})
    legacy_gap = (
        str(row.source or "").lower() == "ais"
        and row.type == "ais_anomaly"
        and str(metadata.get("anomaly_type") or "") == "gap"
        and row.id.startswith("aisanom:")
    )
    mda_gap = (
        str(row.source or "").lower() == "mda"
        and row.type == "ais_anomaly"
        and str(metadata.get("anomaly_type") or "") in {"gap", "long_gap"}
    )
    semantic_label = (
        "AIS telemetry gap cue (legacy context; not an investigation)"
        if legacy_gap
        else "MDA vessel-specific dark-gap cue"
        if mda_gap
        else row.title
    )
    return {
        "kind": "parsed_event",
        "pipeline_role": (
            "context_telemetry" if legacy_gap else "derived_cue" if mda_gap else "normalized_event"
        ),
        "parser_chain_id": event_chain_id(row.source, row.type, metadata),
        "semantic_label": semantic_label,
        "event_id": row.id,
        "timestamp_utc": row.timestamp_utc,
        "source_timestamp_utc": row.source_timestamp_utc,
        "received_at": _dt(row.received_at or row.created_at),
        "type": row.type,
        "severity": row.severity,
        "source": row.source,
        "title": row.title,
        "text": row.text or "",
        "url": row.url or "",
        "lat": row.lat,
        "lon": row.lon,
        "linked_mmsi": row.linked_mmsi or "",
        "maritime_domain": row.maritime_domain,
        "operational_tier": row.operational_tier,
        "humanitarian_case_type": row.humanitarian_case_type,
        "incident_lifecycle": row.incident_lifecycle,
        "location_status": row.location_status,
        "coordinate_review_status": row.coordinate_review_status,
        "location_uncertainty_m": row.location_uncertainty_m,
        "schema_version": row.schema_version,
        "metadata": metadata,
    }


def _ingested_signal(row: IngestedSignalDB) -> dict[str, Any]:
    return {
        "kind": "ingested_signal",
        "signal_id": row.signal_id,
        "organization_id": row.organization_id,
        "connector_id": row.connector_id,
        "source_channel": row.source_channel,
        "source_id": row.source_id,
        "provider_message_id": row.provider_message_id,
        "received_at": _dt(row.received_at),
        "payload": dict(row.payload or {}),
    }


@router.get("/overview")
def operator_ingestion_overview(
    request: Request,
    hours: int = Query(24, ge=1, le=720),
) -> dict[str, Any]:
    _require_gateway(request)
    return _overview_payload(hours)


def _overview_payload(hours: int) -> dict[str, Any]:
    cached = _fast_cache_get("overview", hours)
    if cached is not None:
        return cached
    cutoff = _since(hours)
    with session_scope() as db:
        raw_total = (
            db.query(func.count(SourceObservationDB.observation_id))
            .filter(SourceObservationDB.received_at >= cutoff)
            .scalar()
            or 0
        )
        event_total = (
            db.query(func.count(IntelEventDB.id))
            .filter(IntelEventDB.received_at >= cutoff)
            .scalar()
            or 0
        )
        signal_total = (
            db.query(func.count(IngestedSignalDB.signal_id))
            .filter(IngestedSignalDB.received_at >= cutoff)
            .scalar()
            or 0
        )
        raw_by_source = dict(
            db.query(SourceObservationDB.source_name, func.count(SourceObservationDB.observation_id))
            .filter(SourceObservationDB.received_at >= cutoff)
            .group_by(SourceObservationDB.source_name)
            .order_by(func.count(SourceObservationDB.observation_id).desc())
            .limit(100)
            .all()
        )
        raw_by_type = dict(
            db.query(SourceObservationDB.observation_type, func.count(SourceObservationDB.observation_id))
            .filter(SourceObservationDB.received_at >= cutoff)
            .group_by(SourceObservationDB.observation_type)
            .order_by(func.count(SourceObservationDB.observation_id).desc())
            .limit(100)
            .all()
        )
        events_by_source = dict(
            db.query(IntelEventDB.source, func.count(IntelEventDB.id))
            .filter(IntelEventDB.received_at >= cutoff)
            .group_by(IntelEventDB.source)
            .order_by(func.count(IntelEventDB.id).desc())
            .limit(100)
            .all()
        )
        events_by_type = dict(
            db.query(IntelEventDB.type, func.count(IntelEventDB.id))
            .filter(IntelEventDB.received_at >= cutoff)
            .group_by(IntelEventDB.type)
            .order_by(func.count(IntelEventDB.id).desc())
            .limit(100)
            .all()
        )
        newest_raw = db.query(func.max(SourceObservationDB.received_at)).scalar()
        newest_event = db.query(func.max(IntelEventDB.received_at)).scalar()
        newest_signal = db.query(func.max(IngestedSignalDB.received_at)).scalar()

        # Operator dashboard hot path: keep this independent of public Live
        # projection. build_public_status() performs publication projection and
        # geo/context work that is useful for /status but made the operator
        # console wait >10s on a cold request.
        ais_fixes = int(
            db.query(func.count(VesselTrackDB.id))
            .filter(VesselTrackDB.ts >= cutoff)
            .scalar()
            or 0
        )
        radio_bursts = int(
            db.query(func.count(RadioBurstDB.burst_id))
            .filter(RadioBurstDB.created_at >= cutoff)
            .scalar()
            or 0
        )
        radio_events = int(
            db.query(func.count(RadioEventDB.event_id))
            .filter(RadioEventDB.created_at >= cutoff)
            .scalar()
            or 0
        )
        satellite_observations = int(
            db.query(func.count(SatelliteObservationDB.observation_id))
            .filter(SatelliteObservationDB.discovered_at >= cutoff)
            .scalar()
            or 0
        )
        episodes_total = int(
            db.query(func.count(MaritimeEpisodeDB.episode_id))
            .filter(
                MaritimeEpisodeDB.updated_at >= cutoff,
                MaritimeEpisodeDB.episode_family != "unclassified_episode",
            )
            .scalar()
            or 0
        )
        hypotheses_total = int(
            db.query(func.count(InvestigationHypothesisDB.hypothesis_id))
            .filter(
                InvestigationHypothesisDB.updated_at >= cutoff,
                InvestigationHypothesisDB.state.notin_(("expired", "rejected")),
            )
            .scalar()
            or 0
        )
        newest_analysis = max(
            (
                db.query(func.max(MaritimeEpisodeDB.updated_at)).scalar(),
                db.query(func.max(InvestigationHypothesisDB.updated_at)).scalar(),
            ),
            key=lambda value: value or datetime.min,
        )

    try:
        from core.acquisition.status import acquisition_status_sources
        acquisition = acquisition_status_sources()
    except Exception:
        acquisition = []
    try:
        from core.intel.source_registry import source_registry
        sources = source_registry.get_all()
    except Exception:
        sources = []

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache_ttl_seconds": int(_OPERATOR_FAST_CACHE_TTL_S),
        "lookback_hours": hours,
        "counts": {
            "source_observations": int(raw_total),
            "parsed_events": int(event_total),
            "ingested_signals": int(signal_total),
        },
        "newest": {
            "source_observation": _dt(newest_raw),
            "parsed_event": _dt(newest_event),
            "ingested_signal": _dt(newest_signal),
        },
        "source_observations": {
            "by_source": {str(k): int(v) for k, v in raw_by_source.items()},
            "by_type": {str(k): int(v) for k, v in raw_by_type.items()},
        },
        "parsed_events": {
            "by_source": {str(k): int(v) for k, v in events_by_source.items()},
            "by_type": {str(k): int(v) for k, v in events_by_type.items()},
        },
        "acquisition": acquisition,
        "sources": sources,
        "pipeline_status": {
            "pipeline": {
                "raw_observations": int(raw_total),
                "parsed_events": int(event_total),
                "analysis_outputs": int(episodes_total + hypotheses_total),
                "maritime_episodes": int(episodes_total),
                "investigation_hypotheses": int(hypotheses_total),
            },
            "sensor_activity": {
                "ais_fixes": ais_fixes,
                "radio_bursts": radio_bursts,
                "radio_events": radio_events,
                "satellite_observations": satellite_observations,
                "active_source_names": len(raw_by_source),
            },
            "freshness": {
                "raw_observation": _dt(newest_raw),
                "parsed_event": _dt(newest_event),
                "analysis_output": _dt(newest_analysis),
            },
            "scope": "operator_hot_path",
        },
        "note": (
            "SourceObservation stores the canonical immutable envelope, hash/reference and provenance. "
            "Payload bytes are not stored inline; normalized text and parser output are visible in /events."
        ),
    }
    return _fast_cache_put("overview", hours, payload)


@router.get("/observations")
def operator_source_observations(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    hours: int = Query(24, ge=1, le=720),
    source: str | None = None,
    observation_type: str | None = None,
    service: str | None = None,
    lane: str | None = None,
) -> dict[str, Any]:
    _require_gateway(request)
    with session_scope() as db:
        query = db.query(SourceObservationDB).filter(SourceObservationDB.received_at >= _since(hours))
        if source:
            query = query.filter(SourceObservationDB.source_name == source)
        if observation_type:
            query = query.filter(SourceObservationDB.observation_type == observation_type)
        if service:
            query = query.filter(SourceObservationDB.service == service)
        if lane:
            query = query.filter(SourceObservationDB.lane == lane)
        rows = query.order_by(SourceObservationDB.received_at.desc()).limit(limit).all()
        observations = [_source_observation(row) for row in rows]
    return {"observations": observations, "count": len(observations)}


@router.get("/signals")
def operator_ingested_signals(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    hours: int = Query(24, ge=1, le=720),
    source_channel: str | None = None,
) -> dict[str, Any]:
    _require_gateway(request)
    with session_scope() as db:
        query = db.query(IngestedSignalDB).filter(IngestedSignalDB.received_at >= _since(hours))
        if source_channel:
            query = query.filter(IngestedSignalDB.source_channel == source_channel)
        rows = query.order_by(IngestedSignalDB.received_at.desc()).limit(limit).all()
        signals = [_ingested_signal(row) for row in rows]
    return {"signals": signals, "count": len(signals)}


@router.get("/events")
def operator_parsed_events(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    hours: int = Query(24, ge=1, le=720),
    source: str | None = None,
    event_type: str | None = None,
) -> dict[str, Any]:
    _require_gateway(request)
    with session_scope() as db:
        query = db.query(IntelEventDB).filter(IntelEventDB.received_at >= _since(hours))
        if source:
            query = query.filter(IntelEventDB.source == source)
        if event_type:
            query = query.filter(IntelEventDB.type == event_type)
        rows = query.order_by(IntelEventDB.received_at.desc()).limit(limit).all()
        events = [_intel_event(row) for row in rows]
    return {"events": events, "count": len(events)}


@router.get("/stream")
def operator_ingestion_stream(
    request: Request,
    limit: int = Query(150, ge=1, le=500),
    hours: int = Query(24, ge=1, le=720),
) -> dict[str, Any]:
    _require_gateway(request)
    each = min(limit, 250)
    with session_scope() as db:
        observations = (
            db.query(SourceObservationDB)
            .filter(SourceObservationDB.received_at >= _since(hours))
            .order_by(SourceObservationDB.received_at.desc())
            .limit(each)
            .all()
        )
        events = (
            db.query(IntelEventDB)
            .filter(IntelEventDB.received_at >= _since(hours))
            .order_by(IntelEventDB.received_at.desc())
            .limit(each)
            .all()
        )
        signals = (
            db.query(IngestedSignalDB)
            .filter(IngestedSignalDB.received_at >= _since(hours))
            .order_by(IngestedSignalDB.received_at.desc())
            .limit(each)
            .all()
        )
        items = (
            [_source_observation(row) for row in observations]
            + [_intel_event(row) for row in events]
            + [_ingested_signal(row) for row in signals]
        )

    items.sort(key=lambda item: str(item.get("received_at") or item.get("timestamp_utc") or ""), reverse=True)
    return {"items": items[:limit], "count": min(len(items), limit)}


@router.get("/analysis")
def operator_analysis_outputs(
    request: Request,
    limit: int = Query(80, ge=1, le=250),
    hours: int = Query(24, ge=1, le=720),
) -> dict[str, Any]:
    _require_gateway(request)
    cutoff = _since(hours)
    with session_scope() as db:
        episodes = (
            db.query(MaritimeEpisodeDB)
            .filter(
                MaritimeEpisodeDB.updated_at >= cutoff,
                MaritimeEpisodeDB.episode_family != "unclassified_episode",
            )
            .order_by(MaritimeEpisodeDB.updated_at.desc())
            .limit(limit)
            .all()
        )
        hypotheses = (
            db.query(InvestigationHypothesisDB)
            .filter(InvestigationHypothesisDB.updated_at >= cutoff)
            .order_by(InvestigationHypothesisDB.updated_at.desc())
            .limit(limit)
            .all()
        )
        episode_rows = [
            {
                "kind": "maritime_episode",
                "id": row.episode_id,
                "family": row.episode_family,
                "status": row.status,
                "verification_status": row.verification_status,
                "subjects": len(row.subject_ids or []),
                "observations": len(row.observation_ids or []),
                "independence_groups": len(row.independence_groups or []),
                "start_at": _dt(row.start_at),
                "end_at": _dt(row.end_at),
                "updated_at": _dt(row.updated_at),
            }
            for row in episodes
        ]
        hypothesis_rows = [
            {
                "kind": "investigation_hypothesis",
                "id": row.hypothesis_id,
                "episode_id": row.episode_id,
                "hypothesis_type": row.hypothesis_type,
                "state": row.state,
                "evidence_stage": row.evidence_stage,
                "evidence_links": len(row.evidence_links or []),
                "reason_codes": list(row.reason_codes or []),
                "updated_at": _dt(row.updated_at),
            }
            for row in hypotheses
        ]
    items = episode_rows + hypothesis_rows
    items.sort(key=lambda item: str(item.get("updated_at") or item.get("end_at") or ""), reverse=True)
    return {
        "items": items[:limit],
        "episodes": len(episode_rows),
        "hypotheses": len(hypothesis_rows),
        "count": min(len(items), limit),
    }


from core.intel.measurement_definitions import DERIVED_EVENT_TYPES as _DERIVED_EVENT_TYPES, DERIVED_ANALYSIS_STATES


def _count_pairs(rows: list[tuple[Any, Any]]) -> dict[str, int]:
    return {str(key or "unset"): int(value or 0) for key, value in rows}


def _external_lineage(evidence_id: str) -> str:
    lowered = evidence_id.lower()
    if lowered.startswith("sat:"):
        return "satellite_sensor_lineage"
    if lowered.startswith("radio:") or lowered.startswith("dsc:") or lowered.startswith("navtex:"):
        return "radio_sensor_lineage"
    if lowered.startswith("human:") or lowered.startswith("twitter:") or lowered.startswith("twikit:"):
        return "human_report_lineage"
    if lowered.startswith("ais:"):
        return "ais_sensor_lineage"
    return "external_or_unresolved"


@router.get("/pipeline-map")
def operator_pipeline_map(request: Request) -> dict[str, Any]:
    _require_gateway(request)
    return {
        "chains": pipeline_chains(),
        "semantics": {
            "raw": "Immutable source envelope or sampled source observation.",
            "normalized": "IntelEvent with a stable event schema; normalization does not imply suspicion.",
            "derived_cue": "Rule/model output such as gap, rendezvous or integrity anomaly.",
            "episode": "Time/space-bounded aggregation of related signals for the same subject/family.",
            "hypothesis": "Explicit investigation question with reason and counter-indicator tracking.",
            "corroborated": "Evidence from at least two independent evidence lineages.",
            "review_ready": "Corroborated investigation ready for human review; not an illegality finding.",
            "live": "Currently publication-eligible operational/public signal.",
        },
    }


@router.get("/funnel")
def operator_pipeline_funnel(
    request: Request,
    hours: int = Query(24, ge=1, le=720),
) -> dict[str, Any]:
    _require_gateway(request)
    cached = _fast_cache_get("funnel", hours)
    if cached is not None:
        return cached
    cutoff = _since(hours)
    analysis_state = IntelEventDB.meta["analysis_state"].as_string()
    publication_state = IntelEventDB.meta["publication_status"].as_string()
    anomaly_type = IntelEventDB.meta["anomaly_type"].as_string()

    with session_scope() as db:
        raw_total = int(
            db.query(func.count(SourceObservationDB.observation_id))
            .filter(SourceObservationDB.received_at >= cutoff)
            .scalar()
            or 0
        )
        normalized_total = int(
            db.query(func.count(IntelEventDB.id))
            .filter(IntelEventDB.received_at >= cutoff)
            .scalar()
            or 0
        )
        derived_total_raw = int(
            db.query(func.count(IntelEventDB.id))
            .filter(
                IntelEventDB.received_at >= cutoff,
                or_(
                    IntelEventDB.type.in_(_DERIVED_EVENT_TYPES),
                    analysis_state.in_(DERIVED_ANALYSIS_STATES),
                ),
            )
            .scalar()
            or 0
        )
        legacy_gap_context = int(
            db.query(func.count(IntelEventDB.id))
            .filter(
                IntelEventDB.received_at >= cutoff,
                IntelEventDB.type == "ais_anomaly",
                IntelEventDB.source == "ais",
                IntelEventDB.id.like("aisanom:%"),
                anomaly_type == "gap",
            )
            .scalar()
            or 0
        )
        derived_total = max(0, derived_total_raw - legacy_gap_context)
        episodes_total = int(
            db.query(func.count(MaritimeEpisodeDB.episode_id))
            .filter(
                MaritimeEpisodeDB.updated_at >= cutoff,
                MaritimeEpisodeDB.episode_family != "unclassified_episode",
            )
            .scalar()
            or 0
        )
        unclassified_episodes = int(
            db.query(func.count(MaritimeEpisodeDB.episode_id))
            .filter(
                MaritimeEpisodeDB.updated_at >= cutoff,
                MaritimeEpisodeDB.episode_family == "unclassified_episode",
            )
            .scalar()
            or 0
        )
        corroborated_total = int(
            db.query(func.count(MaritimeEpisodeDB.episode_id))
            .filter(
                MaritimeEpisodeDB.updated_at >= cutoff,
                MaritimeEpisodeDB.episode_family != "unclassified_episode",
                MaritimeEpisodeDB.verification_status == "multi_source_corroborated",
            )
            .scalar()
            or 0
        )
        expired_hypotheses_excluded = int(
            db.query(func.count(InvestigationHypothesisDB.hypothesis_id))
            .filter(
                InvestigationHypothesisDB.updated_at >= cutoff,
                InvestigationHypothesisDB.state.in_(("expired", "rejected")),
            )
            .scalar()
            or 0
        )
        hypotheses = (
            db.query(InvestigationHypothesisDB)
            .filter(
                InvestigationHypothesisDB.updated_at >= cutoff,
                InvestigationHypothesisDB.state.notin_(("expired", "rejected")),
            )
            .all()
        )
        hypothesis_total = len(hypotheses)
        review_ready_total = sum(
            row.state in {"review_ready", "assessed", "published"} for row in hypotheses
        )
        episode_verification = _count_pairs(
            db.query(
                MaritimeEpisodeDB.verification_status,
                func.count(MaritimeEpisodeDB.episode_id),
            )
            .filter(MaritimeEpisodeDB.updated_at >= cutoff)
            .group_by(MaritimeEpisodeDB.verification_status)
            .all()
        )
        episode_families = _count_pairs(
            db.query(
                MaritimeEpisodeDB.episode_family,
                func.count(MaritimeEpisodeDB.episode_id),
            )
            .filter(MaritimeEpisodeDB.updated_at >= cutoff)
            .group_by(MaritimeEpisodeDB.episode_family)
            .all()
        )
        event_analysis = _count_pairs(
            db.query(analysis_state, func.count(IntelEventDB.id))
            .filter(IntelEventDB.received_at >= cutoff)
            .group_by(analysis_state)
            .all()
        )
        event_publication = _count_pairs(
            db.query(publication_state, func.count(IntelEventDB.id))
            .filter(IntelEventDB.received_at >= cutoff)
            .group_by(publication_state)
            .all()
        )
        event_types = _count_pairs(
            db.query(IntelEventDB.type, func.count(IntelEventDB.id))
            .filter(IntelEventDB.received_at >= cutoff)
            .group_by(IntelEventDB.type)
            .order_by(func.count(IntelEventDB.id).desc())
            .limit(40)
            .all()
        )
        raw_types = _count_pairs(
            db.query(
                SourceObservationDB.observation_type,
                func.count(SourceObservationDB.observation_id),
            )
            .filter(SourceObservationDB.received_at >= cutoff)
            .group_by(SourceObservationDB.observation_type)
            .order_by(func.count(SourceObservationDB.observation_id).desc())
            .limit(40)
            .all()
        )

        hypothesis_states = Counter(str(row.state or "unset") for row in hypotheses)
        evidence_stages = Counter(str(row.evidence_stage or "unset") for row in hypotheses)
        reason_codes = Counter(
            str(reason)
            for row in hypotheses
            for reason in (row.reason_codes or [])
            if str(reason)
        )
        counter_indicators = Counter(
            str(reason)
            for row in hypotheses
            for reason in (row.counter_indicators or [])
            if str(reason)
        )

    try:
        from core.api.routes.status import peek_public_status

        cached_public_status = peek_public_status(hours)
        live = (cached_public_status or {}).get("live") or {"total": 0}
        live_count_cached = cached_public_status is not None
    except Exception:
        live = {"total": 0}
        live_count_cached = False

    stages = [
        {"id": "raw", "label": "Raw observations", "count": raw_total},
        {"id": "normalized", "label": "Normalized events", "count": normalized_total},
        {"id": "derived", "label": "Derived cues", "count": derived_total},
        {"id": "episodes", "label": "Episodes", "count": episodes_total},
        {"id": "hypotheses", "label": "Active hypotheses", "count": hypothesis_total},
        {"id": "corroborated", "label": "Corroborated", "count": corroborated_total},
        {"id": "review_ready", "label": "Review ready", "count": review_ready_total},
        {"id": "live", "label": "Public Live", "count": int(live.get("total") or 0)},
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_hours": hours,
        "cache_ttl_seconds": int(_OPERATOR_FAST_CACHE_TTL_S),
        "stages": stages,
        "diagnostics": {
            "raw_observation_types": raw_types,
            "event_types": event_types,
            "event_analysis_states": event_analysis,
            "event_publication_states": event_publication,
            "episode_families": episode_families,
            "episode_verification": episode_verification,
            "unclassified_episodes_excluded": unclassified_episodes,
            "legacy_short_gap_context_excluded": legacy_gap_context,
            "hypothesis_states": dict(hypothesis_states.most_common()),
            "hypothesis_evidence_stages": dict(evidence_stages.most_common()),
            "hypothesis_reason_codes": dict(reason_codes.most_common(30)),
            "hypothesis_counter_indicators": dict(counter_indicators.most_common(30)),
            "expired_or_rejected_hypotheses_excluded": expired_hypotheses_excluded,
        },
        "interpretation": (
            "Stage counts are records present at each analytical layer in the selected window, "
            "not a claim that every raw observation converts one-to-one into the next stage. "
            "The 24h hypothesis stage excludes expired/rejected housekeeping transitions."
        ),
        "live_count_cached": live_count_cached,
    }
    return _fast_cache_put("funnel", hours, payload)




@router.get("/satellite-queue")
def operator_satellite_queue(
    request: Request,
    hours: int = Query(168, ge=1, le=720),
    temporal_hours: float = Query(12.0, ge=0.5, le=48.0),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    _require_gateway(request)
    from core.intel.correlation_stabilization import satellite_coverage_queue

    return satellite_coverage_queue(
        hours=hours, temporal_hours=temporal_hours, limit=limit,
    )


@router.get("/humanitarian-ais-correlation")
def operator_humanitarian_ais_correlation(
    request: Request,
    hours: int = Query(168, ge=1, le=720),
    radius_nm: float = Query(35.0, ge=1.0, le=150.0),
    window_hours: float = Query(2.0, ge=0.25, le=12.0),
    limit: int = Query(50, ge=1, le=250),
) -> dict[str, Any]:
    _require_gateway(request)
    from core.intel.correlation_stabilization import humanitarian_ais_correlation

    return humanitarian_ais_correlation(
        hours=hours, radius_nm=radius_nm, window_hours=window_hours, limit=limit,
    )


@router.get("/stabilization")
def operator_stabilization_status(
    request: Request,
    hours: int = Query(24, ge=1, le=720),
) -> dict[str, Any]:
    """Small set of SLOs for the evidence pipeline stabilization cycle."""
    _require_gateway(request)
    funnel = operator_pipeline_funnel(request, hours=hours)
    stage_counts = {row["id"]: int(row["count"]) for row in funnel["stages"]}
    cutoff = _since(hours)
    with session_scope() as db:
        recent_episodes = (
            db.query(MaritimeEpisodeDB)
            .filter(
                MaritimeEpisodeDB.updated_at >= cutoff,
                MaritimeEpisodeDB.episode_family != "unclassified_episode",
            )
            .limit(5000)
            .all()
        )
        invalid_corroboration = sum(
            row.verification_status == "multi_source_corroborated"
            and len(set(row.independence_groups or ())) < 2
            for row in recent_episodes
        )
        baseline_count = int(
            db.query(func.count(VesselBehaviouralBaselineDB.baseline_id))
            .filter(VesselBehaviouralBaselineDB.window_end >= cutoff)
            .scalar()
            or 0
        )
        newest_raw = db.query(func.max(SourceObservationDB.received_at)).scalar()
        newest_event = db.query(func.max(IntelEventDB.received_at)).scalar()

    from core.intel.correlation_stabilization import satellite_coverage_queue
    from core.radio.decoder_runtime import radio_decoder_status

    sat_queue = satellite_coverage_queue(hours=min(hours, 168), limit=1)
    radio = radio_decoder_status()
    derived = stage_counts.get("derived", 0)
    episodes = stage_counts.get("episodes", 0)
    corroborated = stage_counts.get("corroborated", 0)
    review_ready = stage_counts.get("review_ready", 0)

    def rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    decoded = int(radio.get("decoded") or 0)
    accepted = int(radio.get("dsc_accepted") or 0)
    frames = int(radio.get("frames") or 0)
    decode_ratio = decoded / frames if frames else 0.0
    from core.radio.bridge import radio_acquisition_status
    radio_acquisition = radio_acquisition_status()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_hours": hours,
        "freshness": {
            "raw_observation": _dt(newest_raw),
            "normalized_event": _dt(newest_event),
        },
        "rates": {
            "derived_to_episode": rate(episodes, derived),
            "episode_to_multi_lineage": rate(corroborated, episodes),
            "multi_lineage_to_review_ready": rate(review_ready, corroborated),
        },
        "counts": {
            "derived": derived,
            "episodes": episodes,
            "corroborated": corroborated,
            "review_ready": review_ready,
            "recent_behavioural_baselines": baseline_count,
            "satellite_coverage_candidates": int(sat_queue.get("total_candidates") or 0),
        },
        "invariants": {
            "multi_source_with_lt2_lineages": int(invalid_corroboration),
            "ok": invalid_corroboration == 0,
        },
        "radio": {
            **radio,
            "ready_for_scale": (
                accepted >= 3 and decode_ratio > 0.0
                and int(radio.get("recent_dropped") or 0) == 0
                and radio_acquisition["state"] == "live"
            ),
            "scale_gate": "Require >=3 accepted DSC observations, full receiver coverage and no recent packet loss.",
            "pipeline": radio_acquisition["pipeline"],
        },
        "targets": {
            "episode_to_multi_lineage": "increase without inflating detector count",
            "multi_lineage_to_review_ready": "non-zero after independent evidence closure",
            "invariant_violations": 0,
            "radio_ready_for_scale": True,
        },
    }


@router.get("/overall")
def operator_overall_corpus(request: Request) -> dict[str, Any]:
    """Cached all-time corpus inventory for operator capacity/lineage inspection."""
    _require_gateway(request)
    return _overall_payload()


def _overall_payload() -> dict[str, Any]:
    global _overall_cache
    now_mono = time.monotonic()
    with _overall_cache_lock:
        if _overall_cache is not None and now_mono - _overall_cache[0] < _OVERALL_CACHE_TTL_S:
            return _overall_cache[1]

    analysis_state = IntelEventDB.meta["analysis_state"].as_string()
    anomaly_type = IntelEventDB.meta["anomaly_type"].as_string()

    with session_scope() as db:
        raw_total = int(db.query(func.count(SourceObservationDB.observation_id)).scalar() or 0)
        normalized_total = int(db.query(func.count(IntelEventDB.id)).scalar() or 0)
        derived_total_raw = int(
            db.query(func.count(IntelEventDB.id))
            .filter(
                or_(
                    IntelEventDB.type.in_(_DERIVED_EVENT_TYPES),
                    analysis_state.in_(DERIVED_ANALYSIS_STATES),
                )
            )
            .scalar()
            or 0
        )
        legacy_gap_context = int(
            db.query(func.count(IntelEventDB.id))
            .filter(
                IntelEventDB.type == "ais_anomaly",
                IntelEventDB.source == "ais",
                IntelEventDB.id.like("aisanom:%"),
                anomaly_type == "gap",
            )
            .scalar()
            or 0
        )
        derived_total = max(0, derived_total_raw - legacy_gap_context)

        episodes_total = int(
            db.query(func.count(MaritimeEpisodeDB.episode_id))
            .filter(MaritimeEpisodeDB.episode_family != "unclassified_episode")
            .scalar()
            or 0
        )
        unclassified_episodes = int(
            db.query(func.count(MaritimeEpisodeDB.episode_id))
            .filter(MaritimeEpisodeDB.episode_family == "unclassified_episode")
            .scalar()
            or 0
        )
        corroborated_total = int(
            db.query(func.count(MaritimeEpisodeDB.episode_id))
            .filter(
                MaritimeEpisodeDB.episode_family != "unclassified_episode",
                MaritimeEpisodeDB.verification_status == "multi_source_corroborated",
            )
            .scalar()
            or 0
        )
        hypotheses = db.query(InvestigationHypothesisDB).all()
        hypothesis_total = len(hypotheses)
        review_ready_total = sum(
            row.state in {"review_ready", "assessed", "published"} for row in hypotheses
        )

        ais_fix_count, ais_fix_estimated = _fast_table_count(db, VesselTrackDB)
        sensor_activity = {
            "ais_fixes": ais_fix_count,
            "ais_fixes_estimated": ais_fix_estimated,
            "radio_bursts": int(db.query(func.count(RadioBurstDB.burst_id)).scalar() or 0),
            "radio_events": int(db.query(func.count(RadioEventDB.event_id)).scalar() or 0),
            "satellite_observations": int(
                db.query(func.count(SatelliteObservationDB.observation_id)).scalar() or 0
            ),
            "source_names": int(
                db.query(func.count(func.distinct(SourceObservationDB.source_name))).scalar() or 0
            ),
        }

        by_source = _count_pairs(
            db.query(SourceObservationDB.source_name, func.count(SourceObservationDB.observation_id))
            .group_by(SourceObservationDB.source_name)
            .order_by(func.count(SourceObservationDB.observation_id).desc())
            .limit(40)
            .all()
        )
        raw_types = _count_pairs(
            db.query(
                SourceObservationDB.observation_type,
                func.count(SourceObservationDB.observation_id),
            )
            .group_by(SourceObservationDB.observation_type)
            .order_by(func.count(SourceObservationDB.observation_id).desc())
            .limit(40)
            .all()
        )
        event_sources = _count_pairs(
            db.query(IntelEventDB.source, func.count(IntelEventDB.id))
            .group_by(IntelEventDB.source)
            .order_by(func.count(IntelEventDB.id).desc())
            .limit(40)
            .all()
        )
        event_types = _count_pairs(
            db.query(IntelEventDB.type, func.count(IntelEventDB.id))
            .group_by(IntelEventDB.type)
            .order_by(func.count(IntelEventDB.id).desc())
            .limit(40)
            .all()
        )
        episode_families = _count_pairs(
            db.query(MaritimeEpisodeDB.episode_family, func.count(MaritimeEpisodeDB.episode_id))
            .group_by(MaritimeEpisodeDB.episode_family)
            .order_by(func.count(MaritimeEpisodeDB.episode_id).desc())
            .limit(40)
            .all()
        )
        episode_verification = _count_pairs(
            db.query(
                MaritimeEpisodeDB.verification_status,
                func.count(MaritimeEpisodeDB.episode_id),
            )
            .group_by(MaritimeEpisodeDB.verification_status)
            .order_by(func.count(MaritimeEpisodeDB.episode_id).desc())
            .all()
        )
        hypothesis_types = dict(
            Counter(str(row.hypothesis_type or "unset") for row in hypotheses).most_common(40)
        )
        hypothesis_states = dict(
            Counter(str(row.state or "unset") for row in hypotheses).most_common()
        )
        hypothesis_evidence_stages = dict(
            Counter(str(row.evidence_stage or "unset") for row in hypotheses).most_common()
        )

        first_last = {
            "raw_first": _dt(db.query(func.min(SourceObservationDB.received_at)).scalar()),
            "raw_latest": _dt(db.query(func.max(SourceObservationDB.received_at)).scalar()),
            "event_first": _dt(db.query(func.min(IntelEventDB.received_at)).scalar()),
            "event_latest": _dt(db.query(func.max(IntelEventDB.received_at)).scalar()),
            "episode_first": _dt(db.query(func.min(MaritimeEpisodeDB.created_at)).scalar()),
            "episode_latest": _dt(db.query(func.max(MaritimeEpisodeDB.updated_at)).scalar()),
            "hypothesis_first": _dt(
                db.query(func.min(InvestigationHypothesisDB.created_at)).scalar()
            ),
            "hypothesis_latest": _dt(
                db.query(func.max(InvestigationHypothesisDB.updated_at)).scalar()
            ),
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "all_time",
        "cache_ttl_seconds": int(_OVERALL_CACHE_TTL_S),
        "stages": [
            {"id": "raw", "label": "Raw observations", "count": raw_total},
            {"id": "normalized", "label": "Normalized events", "count": normalized_total},
            {"id": "derived", "label": "Derived cues", "count": derived_total},
            {"id": "episodes", "label": "Recognized episodes", "count": episodes_total},
            {"id": "hypotheses", "label": "Hypotheses", "count": hypothesis_total},
            {"id": "corroborated", "label": "Corroborated", "count": corroborated_total},
            {"id": "review_ready", "label": "Review ready", "count": review_ready_total},
        ],
        "sensor_activity": sensor_activity,
        "first_last": first_last,
        "breakdowns": {
            "raw_by_source": by_source,
            "raw_observation_types": raw_types,
            "normalized_by_source": event_sources,
            "normalized_event_types": event_types,
            "episode_families": episode_families,
            "episode_verification": episode_verification,
            "hypothesis_types": hypothesis_types,
            "hypothesis_states": hypothesis_states,
            "hypothesis_evidence_stages": hypothesis_evidence_stages,
        },
        "excluded_context": {
            "legacy_short_gap_telemetry": legacy_gap_context,
            "unclassified_episodes": unclassified_episodes,
        },
        "interpretation": (
            "All-time stored corpus. Counts describe records retained at each layer, "
            "not one-to-one conversions and not findings of illegality."
        ),
    }
    with _overall_cache_lock:
        _overall_cache = (time.monotonic(), payload)
    return payload


@router.get("/cases")
def operator_case_evidence_chains(
    request: Request,
    limit: int = Query(30, ge=1, le=100),
    hours: int = Query(168, ge=1, le=720),
) -> dict[str, Any]:
    _require_gateway(request)
    cutoff = _since(hours)
    from core.intel.fusion import lineage_for_event

    with session_scope() as db:
        hypotheses = (
            db.query(InvestigationHypothesisDB)
            .filter(InvestigationHypothesisDB.updated_at >= cutoff)
            .order_by(InvestigationHypothesisDB.updated_at.desc())
            .limit(limit)
            .all()
        )
        episode_ids = [row.episode_id for row in hypotheses if row.episode_id]
        episodes = {
            row.episode_id: row
            for row in (
                db.query(MaritimeEpisodeDB)
                .filter(MaritimeEpisodeDB.episode_id.in_(episode_ids))
                .all()
                if episode_ids else []
            )
        }
        durable_ids = sorted({
            str(evidence_id)
            for hypothesis in hypotheses
            for evidence_id in (hypothesis.evidence_links or [])
            if str(evidence_id)
            and not str(evidence_id).startswith(("sat:", "radio:", "dsc:", "navtex:", "ais:"))
        })
        events = {
            row.id: row
            for row in (
                db.query(IntelEventDB).filter(IntelEventDB.id.in_(durable_ids)).all()
                if durable_ids else []
            )
        }

        cases: list[dict[str, Any]] = []
        for hypothesis in hypotheses:
            episode = episodes.get(hypothesis.episode_id)
            evidence: list[dict[str, Any]] = []
            for evidence_id in hypothesis.evidence_links or []:
                eid = str(evidence_id)
                event = events.get(eid)
                if event is not None:
                    metadata = dict(event.meta or {})
                    try:
                        lineage = lineage_for_event(event).independence_group
                    except Exception:
                        lineage = "unknown"
                    evidence.append({
                        "id": event.id,
                        "kind": "intel_event",
                        "source": event.source,
                        "type": event.type,
                        "anomaly_type": metadata.get("anomaly_type"),
                        "title": event.title,
                        "timestamp_utc": event.timestamp_utc,
                        "lat": event.lat,
                        "lon": event.lon,
                        "lineage": lineage,
                        "analysis_state": metadata.get("analysis_state"),
                        "verification_status": metadata.get("verification_status"),
                        "publication_status": metadata.get("publication_status"),
                    })
                else:
                    evidence.append({
                        "id": eid,
                        "kind": "cross_modal_reference",
                        "lineage": _external_lineage(eid),
                    })

            verification = (
                str(episode.verification_status or "single_source_observed")
                if episode is not None else "unresolved"
            )
            independence_groups = list(episode.independence_groups or []) if episode is not None else []
            behaviour = dict(episode.behaviour_context or {}) if episode is not None else {}
            alternatives = list(episode.alternative_explanations or []) if episode is not None else []
            semantics = hypothesis_semantics(str(hypothesis.hypothesis_type or ""))

            blockers: list[str] = []
            if verification != "multi_source_corroborated":
                blockers.append("NO_INDEPENDENT_CORROBORATION")
            if behaviour.get("status") == "insufficient_history":
                blockers.append("INSUFFICIENT_BEHAVIOURAL_HISTORY")
            blockers.extend(str(v) for v in (hypothesis.counter_indicators or []) if str(v))
            if hypothesis.state not in {"review_ready", "assessed", "published"}:
                blockers.append("NOT_REVIEW_READY")

            cases.append({
                "case_id": hypothesis.hypothesis_id,
                "hypothesis_type": hypothesis.hypothesis_type,
                "label": semantics["label"],
                "state": hypothesis.state,
                "evidence_stage": hypothesis.evidence_stage,
                "episode_id": hypothesis.episode_id,
                "episode_family": episode.episode_family if episode is not None else None,
                "verification_status": verification,
                "independence_groups": independence_groups,
                "reason_codes": list(hypothesis.reason_codes or []),
                "counter_indicators": list(hypothesis.counter_indicators or []),
                "alternative_explanations": alternatives,
                "behaviour_context": behaviour,
                "evidence": evidence,
                "evidence_count": len(evidence),
                "blockers": list(dict.fromkeys(blockers)),
                "possible_meaning": semantics["possible_meaning"],
                "illegal_activity_status": semantics["illegal_activity_status"],
                "updated_at": _dt(hypothesis.updated_at),
            })

    return {
        "cases": cases,
        "count": len(cases),
        "note": (
            "These are investigation hypotheses, not findings of illegality. "
            "Evidence lineage and blockers are exposed so operators can see why a case has or has not advanced."
        ),
    }


@router.get("/measurements")
def operator_measurement_contract(
    request: Request,
    hours: int = Query(24, ge=1, le=168),
) -> dict[str, Any]:
    """Canonical temporal comparison. Windows use one as-of cutoff and explicit clock semantics.

    Created counts measure records first created. Updated counts measure rows whose latest
    update fell within the window, not transitions or new evidence. Source ingestion is
    measured at receipt, while AIS track coverage is measured at source time.
    """
    _require_gateway(request)
    cached = _fast_cache_get("measurements", hours)
    if cached is not None:
        return cached
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(hours=hours)
    with session_scope() as db:
        def count(model, field, *conditions):
            return int(db.query(func.count()).select_from(model).filter(field >= cutoff, field <= now, *conditions).scalar() or 0)

        active = InvestigationHypothesisDB.state.notin_(("expired", "rejected"))
        classified = MaritimeEpisodeDB.episode_family != "unclassified_episode"
        new_hypotheses = count(InvestigationHypothesisDB, InvestigationHypothesisDB.created_at, active)
        updated_hypotheses = count(InvestigationHypothesisDB, InvestigationHypothesisDB.updated_at, active)
        new_episodes = count(MaritimeEpisodeDB, MaritimeEpisodeDB.created_at, classified)
        updated_episodes = count(MaritimeEpisodeDB, MaritimeEpisodeDB.updated_at, classified)
        current_open_hypotheses = int(db.query(func.count()).select_from(InvestigationHypothesisDB).filter(active).scalar() or 0)
        excluded_hypotheses = count(
            InvestigationHypothesisDB, InvestigationHypothesisDB.updated_at,
            InvestigationHypothesisDB.state.in_(("expired", "rejected")),
        )
        observations_received = count(SourceObservationDB, SourceObservationDB.received_at)
        events_received = count(IntelEventDB, IntelEventDB.received_at)
        events_created = count(IntelEventDB, IntelEventDB.created_at)
        ais_observed = count(VesselTrackDB, VesselTrackDB.ts)
        ais_received = count(VesselTrackDB, VesselTrackDB.received_at)
        corroborated_updated = count(
            MaritimeEpisodeDB, MaritimeEpisodeDB.updated_at, classified,
            MaritimeEpisodeDB.verification_status == "multi_source_corroborated",
        )
        review_ready_updated = count(
            InvestigationHypothesisDB, InvestigationHypothesisDB.updated_at,
            InvestigationHypothesisDB.state.in_(("review_ready", "assessed", "published")),
        )
        raw_sources = dict(
            db.query(SourceObservationDB.source_name, func.count())
            .filter(SourceObservationDB.received_at >= cutoff, SourceObservationDB.received_at <= now)
            .group_by(SourceObservationDB.source_name).order_by(func.count().desc()).limit(40).all()
        )
    payload = {
        "contract_version": 1, "scope": "rolling", "window_hours": hours,
        "as_of": now.replace(tzinfo=timezone.utc).isoformat(),
        "window_start": cutoff.replace(tzinfo=timezone.utc).isoformat(),
        "counts": {
            "observations_received": observations_received,
            "events_received": events_received,
            "events_created": events_created,
            "investigations_created": new_hypotheses,
            "investigations_updated": updated_hypotheses,
            "investigations_open_now": current_open_hypotheses,
            "investigations_rejected_or_expired_updated": excluded_hypotheses,
            "episodes_created": new_episodes,
            "episodes_updated": updated_episodes,
            "corroborated_episodes_updated": corroborated_updated,
            "investigations_review_ready_updated": review_ready_updated,
            "ais_positions_observed": ais_observed,
            "ais_positions_received": ais_received,
        },
        "sources": {str(key): int(value) for key, value in raw_sources.items()},
        "definitions": {
            "observations_received": {"clock":"received_at","meaning":"Deduplicated raw source observation rows received within the window."},
            "events_received": {"clock":"received_at","meaning":"Normalized Intel records received in the window. Not all raw inputs produce an event."},
            "events_created": {"clock":"created_at","meaning":"Intel records first created within the window."},
            "investigations_created": {"clock":"created_at","meaning":"Hypotheses created within the window and not currently expired/rejected."},
            "investigations_updated": {"clock":"updated_at","meaning":"Non-expired/rejected hypotheses whose latest saved update falls in the window; may include reprocessing with no new evidence."},
            "investigations_open_now": {"clock":"current state","meaning":"Current non-expired/non-rejected hypotheses (including assessed or published). Not a windowed count."},
            "investigations_rejected_or_expired_updated": {"clock":"updated_at","meaning":"Rejected or expired hypotheses whose last update falls in the window, omitted from the main funnel."},
            "episodes_created": {"clock":"created_at","meaning":"Classified episodes first created within the window."},
            "episodes_updated": {"clock":"updated_at","meaning":"Classified episodes with latest update in the window; not necessarily newly recognized."},
            "corroborated_episodes_updated": {"clock":"updated_at","meaning":"Episodes currently tagged multi-source corroborated and updated in the window, not transitions into that state."},
            "investigations_review_ready_updated": {"clock":"updated_at","meaning":"Hypotheses currently in review-ready, assessed or published state and updated in the window; not new transitions."},
            "ais_positions_observed": {"clock":"ts","meaning":"Stored AIS track positions whose source observation time falls within the window."},
            "ais_positions_received": {"clock":"received_at","meaning":"AIS track rows actually received by SeaCommons in the window."},
        },
        "limitations": [
            "Created/updated are current-row snapshots, not event-sourced transition counts.",
            "Current open is a stock, so it does not become a seven-day total.",
            "All values are retained rows, not an immutable lifetime ingestion ledger.",
            "Raw, normalized, derived and episodes are overlapping populations; do not sum or divide as conversion rates.",
        ],
    }
    return _fast_cache_put("measurements", hours, payload)


@router.get("/scheduled-tasks")
def futures_scheduled_tasks(request: Request) -> dict[str, Any]:
    """Read-only ChatGPT task snapshot, private to authenticated Futures users.

    The export is provisioned outside the Git repository, contains no credentials
    or prompts, and is explicitly a snapshot rather than a live scheduler API.
    """
    _require_gateway(request)
    import json
    import os
    from pathlib import Path

    file_path = Path(os.environ.get(
        "SEACOMMONS_FUTURES_TASK_SNAPSHOT",
        "/home/ubuntu/seacommons/data/futures-scheduled-tasks.json",
    ))
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        tasks = raw.get("tasks", [])
        if not isinstance(tasks, list):
            raise ValueError("Invalid scheduler task shape")
        allowed = {"title", "enabled", "cadence", "last_run", "timezone", "status"}
        clean = [{k: row[k] for k in allowed if k in row} for row in tasks if isinstance(row, dict)]
        return {"source": "ChatGPT Tasks snapshot", "live_sync": False,
                "synced_at": raw.get("synced_at"), "tasks": clean}
    except (FileNotFoundError, PermissionError, ValueError, json.JSONDecodeError):
        return {"source": "ChatGPT Tasks", "live_sync": False,
                "synced_at": None, "tasks": [], "status": "not_connected"}


def _overall_metrics_aggregate() -> dict[str, Any]:
    """Bounded, independently recoverable retained-record counters for Futures Overall.

    Each SQL query has its own savepoint and PostgreSQL statement deadline; one
    costly metric must never blank every other metric. Missing values are null.
    Estimated planner totals are explicitly marked, never presented as exact.
    """
    cached = _fast_cache_get("overall_metrics", 0)
    if cached is not None:
        return cached

    from core.intel.measurement_definitions import DERIVED_EVENT_TYPES, DERIVED_ANALYSIS_STATES

    analysis_state = IntelEventDB.meta["analysis_state"].as_string()
    anomaly_type = IntelEventDB.meta["anomaly_type"].as_string()
    unavailable = []
    estimated_fields = []

    with session_scope() as db:
        pg = db.get_bind().dialect.name == "postgresql"

        def n(name, model, *conditions):
            try:
                with db.begin_nested():
                    if pg:
                        db.execute(text("SET LOCAL statement_timeout = '1600ms'"))
                    result = db.query(func.count()).select_from(model).filter(*conditions).scalar()
                    return int(result or 0)
            except Exception:
                unavailable.append(name)
                return None

        def total(name, model):
            if pg:
                try:
                    with db.begin_nested():
                        db.execute(text("SET LOCAL statement_timeout = '1600ms'"))
                        estimate, _ = _fast_table_count(db, model)
                        estimated_fields.append(name)
                        return estimate
                except Exception:
                    unavailable.append(name)
                    return None
            return n(name, model)

        raw = total("raw_observations", SourceObservationDB)
        parsed = total("parsed_events", IntelEventDB)
        derived = n("derived_cues", IntelEventDB, or_(
            IntelEventDB.type.in_(DERIVED_EVENT_TYPES),
            analysis_state.in_(DERIVED_ANALYSIS_STATES),
        ))
        legacy_gap = n("legacy_gap", IntelEventDB,
                       IntelEventDB.type == "ais_anomaly", IntelEventDB.source == "ais",
                       IntelEventDB.id.like("aisanom:%"), anomaly_type == "gap")
        derived_count = max(0, derived - legacy_gap) if derived is not None and legacy_gap is not None else None
        if derived_count is None:
            unavailable.append("derived_cues")
        classified = MaritimeEpisodeDB.episode_family != "unclassified_episode"
        episodes = n("maritime_episodes", MaritimeEpisodeDB, classified)
        hypotheses = n("investigation_hypotheses", InvestigationHypothesisDB)
        corroborated = n("corroborated_episodes", MaritimeEpisodeDB, classified,
                         MaritimeEpisodeDB.verification_status == "multi_source_corroborated")
        ready = n("review_ready", InvestigationHypothesisDB,
                  InvestigationHypothesisDB.state.in_(("review_ready","assessed","published")))
        ais = total("ais_fixes", VesselTrackDB)
        radio_bursts = n("radio_bursts", RadioBurstDB)
        radio_events = n("radio_events", RadioEventDB)
        satellite = n("satellite_observations", SatelliteObservationDB)
        # Number of distinct sources, not the number of observations.
        try:
            with db.begin_nested():
                if pg:
                    db.execute(text("SET LOCAL statement_timeout = '1600ms'"))
                source_names = int(db.query(func.count(func.distinct(SourceObservationDB.source_name))).scalar() or 0)
        except Exception:
            unavailable.append("source_names")
            source_names = None
    payload = {
        "scope": "all_time", "generated_at": datetime.now(timezone.utc).isoformat(),
        "stages": [
            {"id":"raw","count":raw},{"id":"normalized","count":parsed},
            {"id":"derived","count":derived_count},{"id":"episodes","count":episodes},
            {"id":"hypotheses","count":hypotheses},{"id":"corroborated","count":corroborated},
            {"id":"review_ready","count":ready},
        ],
        "sensor_activity": {
            "ais_fixes":ais,"ais_fixes_estimated": "ais_fixes" in estimated_fields,
            "radio_bursts":radio_bursts,"radio_events":radio_events,
            "satellite_observations":satellite,"source_names":source_names,
        },
        "estimated_fields": estimated_fields, "unavailable_fields": sorted(set(unavailable)),
        "retention_semantics": "Currently retained records, not immutable lifetime intake.",
    }
    # Do not retain partial results for longer than the fast aggregation TTL.
    return _fast_cache_put("overall_metrics", 0, payload)


# The public endpoint uses the same canonical calculation as the protected
# operator endpoint. Never copy a gateway secret or a simulated Request.
_PUBLIC_OVERALL_METRIC_LOCK = threading.Lock()


def public_futures_overall_metrics() -> dict[str, Any]:
    """Anonymous, strictly aggregate-only retained Overall with bounded refresh."""
    with _PUBLIC_OVERALL_METRIC_LOCK:
        computed = _overall_metrics_aggregate()
    # Make the response schema an explicit projection; no raw/case/source records.
    stage_keys = ("raw", "normalized", "derived", "episodes", "hypotheses", "corroborated", "review_ready")
    sensor_keys = ("ais_fixes", "radio_bursts", "radio_events", "satellite_observations", "source_names")
    stages = {row["id"]: row.get("count") for row in computed.get("stages", []) if isinstance(row, dict)}
    sensors = computed.get("sensor_activity", {})
    if not isinstance(sensors, dict):
        sensors = {}
    return {
        "scope": "all_time",
        "access": "public_aggregate",
        "source": "canonical_retained_inventory",
        "generated_at": computed["generated_at"],
        "retention_semantics": "Currently retained records, not immutable lifetime intake or verified incidents.",
        "stages": [{"id": key, "count": stages.get(key)} for key in stage_keys],
        "sensor_activity": {key: sensors.get(key) for key in sensor_keys},
        "estimated_fields": [key for key in computed.get("estimated_fields", []) if key in ("raw_observations", "parsed_events", "ais_fixes")],
        "unavailable_fields": [key for key in computed.get("unavailable_fields", []) if key in (*stage_keys, *sensor_keys, "legacy_gap")],
    }


@router.get("/overall-metrics")
def operator_overall_metrics(request: Request) -> dict[str, Any]:
    """Private operator alias: preserve gateway authentication and shape."""
    _require_gateway(request)
    return _overall_metrics_aggregate()
