# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sentinel scene metadata cache + AOI/time query (docs/fixes.md M7.1).

**Goal (M7): use independent sensors to strengthen evidence without
overstating attribution.** M7.1: "Current Copernicus STAC only. Cache
scene metadata. Query by episode AOI and time window."

This module is the cache-and-query half only: ``SceneMetadata`` plus
``query_scenes()``, a pure filter over an already-fetched scene list. It
does **not** include a live Copernicus STAC HTTP client -- fetching real
scene metadata needs Copernicus Data Space Ecosystem credentials this
session has no access to, and guessing at STAC request/response shapes
without being able to test against the real API would produce untested,
unverifiable integration code. That client is its own follow-up, to be
built and tested against real (or recorded/replayed) STAC responses.

``query_scenes()`` is what a caller (an episode from M5.2's
``core.live.episode_builder``, or a hypothesis from M6's
``core.intel.hypothesis``) uses once scenes exist in the cache: "does any
cached scene cover this AOI within this time window."
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class SceneMetadata:
    """One cached Copernicus STAC item -- only the fields M7.2's
    association step actually needs, not the full STAC item schema."""

    scene_id: str
    collection: str  # e.g. "sentinel-1-grd", "sentinel-2-l2a"
    acquired_at: datetime
    bbox: tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)
    cloud_cover_pct: Optional[float] = None
    stac_href: str = ""


def _bbox_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    a_min_lon, a_min_lat, a_max_lon, a_max_lat = a
    b_min_lon, b_min_lat, b_max_lon, b_max_lat = b
    return not (
        a_max_lon < b_min_lon or b_max_lon < a_min_lon
        or a_max_lat < b_min_lat or b_max_lat < a_min_lat
    )


def query_scenes(
    scenes: list[SceneMetadata],
    *,
    aoi_bbox: tuple[float, float, float, float],
    time_start: datetime,
    time_end: datetime,
) -> list[SceneMetadata]:
    """Every cached scene whose acquisition time falls in
    ``[time_start, time_end]`` and whose bbox intersects ``aoi_bbox``,
    newest first. Pure filter -- never fetches, never mutates the cache;
    a caller owns populating ``scenes`` from wherever it keeps the cache
    (in-memory list, DB rows mapped to SceneMetadata, ...).
    """
    matches = [
        scene
        for scene in scenes
        if time_start <= scene.acquired_at <= time_end
        and _bbox_intersects(scene.bbox, aoi_bbox)
    ]
    matches.sort(key=lambda s: s.acquired_at, reverse=True)
    return matches
