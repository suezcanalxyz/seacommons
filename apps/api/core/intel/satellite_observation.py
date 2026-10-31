"""Provider-neutral satellite evidence contract for Live/Play."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import math
from typing import Any, Literal

logger = logging.getLogger(__name__)

TemporalRelation = Literal["reverse", "nearest", "forward"]


@dataclass(frozen=True)
class SatelliteObservation:
    observation_id: str
    incident_id: str
    provider: str
    mission: str
    product_id: str
    acquisition_time: str
    discovered_at: str
    footprint: dict[str, Any] | None
    bbox: list[float] | None
    sensor_type: str
    temporal_relation: TemporalRelation
    temporal_delta_s: float
    asset_ref: str
    source_url: str
    provenance: dict[str, Any]
    resolution_m: float | None = None
    cloud_cover: float | None = None
    polarisation: list[str] | None = None
    evidence_status: str = "contextual"
    # core.mda.darkship_cue's own vocabulary: "unmatched_candidate" for a SAR
    # detection inside a reachable-area calculation that hasn't been matched
    # to a vessel -- a candidate, never a confirmed identity. None means the
    # association question doesn't apply to this observation.
    association_status: str | None = None
    # Non-null only when this observation is explicitly associated with the
    # canonical MaritimeEpisode rather than merely sharing case context.
    episode_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _merged_provenance(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    # Provider lineage is untrusted JSON. Malformed containers or nested
    # case-target fields must not abort an otherwise valid satellite ingest.
    merged = dict(existing) if isinstance(existing, dict) else {}
    incoming = dict(incoming) if isinstance(incoming, dict) else {}
    for key, value in incoming.items():
        # Conflict lineage is computed locally, never accepted from a provider.
        if key not in ("case_targets", "association_conflict"):
            merged[key] = value
    targets = []
    seen = set()
    previous_targets = merged.get("case_targets")
    new_targets = incoming.get("case_targets")
    for row in [
        *(previous_targets if isinstance(previous_targets, list) else []),
        *(new_targets if isinstance(new_targets, list) else []),
    ]:
        if not isinstance(row, dict):
            continue
        # A tuple containing a provider-supplied list/dict is unhashable.
        # Canonical JSON retains the established seven-field deduplication
        # identity while tolerating nested JSON values.
        key = json.dumps(
            [
                row.get("role"), row.get("lat"), row.get("lon"), row.get("at"),
                row.get("search_direction"), row.get("drift_id"), row.get("trajectory_index"),
            ],
            sort_keys=True, separators=(",", ":"), default=str,
        )
        if key in seen:
            continue
        seen.add(key)
        targets.append(dict(row))
    if targets:
        merged["case_targets"] = targets
    return merged


def _reconcile_association(existing: Any, incoming: SatelliteObservation) -> None:
    """Keep replayed SAR evidence consistent; quarantine contradictory matches.

    A contextual replay must not erase a valid strong match. An explicit
    conflict, or two different strong episode identities for one observation,
    instead invalidates automatic corroboration until human review.
    """
    old_status = existing.association_status
    new_status = incoming.association_status

    # Once contradictory evidence is recorded, a routine ingest must not
    # silently re-promote the same observation to a confirmed identity.
    if old_status == "conflict":
        existing.episode_id = None
        existing.evidence_status = "contextual"
        return

    if new_status == "conflict" and old_status == "strong":
        existing.association_status = "conflict"
        existing.episode_id = None
        existing.evidence_status = "contextual"
        return

    if new_status == "strong" and incoming.episode_id:
        if (
            old_status == "strong"
            and existing.episode_id
            and existing.episode_id != incoming.episode_id
        ):
            existing.association_status = "conflict"
            existing.episode_id = None
            existing.evidence_status = "contextual"
            return
        existing.association_status = "strong"
        existing.episode_id = incoming.episode_id
        existing.evidence_status = "associated"
        return

    if old_status == "strong" and existing.episode_id:
        # No demotion for an ordinary unmatched/contextual replay.
        return

    if new_status == "strong" and not incoming.episode_id:
        # A provider flag without a canonical parent is not corroboration.
        new_status = "provider_matched_unresolved"
    if new_status:
        existing.association_status = new_status
    # A non-strong observation must never acquire an episode identity solely
    # because an upstream record provided an episode_id field.
    existing.episode_id = None
    if incoming.evidence_status not in ("contextual", "associated"):
        existing.evidence_status = incoming.evidence_status
    else:
        existing.evidence_status = "contextual"


def _reconcile_observation_replay(existing: Any, incoming: SatelliteObservation) -> None:
    """Reconcile association and provenance together, preserving conflict lineage."""
    previous = existing.provenance if isinstance(existing.provenance, dict) else {}
    previous_status = existing.association_status
    previous_episode = existing.episode_id
    merged = _merged_provenance(previous, incoming.provenance)
    _reconcile_association(existing, incoming)

    if existing.association_status == "conflict":
        # A later replay must not replace the original reason for quarantine.
        merged["association_method"] = "conflict_requires_review"
        if previous_status == "conflict" and isinstance(previous.get("association_conflict"), dict):
            merged["association_conflict"] = previous["association_conflict"]
        else:
            merged["association_conflict"] = {
                "previous_status": previous_status,
                "previous_episode_id": previous_episode,
                "incoming_status": incoming.association_status,
                "incoming_episode_id": incoming.episode_id,
            }
    elif previous_status == "strong" and existing.association_status == "strong":
        # Contextual replays must not erase the provenance of a retained link.
        if incoming.association_status != "strong":
            for key in ("association_method", "provider_matched"):
                if key in previous:
                    merged[key] = previous[key]

    existing.provenance = merged


_REPLAY_IDENTITY_FIELDS = (
    "incident_id", "provider", "mission", "product_id",
    "acquisition_time", "sensor_type",
)


def _same_observation_identity(existing: Any, incoming: SatelliteObservation) -> bool:
    """An observation ID cannot silently change its case or source identity.

    Scene metadata and GFW detections may be replayed. Only evidence from
    the same immutable observation is eligible for provenance/association
    reconciliation. Reject ID collisions instead of merging evidence across
    cases or satellite products.
    """
    return all(
        getattr(existing, field, None) == getattr(incoming, field, None)
        for field in _REPLAY_IDENTITY_FIELDS
    )


def persist_observations(observations: list[SatelliteObservation]) -> int:
    """Persist scene metadata idempotently while merging case-target lineage."""
    from core.db.models import SatelliteObservationDB
    from core.db.session import session_scope
    from core.intel.lifecycle import parse_utc

    created = 0
    with session_scope() as db:
        for observation in observations:
            existing = db.get(SatelliteObservationDB, observation.observation_id)
            if existing is not None:
                if not _same_observation_identity(existing, observation):
                    # Preserve the original row and evidence exactly. A shared
                    # scene must use a case-scoped observation ID, not silently
                    # transfer its episode association to another incident.
                    logger.warning(
                        "Rejecting satellite observation ID collision: %s",
                        observation.observation_id,
                    )
                    continue
                _reconcile_observation_replay(existing, observation)
                continue
            discovered = parse_utc(observation.discovered_at)
            db.add(SatelliteObservationDB(
                observation_id=observation.observation_id,
                incident_id=observation.incident_id,
                provider=observation.provider,
                mission=observation.mission,
                product_id=observation.product_id,
                acquisition_time=observation.acquisition_time,
                discovered_at=(discovered or datetime.now(timezone.utc)).replace(tzinfo=None),
                footprint=observation.footprint,
                bbox=observation.bbox,
                sensor_type=observation.sensor_type,
                temporal_relation=observation.temporal_relation,
                temporal_delta_s=observation.temporal_delta_s,
                asset_ref=observation.asset_ref,
                source_url=observation.source_url,
                provenance=observation.provenance,
                resolution_m=observation.resolution_m,
                cloud_cover=observation.cloud_cover,
                polarisation=observation.polarisation,
                evidence_status=observation.evidence_status,
                association_status=observation.association_status,
                episode_id=observation.episode_id,
            ))
            created += 1
    return created


def list_incident_observations(incident_id: str) -> list[SatelliteObservation]:
    from core.db.models import SatelliteObservationDB
    from core.db.session import session_scope

    with session_scope() as db:
        rows = (
            db.query(SatelliteObservationDB)
            .filter(SatelliteObservationDB.incident_id == incident_id)
            .order_by(SatelliteObservationDB.acquisition_time.asc())
            .all()
        )
        return [SatelliteObservation(
            observation_id=row.observation_id,
            incident_id=row.incident_id,
            provider=row.provider,
            mission=row.mission,
            product_id=row.product_id,
            acquisition_time=row.acquisition_time,
            discovered_at=row.discovered_at.replace(tzinfo=timezone.utc).isoformat()
            if row.discovered_at else "",
            footprint=row.footprint,
            bbox=list(row.bbox) if row.bbox else None,
            sensor_type=row.sensor_type,
            temporal_relation=row.temporal_relation,
            temporal_delta_s=float(row.temporal_delta_s or 0),
            asset_ref=row.asset_ref or "",
            source_url=row.source_url or "",
            provenance=dict(row.provenance or {}),
            resolution_m=row.resolution_m,
            cloud_cover=row.cloud_cover,
            polarisation=list(row.polarisation) if row.polarisation else None,
            evidence_status=row.evidence_status or "contextual",
            association_status=row.association_status,
            episode_id=row.episode_id,
        ) for row in rows]


def _valid_mmsi(value: Any) -> str:
    text = str(value or "").strip()
    return text if len(text) == 9 and text.isascii() and text.isdecimal() else ""


def _valid_detection_position(lat: Any, lon: Any) -> tuple[float, float] | None:
    """Reject non-finite, malformed and out-of-WGS84 SAR target coordinates."""
    if isinstance(lat, bool) or isinstance(lon, bool):
        return None
    try:
        latitude, longitude = float(lat), float(lon)
    except (TypeError, ValueError, OverflowError):
        return None
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return None
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None
    return latitude, longitude


def _valid_acquisition_time(value: Any, now: datetime) -> str | None:
    """Require an actual timezone-qualified acquisition, never fabricate 'now'."""
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        observed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        return None
    observed = observed.astimezone(timezone.utc)
    if observed > now + timedelta(minutes=5):
        return None
    return observed.isoformat()


def materialize_sar_detections(
    *,
    incident_id: str,
    cue: dict[str, Any],
    expected_mmsi: str | None = None,
    episode_id: str | None = None,
) -> list[SatelliteObservation]:
    """Materialize GFW SAR detections with conservative association semantics.

    Exact provider MMSI equality may attach a detection to the current
    canonical episode. An unmatched target, a conflicting MMSI, or a provider
    identity that cannot be compared stays contextual.
    """
    import hashlib

    raw = cue.get("gfw_sar_detections")
    if not isinstance(raw, list):
        raw = cue.get("gfw_unmatched_in_area") or []
    detections = [d for d in raw if isinstance(d, dict)]
    expected = _valid_mmsi(expected_mmsi)
    observations: list[SatelliteObservation] = []
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    for detection in detections:
        position = _valid_detection_position(detection.get("lat"), detection.get("lon"))
        timestamp = _valid_acquisition_time(detection.get("timestamp"), now_dt)
        if position is None or timestamp is None:
            continue
        lat, lon = position
        digest = hashlib.blake2s(
            f"{incident_id}:{timestamp}:{lat}:{lon}".encode(), digest_size=16,
        ).hexdigest()
        detected = _valid_mmsi(detection.get("mmsi"))
        # JSON boolean only: e.g. the string "false" must not promote a target.
        provider_matched = detection.get("matched") is True
        if provider_matched and expected and detected == expected and episode_id:
            association_status = "strong"
            linked_episode = episode_id
            evidence_status = "associated"
            association_method = "provider_exact_mmsi"
        elif provider_matched and detected and expected and detected != expected:
            association_status = "conflict"
            linked_episode = None
            evidence_status = "contextual"
            association_method = "provider_mmsi_conflict"
        elif provider_matched:
            association_status = "provider_matched_unresolved"
            linked_episode = None
            evidence_status = "contextual"
            association_method = "provider_identity_unresolved"
        else:
            association_status = "unmatched_candidate"
            linked_episode = None
            evidence_status = "contextual"
            association_method = "none"

        observations.append(SatelliteObservation(
            observation_id=f"sat:gfw_sar:{digest}",
            incident_id=incident_id,
            provider="gfw",
            mission="sentinel1",
            product_id=f"gfw_sar:{digest}",
            acquisition_time=timestamp,
            discovered_at=now,
            footprint={"type": "Point", "coordinates": [float(lon), float(lat)]},
            bbox=None,
            sensor_type="sar",
            temporal_relation="nearest",
            temporal_delta_s=0.0,
            asset_ref="",
            source_url="",
            provenance={
                "source": "gfw_sar_detection",
                "darkship_cue": True,
                "provider_matched": provider_matched,
                "association_method": association_method,
            },
            evidence_status=evidence_status,
            association_status=association_status,
            episode_id=linked_episode,
        ))
    return observations


def materialize_unmatched_sar_detections(
    *, incident_id: str, cue: dict[str, Any],
) -> list[SatelliteObservation]:
    """Backward-compatible contextual-only materialization."""
    contextual_cue = dict(cue)
    contextual_cue["gfw_sar_detections"] = [
        d for d in (cue.get("gfw_unmatched_in_area") or ()) if isinstance(d, dict)
    ]
    return materialize_sar_detections(incident_id=incident_id, cue=contextual_cue)
