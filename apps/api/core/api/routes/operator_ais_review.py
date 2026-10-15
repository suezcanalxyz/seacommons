# SPDX-License-Identifier: AGPL-3.0-or-later
"""Authenticated, append-only human AIS case reviews for offline evaluation.

A review is a research annotation, never an AIS observation, corroborating
source, public incident determination or online training instruction.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from core.api.ratelimit import rate_limit
from core.db.models import AISCaseReviewDB
from core.db.session import session_scope
from core.live.feed import public_signal_collection
from core.security import require_futures_identity

router = APIRouter(prefix="/api/v1/operator/ais-reviews", tags=["operator-ais-reviews"])

VERDICTS = frozenset({"supported", "false_positive", "inconclusive"})
POSITION_CHECKS = frozenset({"consistent", "inconsistent", "unavailable"})


class ReviewInput(BaseModel):
    case_id: str = Field(min_length=5, max_length=128)
    verdict: str
    position_check: str
    explanation: str = Field(min_length=20, max_length=2000)
    external_visual_reference_checked: bool = False

    @field_validator("verdict")
    @classmethod
    def valid_verdict(cls, value: str) -> str:
        if value not in VERDICTS:
            raise ValueError("Unsupported case verdict")
        return value

    @field_validator("position_check")
    @classmethod
    def valid_position_check(cls, value: str) -> str:
        if value not in POSITION_CHECKS:
            raise ValueError("Unsupported position comparison")
        return value


def _reviewer(request: Request) -> str:
    # Do not conflate Futures' read-only partner login with write permission.
    principal = require_futures_identity(request)
    email = str(principal.claims.get("email") or "").strip().lower()
    allowed = {
        value.strip().lower()
        for value in os.getenv("SEACOMMONS_AIS_REVIEWER_EMAILS", "").split(",")
        if value.strip()
    }
    if not allowed:
        raise HTTPException(status_code=503, detail="AIS reviewer access is not configured")
    if not email or email not in allowed or principal.claims.get("email_verified") is False:
        raise HTTPException(status_code=403, detail="AIS review requires an approved reviewer")
    return principal.subject


def _case_snapshot(case_id: str) -> dict:
    # Do not trust client-supplied vessel IDs, coordinates, case states or AIS
    # snapshots. The live projection is the canonical eligible source.
    collection = public_signal_collection(limit=500, days=7, mode="maritime")
    feature = next(
        (item for item in collection.get("features", [])
         if str(item.get("id") or (item.get("properties") or {}).get("id")) == case_id),
        None,
    )
    if feature is None:
        raise HTTPException(status_code=409, detail="Case is no longer in the current Live review window")
    props = feature.get("properties") or {}
    mmsi = str(props.get("linked_mmsi") or props.get("mmsi") or "").strip()
    imo = str(props.get("imo") or "").strip()
    if not (len(mmsi) == 9 and mmsi.isdigit()) and not (len(imo) == 7 and imo.isdigit()):
        raise HTTPException(status_code=422, detail="Case lacks a reliable vessel identifier")
    geometry = feature.get("geometry") or {}
    if geometry.get("type") != "Point":
        raise HTTPException(status_code=422, detail="Case has no reviewable point")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) != 2:
        raise HTTPException(status_code=422, detail="Case coordinates unavailable")
    # Snapshot canonical AIS information at review time. We cannot capture
    # the external provider's position through the embed or claim it as an
    # independent sensor reading.
    last_fix = None
    if len(mmsi) == 9 and mmsi.isdigit():
        from core.vessels.registry import registry
        matched = registry.get_last_known_geojson({mmsi})
        vessel = next((
            item for item in matched.get("features", [])
            if str((item.get("properties") or {}).get("mmsi") or "") == mmsi
        ), None)
        if vessel:
            fields = vessel.get("properties") or {}
            last_fix = {
                "coordinates": (vessel.get("geometry") or {}).get("coordinates"),
                "observed_at": fields.get("last_seen"),
                "course": fields.get("course"),
                "speed": fields.get("speed"),
                "lineage": "SeaCommons AIS registry",
            }
    return {
        "case_id": case_id,
        "mmsi": mmsi,
        "imo": imo,
        "sea_commons_last_ais": last_fix,
        "review_contract_version": "ais-human-review-v1",
        "title": str(props.get("title") or "")[:255],
        "case_observed_at": props.get("timestamp_utc"),
        "event_position": coordinates,
        "anomaly_type": props.get("anomaly_type"),
        "verification_status": props.get("verification_status"),
        "resolution_state": props.get("resolution_state"),
        "source": props.get("source"),
        "episode_family": props.get("episode_family"),
    }


def _serialize(row: AISCaseReviewDB) -> dict:
    return {
        "review_id": row.review_id,
        "case_id": row.case_id,
        "verdict": row.verdict,
        "position_check": row.position_check,
        "explanation": row.explanation,
        "external_visual_reference_checked": row.external_visual_reference_checked,
        "created_at": row.created_at.replace(tzinfo=timezone.utc).isoformat()
        if row.created_at.tzinfo is None else row.created_at.isoformat(),
        "case_snapshot": dict(row.case_snapshot or {}),
        "review_stage": "human_annotation_not_training",
    }


@router.get("/lookup")
def vessel_lookup(
    request: Request,
    imo: str = Query(default="", max_length=7),
    mmsi: str = Query(default="", max_length=9),
) -> dict:
    # Viewers may inspect one identity, never the fleet or an unfiltered AIS dump.
    # Authentication is distinct from review-write permissions.
    require_futures_identity(request)
    rate_limit(request, max_per_minute=40, scope="ais-review-lookup")
    if not ((len(imo) == 7 and imo.isdigit()) or (len(mmsi) == 9 and mmsi.isdigit())):
        raise HTTPException(status_code=422, detail="Valid IMO or MMSI required")
    from core.vessels.registry import registry

    result = []
    for item in registry.get_last_known_geojson().get("features", []):
        p = item.get("properties") or {}
        if ((imo and str(p.get("imo") or "") == imo)
                or (mmsi and str(p.get("mmsi") or "") == mmsi)):
            coords = (item.get("geometry") or {}).get("coordinates") or []
            result.append({
                "imo": str(p.get("imo") or ""),
                "mmsi": str(p.get("mmsi") or ""),
                "ship_name": p.get("ship_name"),
                "last_seen": p.get("last_seen"),
                "speed_kn": p.get("speed"),
                "course_deg": p.get("course"),
                "lon": coords[0] if len(coords) == 2 else None,
                "lat": coords[1] if len(coords) == 2 else None,
            })
            if len(result) >= 3:
                break
    return {"vessels": result, "count": len(result), "source": "SeaCommons registry"}


@router.get("")
def list_reviews(request: Request, case_id: str = Query(..., min_length=5, max_length=128),
                 limit: int = Query(30, ge=1, le=100)) -> dict:
    _reviewer(request)
    with session_scope() as db:
        rows = (
            db.query(AISCaseReviewDB)
            .filter(AISCaseReviewDB.case_id == case_id)
            .order_by(AISCaseReviewDB.created_at.desc())
            .limit(limit)
            .all()
        )
        reviews = [_serialize(item) for item in rows]
    return {"case_id": case_id, "reviews": reviews, "count": len(reviews)}


@router.post("", status_code=201)
def submit_review(request: Request, body: ReviewInput) -> dict:
    reviewer_sub = _reviewer(request)
    rate_limit(request, max_per_minute=12, scope="ais-review")
    snapshot = _case_snapshot(body.case_id)
    # The external embed cannot be inspected by us: this flag only documents
    # a reviewer's self-reported manual comparison.
    created = datetime.now(timezone.utc)
    review = AISCaseReviewDB(
        review_id=str(uuid4()),
        case_id=body.case_id,
        mmsi=snapshot["mmsi"],
        imo=snapshot["imo"],
        reviewer_sub=reviewer_sub,
        verdict=body.verdict,
        position_check=body.position_check,
        explanation=body.explanation,
        external_visual_reference_checked=body.external_visual_reference_checked,
        case_snapshot=snapshot,
        created_at=created,
    )
    with session_scope() as db:
        db.add(review)
        db.flush()
        result = _serialize(review)
    return result
