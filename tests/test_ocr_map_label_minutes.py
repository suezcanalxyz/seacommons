# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression for Alarm Phone map-label OCR with omitted minute-prime glyphs."""
import pytest

from core.intel.geoextract import _extract_numeric_coords_raw


@pytest.mark.parametrize("label", [
    "38 people in distress @11:28CET at N36°04, E016°37",
    "N36°04 E016°37",
    "N36°04' E016°37'",
    "N 36° 04’ E 016° 37’",
])
def test_alarm_phone_map_label_coordinate(label):
    lat, lon = _extract_numeric_coords_raw(label)
    assert lat == pytest.approx(36 + 4 / 60, abs=1e-5)
    assert lon == pytest.approx(16 + 37 / 60, abs=1e-5)


@pytest.mark.parametrize("label", [
    "N36°99 E016°37",  # invalid minute, never clamp
    "N36°04 E016°99",
    "Palermo Sicily Malta",  # no invented exact position
    "N36 E016",  # degrees alone are insufficient
])
def test_invalid_or_ambiguous_ocr_does_not_create_position(label):
    assert _extract_numeric_coords_raw(label) is None
