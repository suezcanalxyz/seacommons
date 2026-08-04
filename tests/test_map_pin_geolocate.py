# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from core.intel.map_pin_geolocate import (
    _fit_axis,
    _haversine_km,
    _match_landmarks,
    _normalize_label,
    geolocate_pin_from_image,
)


def test_normalize_label_strips_accents_and_punctuation() -> None:
    assert _normalize_label("Réthymno,") == "rethymno"
    assert _normalize_label("Agíos Nikolaos") == "agios nikolaos"
    assert _normalize_label("  Heraklion  ") == "heraklion"


def _word(text, left, top, width, height, *, block="1", par="1", line="1", word=1):
    return {
        "text": text, "left": left, "top": top, "width": width, "height": height,
        "block": block, "par": par, "line": line, "word": word,
    }


def test_match_landmarks_finds_single_word_places() -> None:
    boxes = [
        _word("Heraklion", 100, 50, 90, 14, line="1", word=1),
        _word("Rethymno", 400, 55, 80, 14, line="2", word=1),
        _word("Unrelated", 200, 200, 90, 14, line="3", word=1),
    ]
    matches = dict((name, (px, py)) for name, px, py in _match_landmarks(boxes))
    assert "heraklion" in matches
    assert "rethymno" in matches
    assert "unrelated" not in matches
    assert matches["heraklion"] == (145.0, 57.0)


def test_match_landmarks_joins_adjacent_words_for_multiword_places() -> None:
    boxes = [
        _word("Agios", 100, 50, 60, 14, line="1", word=1),
        _word("Nikolaos", 165, 50, 90, 14, line="1", word=2),
    ]
    matches = dict((name, (px, py)) for name, px, py in _match_landmarks(boxes))
    assert "agios nikolaos" in matches


def test_fit_axis_recovers_linear_relationship() -> None:
    # pixel = 10*geo + 5, exactly — polyfit should recover it losslessly.
    geo = [1.0, 2.0, 3.0]
    pixel = [15.0, 25.0, 35.0]
    slope, intercept = _fit_axis(pixel, geo)
    assert abs(slope - 10.0) < 1e-6
    assert abs(intercept - 5.0) < 1e-6


def test_fit_axis_returns_none_for_degenerate_input() -> None:
    assert _fit_axis([10.0, 10.0, 10.0], [1.0, 1.0, 1.0]) is None


def test_haversine_km_known_distance() -> None:
    # Rome to Naples is a well-known ~190 km great-circle distance.
    km = _haversine_km(41.90, 12.50, 40.85, 14.27)
    assert 180 < km < 210


def test_haversine_km_zero_for_identical_points() -> None:
    assert _haversine_km(35.0, 25.0, 35.0, 25.0) == 0.0


def test_geolocate_pin_from_image_returns_none_without_tesseract(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert geolocate_pin_from_image(b"not a real image") is None


def test_geolocate_pin_from_image_end_to_end_with_synthetic_map(monkeypatch) -> None:
    """Build a synthetic 'map': two labelled towns + a red pin between them,
    positioned so the true pin location is knowable in advance, then check
    the recovered lat/lon is close to that ground truth."""
    import io

    import numpy as np
    from PIL import Image

    width, height = 900, 600
    img = np.full((height, width, 3), 235, dtype=np.uint8)  # light basemap

    # A single consistent north-up linear model (pixel = scale*geo + origin)
    # shared by every landmark AND the pin, exactly like a real web-map
    # projection over a small extent — so the fit should recover it exactly.
    def lon_to_x(lon: float) -> int:
        return round(400 * (lon - 24.0) + 50)

    def lat_to_y(lat: float) -> int:
        return round(800 * (35.50 - lat) + 50)  # y grows as lat decreases

    def x_to_lon(x: float) -> float:
        return (x - 50) / 400 + 24.0

    def y_to_lat(y: float) -> float:
        return 35.50 - (y - 50) / 800

    landmarks = {
        "Heraklion": (35.34, 25.13),
        "Rethymno": (35.37, 24.47),
        "Ierapetra": (35.01, 25.74),
    }
    pin_px = (400, 300)
    expected_lon = x_to_lon(pin_px[0])
    expected_lat = y_to_lat(pin_px[1])

    # Paint a compact red teardrop-ish blob at the pin's pixel position.
    px, py = pin_px
    img[py - 6:py + 6, px - 4:px + 4] = [220, 40, 30]

    image = Image.fromarray(img, mode="RGB")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    payload = buf.getvalue()

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/tesseract")

    fake_boxes = []
    for line_num, (name, (lat, lon)) in enumerate(landmarks.items(), start=1):
        center_x, center_y = lon_to_x(lon), lat_to_y(lat)
        fake_boxes.append({
            "text": name, "left": center_x - 40, "top": center_y - 6,
            "width": 80, "height": 12,
            "block": "1", "par": "1", "line": str(line_num), "word": 1,
        })
    monkeypatch.setattr(
        "core.intel.map_pin_geolocate._ocr_word_boxes",
        lambda image, executable: fake_boxes,
    )

    result = geolocate_pin_from_image(payload)
    assert result is not None
    lat, lon = result
    assert abs(lon - expected_lon) < 0.02
    assert abs(lat - expected_lat) < 0.02


def test_geolocate_pin_from_image_refuses_a_fit_far_from_every_matched_landmark(monkeypatch) -> None:
    """Within the broad Mediterranean lat/lon bounds but ~800 km from both
    matched landmarks — the kind of result a genuinely wrong OCR match (not
    an out-of-theatre one) would produce. The nearest-landmark distance
    guard, not the lat/lon range check, must be what rejects this."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/tesseract")
    monkeypatch.setattr(
        "core.intel.map_pin_geolocate._detect_marker_pixel",
        lambda image: (150, -7240),
    )
    monkeypatch.setattr(
        "core.intel.map_pin_geolocate._ocr_word_boxes",
        lambda image, executable: [
            {"text": "Heraklion", "left": 110, "top": 94, "width": 80, "height": 12,
             "block": "1", "par": "1", "line": "1", "word": 1},
            {"text": "Rethymno", "left": 130, "top": 124, "width": 80, "height": 12,
             "block": "1", "par": "1", "line": "2", "word": 1},
        ],
    )
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (235, 235, 235)).save(buf, format="PNG")
    assert geolocate_pin_from_image(buf.getvalue()) is None


def test_geolocate_pin_from_image_refuses_single_landmark(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/tesseract")
    monkeypatch.setattr(
        "core.intel.map_pin_geolocate._detect_marker_pixel",
        lambda image: (400, 300),
    )
    monkeypatch.setattr(
        "core.intel.map_pin_geolocate._ocr_word_boxes",
        lambda image, executable: [
            {"text": "Heraklion", "left": 100, "top": 100, "width": 80, "height": 12,
             "block": "1", "par": "1", "line": "1", "word": 1},
        ],
    )
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (235, 235, 235)).save(buf, format="PNG")
    assert geolocate_pin_from_image(buf.getvalue()) is None
