# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mediterranean/Atlantic region classification (docs/updates.md P1.2).

**Goal:** the Coverage Matrix needs a region label per observed event.
This module is the one place that owns that classification -- every
other module that needs a region string must call ``classify_region``
here rather than re-deriving its own bounding boxes.

The boxes below are deliberately approximate operational groupings
(the same six named in docs/updates.md P1.2), not authoritative
geographic or political boundaries -- they exist only to bucket a
lat/lon pair for coverage reporting. Overlap is resolved by checking
the narrower/more specific regions (Aegean, Adriatic/Ionian, Atlantic/
Canary) before the broad Western/Central/Eastern Mediterranean bands.
A coordinate outside every box returns ``None`` honestly rather than
being forced into the nearest region.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

REGIONS: tuple[str, ...] = (
    "Western Mediterranean",
    "Central Mediterranean",
    "Eastern Mediterranean",
    "Aegean",
    "Adriatic / Ionian",
    "Atlantic / Canary route",
)


class _BBox(NamedTuple):
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


# Checked in this order -- narrower/more specific regions first so they
# win over the broad Mediterranean bands they geographically overlap.
_ORDERED_BOXES: tuple[tuple[str, _BBox], ...] = (
    ("Aegean", _BBox(35.0, 40.5, 23.0, 29.0)),
    ("Adriatic / Ionian", _BBox(38.0, 45.8, 12.0, 20.0)),
    ("Atlantic / Canary route", _BBox(20.0, 36.5, -20.0, -6.0)),
    ("Western Mediterranean", _BBox(34.5, 41.0, -6.0, 3.0)),
    ("Central Mediterranean", _BBox(30.0, 38.5, 3.0, 20.0)),
    ("Eastern Mediterranean", _BBox(30.5, 37.5, 20.0, 36.5)),
)


def classify_region(lat: Optional[float], lon: Optional[float]) -> Optional[str]:
    """Returns one of REGIONS, or None if lat/lon is missing or falls
    outside every known box (never guessed/forced)."""
    if lat is None or lon is None:
        return None
    for name, box in _ORDERED_BOXES:
        if box.lat_min <= lat <= box.lat_max and box.lon_min <= lon <= box.lon_max:
            return name
    return None
