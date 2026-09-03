# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/fixes.md M7.1: Sentinel scene metadata cache + AOI/time query."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.mda.sentinel_cache import SceneMetadata, query_scenes

_T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _scene(scene_id, *, hours_offset=0, bbox=(13.0, 34.0, 15.0, 36.0)):
    return SceneMetadata(
        scene_id=scene_id, collection="sentinel-1-grd",
        acquired_at=_T0 + timedelta(hours=hours_offset), bbox=bbox,
    )


def test_query_matches_scenes_inside_the_time_window():
    scenes = [_scene("in", hours_offset=0), _scene("out", hours_offset=48)]
    result = query_scenes(
        scenes, aoi_bbox=(13.0, 34.0, 15.0, 36.0),
        time_start=_T0 - timedelta(hours=1), time_end=_T0 + timedelta(hours=1),
    )
    assert [s.scene_id for s in result] == ["in"]


def test_query_matches_scenes_whose_bbox_intersects_the_aoi():
    scenes = [
        _scene("overlap", bbox=(14.0, 35.0, 16.0, 37.0)),
        _scene("far", bbox=(100.0, 50.0, 102.0, 52.0)),
    ]
    result = query_scenes(
        scenes, aoi_bbox=(13.0, 34.0, 15.0, 36.0),
        time_start=_T0 - timedelta(hours=1), time_end=_T0 + timedelta(hours=1),
    )
    assert [s.scene_id for s in result] == ["overlap"]


def test_query_results_are_newest_first():
    scenes = [_scene("older", hours_offset=-2), _scene("newer", hours_offset=-1)]
    result = query_scenes(
        scenes, aoi_bbox=(13.0, 34.0, 15.0, 36.0),
        time_start=_T0 - timedelta(hours=3), time_end=_T0,
    )
    assert [s.scene_id for s in result] == ["newer", "older"]


def test_query_never_mutates_the_input_list():
    scenes = [_scene("a", hours_offset=-2), _scene("b", hours_offset=-1)]
    original_order = list(scenes)
    query_scenes(
        scenes, aoi_bbox=(13.0, 34.0, 15.0, 36.0),
        time_start=_T0 - timedelta(hours=3), time_end=_T0,
    )
    assert scenes == original_order


def test_empty_cache_returns_no_matches():
    assert query_scenes(
        [], aoi_bbox=(13.0, 34.0, 15.0, 36.0), time_start=_T0, time_end=_T0,
    ) == []
