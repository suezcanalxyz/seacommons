# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure, deterministic AIS-behaviour classifiers (docs/fixes.md M4.1).

``AISSpikeDetector`` (core.intel.ais_spike_detector) is stateful and
time-series-driven -- it polls the live vessel registry, keeps an
in-memory previous-sample dict, and emits IntelEvents as a side effect.
There has never been a pure ``classify(input) -> label`` entry point for
it to call in isolation, so ``tests/fixtures/alert_recognition/
ais_behaviour.jsonl`` sat unscored (docs/ALERT_RECOGNITION_BASELINE.md)
since it was written.

This module is that entry point: ``classify(input: dict) -> (label,
confidence)`` for exactly the fixture's input shape (an ordered dict of
named fields, not a live registry snapshot), replaying the SAME threshold
constants ``ais_spike_detector`` already uses (imported, not duplicated) so
neither module's tuning can silently drift out of sync with the other.
It does not replace the live detector or touch its emission/state logic --
this is read-only classification for the replay/scoring surface only.

v0 scope: three of ``ais_behaviour.jsonl``'s kinds are covered --
sudden_stop, rescue_cluster, ngo_search_pattern (vessel_loiter has no
fixture yet). ``ais_integrity.jsonl`` (gap/impossible_speed/
dark_zone_entry) is a separate follow-up PR -- coverage-baseline
reasoning (M4.2) informs the gap classifier and shouldn't be guessed at
ahead of that milestone.
"""
from __future__ import annotations

from core.intel.ais_spike_detector import (
    CLUSTER_RADIUS_NM,
    SEARCH_TRACK_MIN_FIXES,
    SEARCH_TRACK_WINDOW_MIN,
    SPEED_THRESHOLD_KN,
    STOP_THRESHOLD_KN,
)

_MIN_SEARCH_TURN_COUNT = 3
_NOT_ALERTABLE = ("not_alertable", 0.0)


def classify_sudden_stop(
    *, previous_speed_kn: float, current_speed_kn: float, in_port_exclusion_zone: bool,
) -> tuple[str, float]:
    """A one-sample speed transition is a low-confidence *cue*, never a
    high-confidence alert on its own (docs/prompt.md) -- confirming it
    needs the same corroborating signals AISSpikeDetector already checks
    live (hotspot, NGO identity), which this single-sample replay input
    doesn't carry."""
    if in_port_exclusion_zone:
        return _NOT_ALERTABLE
    was_underway = previous_speed_kn >= SPEED_THRESHOLD_KN
    now_stopped = current_speed_kn <= STOP_THRESHOLD_KN
    if not (was_underway and now_stopped):
        return _NOT_ALERTABLE
    return "cue", 0.35


def classify_rescue_cluster(
    *,
    vessel_count: int,
    min_distance_nm: float,
    positions_fresh: bool,
    converging: bool,
    in_port: bool = False,
) -> tuple[str, float]:
    """Never more than *possible* from AIS proximity alone -- convergence
    and freshness raise confidence within that ceiling, they never promote
    it to a confirmed rescue."""
    if in_port or not positions_fresh:
        return _NOT_ALERTABLE
    if vessel_count < 2 or min_distance_nm > CLUSTER_RADIUS_NM:
        return _NOT_ALERTABLE
    confidence = 0.4
    if converging:
        confidence += 0.15
    if vessel_count >= 3:
        confidence += 0.1
    return "possible_rescue_cluster", min(confidence, 0.7)


def classify_ngo_search_pattern(
    *,
    fix_count: int,
    window_minutes: float,
    turn_count: int,
    known_operational_role: str,
) -> tuple[str, float]:
    """Only a known SAR-role vessel's track ever qualifies -- the same
    course-change signature from an unknown vessel is exactly what the
    spoofing/gap detectors treat as suspicious instead (core.mda.watch)."""
    if known_operational_role != "sar_ngo":
        return _NOT_ALERTABLE
    if fix_count < SEARCH_TRACK_MIN_FIXES or window_minutes > SEARCH_TRACK_WINDOW_MIN:
        return _NOT_ALERTABLE
    if turn_count < _MIN_SEARCH_TURN_COUNT:
        return _NOT_ALERTABLE
    confidence = 0.5 + min(0.3, 0.03 * turn_count)
    return "ngo_search_pattern", min(confidence, 0.8)


_CLASSIFIERS = {
    "sudden_stop": classify_sudden_stop,
    "rescue_cluster": classify_rescue_cluster,
    "ngo_search_pattern": classify_ngo_search_pattern,
}


def classify(input_: dict) -> tuple[str, float]:
    """Dispatch on input_["kind"] -- the ais_behaviour.jsonl fixture shape.

    Raises KeyError for a kind this v0 doesn't cover yet (vessel_loiter),
    rather than silently returning a fabricated not_alertable -- a caller
    (the scorer) needs to know the difference between "genuinely not
    alertable" and "this kind isn't implemented yet".
    """
    kind = input_["kind"]
    fn = _CLASSIFIERS[kind]
    kwargs = {k: v for k, v in input_.items() if k != "kind"}
    return fn(**kwargs)
