# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure, deterministic AIS-integrity classifiers (docs/fixes.md M4.1/M4.3).

Sibling to core.intel.ais_behaviour_replay -- the same "pure classify(input)
-> (label, confidence)" entry point, this time for the ``ais_integrity.jsonl``
corpus (gap/impossible_speed/dark_zone_entry) that sat unscored since it was
written (docs/ALERT_RECOGNITION_BASELINE.md).

``classify_gap`` is the docs/fixes.md M4.3-relevant one: it distinguishes a
vessel-specific gap from a feed-wide coverage outage using
``local_reporting_ratio`` -- how many OTHER nearby vessels also kept
reporting through the same window (the same reasoning
core.mda.coverage.CoverageBaseline's neighbour_message_ratio/
local_receiver_density compute from live track history; this pure function
takes the ratio as an input rather than the live baseline, matching the
fixture's shape). Critically, it never looks at vessel type at all --
"vessel class becomes a contextual feature only" (M4.3) is satisfied here
by construction: there is no vessel_type parameter to exclude on. This
does NOT replace core.mda.watch.scan_gaps()'s hard vessel-class exclusions
yet -- wiring a coverage-ratio-based decision into that live, production
detector is a separate, larger PR needing its own careful review against
the M4.3 exit gate.
"""
from __future__ import annotations

_NOT_ALERTABLE = ("not_alertable", 0.0)

_IMPOSSIBLE_SPEED_FLOOR_KN = 50.0
_IMPOSSIBLE_SPEED_CONFIDENCE_SPAN_KN = 100.0


def classify_gap(
    *,
    silence_duration_min: float,
    nearby_vessels_reporting_before: int,
    nearby_vessels_reporting_after: int,
    local_reporting_ratio: float,
) -> tuple[str, float]:
    """docs/fixes.md M4.3: "a feed-wide AIS outage must NOT create hundreds
    of vessel-specific gaps." A low local_reporting_ratio means nearby
    traffic went quiet too -- the cause is the reception environment, not
    this one vessel. Vessel type is deliberately not a parameter here at
    all (see module docstring)."""
    if local_reporting_ratio < 0.5:
        return "coverage_gap", 0.05
    confidence = 0.4 + 0.3 * min(1.0, local_reporting_ratio)
    return "vessel_gap", round(min(confidence, 0.7), 3)


def classify_impossible_speed(
    *, implied_speed_kn: float, vessel_type: str, time_delta_s: float,
) -> tuple[str, float]:
    """A fixed physical-plausibility ceiling is the anomaly signal itself.
    ``vessel_type`` is accepted (present in every real message and in the
    fixture) but never used to gate the alert -- flagging a fast cargo
    ship the same way as any other type is exactly "vessel class becomes
    a contextual feature only" (M4.3), not an exemption list."""
    if implied_speed_kn < _IMPOSSIBLE_SPEED_FLOOR_KN:
        return _NOT_ALERTABLE
    over = implied_speed_kn - _IMPOSSIBLE_SPEED_FLOOR_KN
    confidence = 0.5 + over / _IMPOSSIBLE_SPEED_CONFIDENCE_SPAN_KN
    return "position_anomaly", round(min(confidence, 0.8), 3)


def classify_dark_zone_entry(
    *, mmsi: str, zone: str, prior_gap: bool,
) -> tuple[str, float]:
    """docs/fixes.md: "An AIS gap is not proof of intentional disabling" --
    single-signal zone entry is a *candidate*, never confirmed spoofing.
    A prior gap on the same vessel raises confidence but the ceiling stays
    well under the "confirmed" range."""
    if zone != "known_dark_fleet_corridor":
        return _NOT_ALERTABLE
    return "spoofing_candidate", 0.35 if prior_gap else 0.15


_CLASSIFIERS = {
    "gap": classify_gap,
    "impossible_speed": classify_impossible_speed,
    "dark_zone_entry": classify_dark_zone_entry,
}


def classify(input_: dict) -> tuple[str, float]:
    """Dispatch on input_["kind"] -- the ais_integrity.jsonl fixture shape.

    Raises KeyError for an unimplemented kind rather than silently
    returning a fabricated not_alertable.
    """
    kind = input_["kind"]
    fn = _CLASSIFIERS[kind]
    kwargs = {k: v for k, v in input_.items() if k != "kind"}
    return fn(**kwargs)
