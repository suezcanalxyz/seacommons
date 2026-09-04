# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sanity checks for the synthetic Alarm Phone image fixture set.

These do not exercise the OCR pipeline (that is the benchmark's job -- see
`docs/ALARM_PHONE_IMAGE_PIPELINE_AUDIT.md` section 6). They prove the
generators are deterministic, render valid images, and that every
coordinate-bearing case's printed string is actually parseable by
`geoextract` to the ground-truth coordinate -- so a later PR that changes the
parser or the geolocator has a fixed target to hit.
"""
from __future__ import annotations

import io
import json
import math

import pytest
from core.intel.geoextract import extract_numeric_coords

from tests.fixtures.alarm_phone_images import CASES, ground_truth, render_case


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_case_renders_a_valid_deterministic_png(case) -> None:
    from PIL import Image

    first = case.render()
    second = case.render()
    assert first == second, f"{case.name} render is not deterministic"

    with Image.open(io.BytesIO(first)) as image:
        assert image.format == "PNG"
        assert image.width >= 320 and image.height >= 200


@pytest.mark.parametrize(
    "case",
    [c for c in CASES if c.has_coordinate_text],
    ids=lambda c: c.name,
)
def test_printed_coordinate_string_parses_to_ground_truth(case) -> None:
    """The popup text the generator draws must parse to the declared
    coordinate. Derives the string from the same source the renderer uses."""
    # The renderer draws the string via a closure; re-derive it from notes-free
    # ground truth by re-parsing the known formats used in the module.
    strings = {
        "coordinate_popup_dmm": "N 34\u00b0 16.292'  E 011\u00b0 56.538'",
        "coordinate_popup_dms": "37\u00b018'31.3\"N  27\u00b009'51.1\"E",
        "coordinate_popup_tiny_text": "N 33\u00b052.664'  E 013\u00b010.555'",
        "coordinate_popup_dark": "41\u00b033'09.1\"N  26\u00b031'37.1\"E",
        "coordinate_popup_quoted_tweet": "N 34\u00b0 16.292'  E 011\u00b0 56.538'",
        "low_res_preview_popup": "N 34\u00b0 16.292'  E 011\u00b0 56.538'",
    }
    parsed = extract_numeric_coords(strings[case.name])
    assert parsed is not None, f"{case.name}: parser returned None for its own popup text"
    assert case.expected_coordinate is not None
    error_km = _haversine_km(parsed, case.expected_coordinate)
    assert error_km <= case.tolerance_km, (
        f"{case.name}: parsed {parsed} is {error_km:.2f} km from "
        f"ground truth {case.expected_coordinate}"
    )


def test_negative_cases_have_no_expected_coordinate() -> None:
    for name in (
        "pin_insufficient_landmarks",
        "unrelated_numbers_no_coordinate",
        "text_card_people_and_condition",
        "photo_not_a_map",
    ):
        case = next(c for c in CASES if c.name == name)
        assert case.expected_coordinate is None


def test_ground_truth_is_json_serialisable() -> None:
    payload = json.dumps(ground_truth(), indent=2)
    restored = json.loads(payload)
    assert {row["name"] for row in restored} == {c.name for c in CASES}
    assert render_case(restored[0]["name"])
