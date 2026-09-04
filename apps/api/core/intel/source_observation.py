# SPDX-License-Identifier: AGPL-3.0-or-later
"""SourceObservation write path (docs/fixes.md M1.1).

The first durable, lossless layer of the canonical data flow:

    source adapter -> normalize envelope -> SourceObservationDB -> downstream subscribers

``record_observation()`` is the only way a source adapter should create one
of these rows. It is idempotent by ``(source_name, source_id)`` -- the
"source-stable delivery key" docs/fixes.md requires every connector to use
-- so replaying the exact same raw fixture twice produces one row and an
identical returned dict both times, never a duplicate (the M1.1 exit gate).

This module does not replace ``core.intel.store.intel_store`` / the
``IntelEventDB`` public-projection envelope. Wired (docs/fixes.md M1.2 /
docs/updates.md P0.2) alongside each adapter's existing write path, never
replacing it, in: core.intel.twikit_monitor, core.intel.news_monitor,
core.intel.gdacs_monitor, core.intel.ingestion_service, core.vessels.
ais_source_observation, core.intel.gfw_monitor, core.intel.viirs_monitor,
core.intel.twitter_monitor, core.intel.vessel_incident_monitor,
core.mda.warfare. core.mda.watch's own detections (scan_gaps and
siblings) are derived features over AIS positions already recorded
through core.vessels.ais_source_observation, not new source acquisition,
so they intentionally have no SourceObservation call site of their own.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.db.models import SourceObservationDB

DEFAULT_SCHEMA_VERSION = 1


def observation_id(source_name: str, source_id: str) -> str:
    """Deterministic id from the delivery key -- this, not a fresh UUID per
    call, is what makes record_observation() idempotent: the same
    (source_name, source_id) always resolves to the same row."""
    digest = hashlib.blake2s(f"{source_name}:{source_id}".encode(), digest_size=16).hexdigest()
    return f"obs:{digest}"


def _payload_hash(raw_payload: str | bytes) -> str:
    data = raw_payload.encode("utf-8") if isinstance(raw_payload, str) else raw_payload
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class SourceObservation:
    observation_id: str
    service: str
    lane: str
    observation_type: str
    source_name: str
    source_policy: str
    source_id: str
    source_url: str
    observed_at: str
    received_at: str
    raw_payload_hash: str
    raw_payload_ref: str
    lat: float | None
    lon: float | None
    location_precision: str | None
    uncertainty_m: float | None
    subject_refs: list[str]
    provenance: dict[str, Any]
    schema_version: int
    preservation_status: str
    replayed: bool  # True when this call found an existing row (idempotent hit)


def _to_observation(row: SourceObservationDB, *, replayed: bool) -> SourceObservation:
    return SourceObservation(
        observation_id=row.observation_id,
        service=row.service,
        lane=row.lane,
        observation_type=row.observation_type,
        source_name=row.source_name,
        source_policy=row.source_policy,
        source_id=row.source_id,
        source_url=row.source_url or "",
        observed_at=row.observed_at,
        received_at=row.received_at.isoformat() if row.received_at else "",
        raw_payload_hash=row.raw_payload_hash,
        raw_payload_ref=row.raw_payload_ref or "",
        lat=row.lat,
        lon=row.lon,
        location_precision=row.location_precision,
        uncertainty_m=row.uncertainty_m,
        subject_refs=list(row.subject_refs or []),
        provenance=dict(row.provenance or {}),
        schema_version=row.schema_version,
        preservation_status=row.preservation_status or "",
        replayed=replayed,
    )


def record_observation(
    db,
    *,
    service: str,
    lane: str,
    observation_type: str,
    source_name: str,
    source_policy: str,
    source_id: str,
    observed_at: str,
    raw_payload: str | bytes,
    source_url: str = "",
    raw_payload_ref: str = "",
    lat: float | None = None,
    lon: float | None = None,
    location_precision: str | None = None,
    uncertainty_m: float | None = None,
    subject_refs: list[str] | None = None,
    provenance: dict[str, Any] | None = None,
    schema_version: int = DEFAULT_SCHEMA_VERSION,
) -> SourceObservation:
    """Record one immutable SourceObservation, idempotently.

    Caller owns the transaction (``db``); this flushes but does not commit.
    A second call with the same (source_name, source_id) returns the
    existing row unchanged (``replayed=True``) -- it never re-hashes the
    new raw_payload against the stored one and never updates the row: the
    whole point of an immutable observation is that it does not change
    once recorded. A source that legitimately has new information sends a
    new source_id (e.g. a new tweet id, a new AIS message sequence).
    """
    from core.intel.preservation import classify_preservation_status

    obs_id = observation_id(source_name, source_id)
    existing = db.get(SourceObservationDB, obs_id)
    if existing is not None:
        return _to_observation(existing, replayed=True)

    row = SourceObservationDB(
        observation_id=obs_id,
        service=service,
        lane=lane,
        observation_type=observation_type,
        source_name=source_name,
        source_policy=source_policy,
        source_id=source_id,
        source_url=source_url,
        observed_at=observed_at,
        # Naive UTC, matching this codebase's DateTime-column convention
        # (e.g. core.cases.service.open_case's retention_until) -- SQLite
        # has no native timezone-aware storage, so a tz-aware value written
        # here comes back naive on the next fetch (record_observation's own
        # idempotent-replay path); storing naive from the start keeps a
        # freshly created row and one re-fetched from the DB identical.
        received_at=datetime.now(timezone.utc).replace(tzinfo=None),
        raw_payload_hash=_payload_hash(raw_payload),
        raw_payload_ref=raw_payload_ref,
        lat=lat,
        lon=lon,
        location_precision=location_precision,
        uncertainty_m=uncertainty_m,
        subject_refs=list(subject_refs or []),
        provenance=dict(provenance or {}),
        schema_version=schema_version,
        preservation_status=classify_preservation_status(
            service, has_archive_ref=bool(raw_payload_ref),
        ),
    )
    db.add(row)
    db.flush()
    return _to_observation(row, replayed=False)


def get_observation(db, obs_id: str) -> SourceObservation | None:
    row = db.get(SourceObservationDB, obs_id)
    return _to_observation(row, replayed=True) if row is not None else None
