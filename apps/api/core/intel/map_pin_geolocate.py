# SPDX-License-Identifier: AGPL-3.0-or-later
"""Geolocate a map-screenshot pin that carries no printed coordinate text.

Alarm Phone (and other tracked accounts) sometimes attach a plain map
screenshot — basemap + place-name labels + a single drop-pin marker — with
no lat/lon readout anywhere in the image. `x_media_utils.ocr_png_coordinate`
only ever finds a position when one is printed as text, so those images
silently fall back to a rough place-name/region centroid.

This module recovers a real position from the image itself:
  1. Detect the pin marker's pixel position (colour-based blob detection).
  2. OCR the full image for word-level bounding boxes.
  3. Match words (and adjacent-word phrases) against a small, precise
     gazetteer of unambiguous coastal towns/islands.
  4. With >= 2 matched landmarks, fit an independent linear pixel<->geo
     transform per axis (standard web maps are north-up, so x maps to
     longitude and y to latitude with no rotation/shear) and invert it for
     the pin's own pixel position.

Deliberately conservative: any missing precondition (no pin found, fewer
than two landmarks, degenerate/duplicate pixel positions, an out-of-range or
wildly extrapolated result) returns None rather than a guess — a caller that
gets None simply keeps the weaker fallback it already had.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import unicodedata
from typing import Optional

from core.intel.geoextract import PRECISE_PLACES

_MIN_LANDMARK_MATCHES = 2
_MIN_PIXEL_SPREAD = 20          # px — matched landmarks must actually spread out
_MIN_WORD_CONF = 40             # tesseract word confidence, 0-100
_EXTRAPOLATION_FACTOR = 2.0     # how far past the matched-landmark pixel span to still trust
_LAT_RANGE = (20.0, 48.0)
_LON_RANGE = (-12.0, 42.0)

_PLACES_SORTED = sorted(PRECISE_PLACES.items(), key=lambda kv: -len(kv[0]))
_MAX_PHRASE_WORDS = max((len(name.split()) for name in PRECISE_PLACES), default=1)


def _normalize_label(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z ]", "", stripped.lower()).strip()


def _detect_marker_pixel(image) -> Optional[tuple[int, int]]:
    """Find a single compact red drop-pin marker; None if none/ambiguous.

    Tuned for the marker red used by Google/Apple Maps and similar static
    map exports (high red, low green, low blue) — narrow enough to reject
    orange/tan basemap fills, which have a much higher green channel.
    """
    import numpy as np

    rgb = image.convert("RGB")
    pixels = np.asarray(rgb)
    r = pixels[:, :, 0].astype(int)
    g = pixels[:, :, 1].astype(int)
    b = pixels[:, :, 2].astype(int)
    mask = (r > 150) & (g < 110) & (b < 110) & (r - g > 60) & (r - b > 60)

    count = int(mask.sum())
    height, width = mask.shape
    if count < 12 or count > 0.02 * width * height:
        return None

    ys, xs = np.nonzero(mask)
    box_w = int(xs.max() - xs.min()) + 1
    box_h = int(ys.max() - ys.min()) + 1
    # A single pin icon is small and compact; a large/sparse red bounding box
    # means multiple unrelated red elements were picked up — bail rather
    # than average them into a meaningless point.
    if box_w > 0.1 * width or box_h > 0.12 * height:
        return None

    center_x = int(round(float(xs.mean())))
    # A teardrop pin's point is its bottom tip, not its centroid.
    tip_y = int(ys.max())
    return center_x, tip_y


def _ocr_word_boxes(image, *, executable: str) -> list[dict]:
    """Word-level OCR boxes (pixel-space) via tesseract's TSV output mode."""
    from PIL import Image

    width, _ = image.size
    scale = max(1, min(3, 2000 // max(1, width)))
    scaled = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS) if scale > 1 else image
    buf = io.BytesIO()
    scaled.convert("RGB").save(buf, format="PNG")

    try:
        result = subprocess.run(
            [executable, "stdin", "stdout", "--psm", "11", "-l", "eng", "tsv"],
            input=buf.getvalue(),
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    boxes: list[dict] = []
    lines = result.stdout.decode("utf-8", errors="replace").splitlines()
    for line in lines[1:]:  # skip header
        fields = line.split("\t")
        if len(fields) < 12:
            continue
        level, _page, block, par, line_num, word_num, left, top, w, h, conf, text = fields[:12]
        text = text.strip()
        if level != "5" or not text:
            continue
        try:
            conf_f = float(conf)
        except ValueError:
            continue
        if conf_f < _MIN_WORD_CONF:
            continue
        try:
            boxes.append({
                "text": text,
                "left": int(left) // scale,
                "top": int(top) // scale,
                "width": int(w) // scale,
                "height": int(h) // scale,
                "block": block, "par": par, "line": line_num, "word": int(word_num),
            })
        except ValueError:
            continue
    return boxes


def _match_landmarks(word_boxes: list[dict]) -> list[tuple[str, float, float]]:
    """Match single words and adjacent-word phrases against the gazetteer.

    Returns (name, pixel_x, pixel_y) for the highest-confidence span per
    matched landmark name (a name may legitimately be printed once; if it
    somehow matches twice, only the first occurrence found is kept — better
    to under-use a duplicate than let it silently corrupt the pixel fit).
    """
    by_line: dict[tuple[str, str, str], list[dict]] = {}
    for box in word_boxes:
        key = (box["block"], box["par"], box["line"])
        by_line.setdefault(key, []).append(box)

    matched: dict[str, tuple[float, float]] = {}
    for boxes in by_line.values():
        boxes = sorted(boxes, key=lambda b: b["word"])
        for start in range(len(boxes)):
            for span in range(1, min(_MAX_PHRASE_WORDS, len(boxes) - start) + 1):
                span_boxes = boxes[start:start + span]
                phrase = _normalize_label(" ".join(b["text"] for b in span_boxes))
                if not phrase or phrase not in PRECISE_PLACES:
                    continue
                if phrase in matched:
                    continue
                left = min(b["left"] for b in span_boxes)
                top = min(b["top"] for b in span_boxes)
                right = max(b["left"] + b["width"] for b in span_boxes)
                bottom = max(b["top"] + b["height"] for b in span_boxes)
                matched[phrase] = ((left + right) / 2, (top + bottom) / 2)

    return [(name, px, py) for name, (px, py) in matched.items()]


def _fit_axis(pixel_values: list[float], geo_values: list[float]) -> Optional[tuple[float, float]]:
    """Least-squares pixel = slope*geo + intercept; None if geo values don't spread."""
    if max(geo_values) - min(geo_values) < 1e-6:
        return None
    import numpy as np

    slope, intercept = np.polyfit(geo_values, pixel_values, 1)
    return float(slope), float(intercept)


def geolocate_pin_from_image(payload: bytes, *, executable: Optional[str] = None) -> Optional[tuple[float, float]]:
    """Best-effort: recover the pin's real-world position from a plain map
    screenshot with no printed coordinates, using visible place labels as
    calibration points. Returns None on any missing precondition."""
    command = executable or shutil.which("tesseract")
    if not command:
        return None

    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 25_000_000
    try:
        with Image.open(io.BytesIO(payload)) as source:
            image = ImageOps.exif_transpose(source)
            pin = _detect_marker_pixel(image)
            if pin is None:
                return None
            word_boxes = _ocr_word_boxes(image, executable=command)
    except Exception:
        return None

    landmarks = _match_landmarks(word_boxes)
    if len(landmarks) < _MIN_LANDMARK_MATCHES:
        return None

    pixel_xs = [px for _, px, _ in landmarks]
    pixel_ys = [py for _, _, py in landmarks]
    lons = [PRECISE_PLACES[name][1] for name, _, _ in landmarks]
    lats = [PRECISE_PLACES[name][0] for name, _, _ in landmarks]

    if max(pixel_xs) - min(pixel_xs) < _MIN_PIXEL_SPREAD or max(pixel_ys) - min(pixel_ys) < _MIN_PIXEL_SPREAD:
        return None

    x_fit = _fit_axis(pixel_xs, lons)
    y_fit = _fit_axis(pixel_ys, lats)
    if x_fit is None or y_fit is None:
        return None

    slope_x, intercept_x = x_fit
    slope_y, intercept_y = y_fit
    if abs(slope_x) < 1e-9 or abs(slope_y) < 1e-9:
        return None

    pin_x, pin_y = pin
    lon = (pin_x - intercept_x) / slope_x
    lat = (pin_y - intercept_y) / slope_y

    # Refuse to extrapolate far past the region the landmarks actually cover,
    # and refuse anything outside the plausible operating theatre entirely.
    x_span = max(pixel_xs) - min(pixel_xs)
    y_span = max(pixel_ys) - min(pixel_ys)
    if not (min(pixel_xs) - _EXTRAPOLATION_FACTOR * x_span <= pin_x <= max(pixel_xs) + _EXTRAPOLATION_FACTOR * x_span):
        return None
    if not (min(pixel_ys) - _EXTRAPOLATION_FACTOR * y_span <= pin_y <= max(pixel_ys) + _EXTRAPOLATION_FACTOR * y_span):
        return None
    if not (_LAT_RANGE[0] <= lat <= _LAT_RANGE[1] and _LON_RANGE[0] <= lon <= _LON_RANGE[1]):
        return None

    return round(lat, 5), round(lon, 5)
