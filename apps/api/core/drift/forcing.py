# SPDX-License-Identifier: AGPL-3.0-or-later
"""Forcing provenance and operational-quality policy."""
from __future__ import annotations


def classify_forcing_quality(
    *,
    wind_coverage: float,
    current_coverage: float,
    cmems_current: bool,
    grid_reader: bool,
) -> tuple[str, bool]:
    """Classify required forcing from observed coverage, not reader presence.

    Wind and current are required. CMEMS can satisfy current coverage, but no
    reader object can turn absent wind samples into observed forcing.
    """
    wind = max(0.0, min(1.0, float(wind_coverage)))
    current = 1.0 if cmems_current else max(0.0, min(1.0, float(current_coverage)))
    if grid_reader and wind == 1.0 and current == 1.0:
        return "observed-spatiotemporal", True
    if wind > 0.0 and current > 0.0:
        return "mixed", False
    return "degraded-constant", False
