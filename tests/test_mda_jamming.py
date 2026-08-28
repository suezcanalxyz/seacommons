# SPDX-License-Identifier: AGPL-3.0-or-later
"""GNSS jamming zone index."""
from __future__ import annotations

import json

from core.mda import jamming as jam


def test_empty_index_is_clear():
    idx = jam.JammingIndex()
    # bundle has no cached file in CI -> everything clear
    assert idx.in_jamming_zone(35.0, 33.0) == 0.0


def test_index_loads_a_zone(tmp_path, monkeypatch):
    gj = {
        "as_of": "2026-08-29",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[32.0, 34.0], [34.0, 34.0], [34.0, 36.0], [32.0, 36.0], [32.0, 34.0]]]},
            "properties": {"bad": 40, "count": 50},
        }],
    }
    f = tmp_path / "current.geojson"
    f.write_text(json.dumps(gj))
    monkeypatch.setattr(jam, "_CURRENT", f)
    idx = jam.JammingIndex()
    assert idx.in_jamming_zone(35.0, 33.0) >= 0.7      # inside, bad/total = 0.8
    assert idx.in_jamming_zone(10.0, 5.0) == 0.0       # outside
    assert idx.as_of() == "2026-08-29"
