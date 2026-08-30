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
_LAT_RANGE = (20.0, 48.0)
_LON_RANGE = (-12.0, 42.0)
# A distress pin routinely sits hundreds of km out at sea from the nearest
# labelled coastal town (that's the whole point of "boat spotted south of
# Crete" reports), so this guards against a genuinely wrong landmark match
# (OCR misread / wrong instance of an ambiguous name) rather than against
# normal, expected extrapolation distance.
_MAX_KM_FROM_NEAREST_LANDMARK = 600.0
_EARTH_RADIUS_KM = 6371.0

_PLACES_SORTED = sorted(PRECISE_PLACES.items(), key=lambda kv: -len(kv[0]))
_MAX_PHRASE_WORDS = max((len(name.split()) for name in PRECISE_PLACES), default=1)


def _normalize_label(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z ]", "", stripped.lower()).strip()


def _blob_from_mask(mask, width: int, height: int) -> Optional[tuple[int, int]]:
    """A single compact, isolated marker blob from a boolean mask; its tip."""
    import numpy as np

    count = int(mask.sum())
    if count < 10 or count > 0.02 * width * height:
        return None
    ys, xs = np.nonzero(mask)
    box_w = int(xs.max() - xs.min()) + 1
    box_h = int(ys.max() - ys.min()) + 1
    # A single pin icon is small and compact; a large/sparse bounding box
    # means multiple unrelated elements were picked up.
    if box_w > 0.1 * width or box_h > 0.14 * height:
        return None
    # Fill ratio: a real marker fills a good fraction of its bounding box;
    # scattered specks do not.
    if count < 0.20 * box_w * box_h:
        return None
    center_x = int(round(float(xs.mean())))
    # Circular incident markers encode their position at the centre; a tall
    # teardrop pin encodes it at the bottom tip.
    aspect = box_h / max(1, box_w)
    tip_y = int(round(float(ys.mean()))) if 0.8 <= aspect <= 1.25 else int(ys.max())
    return center_x, tip_y


def _detect_marker_pixel(image) -> Optional[tuple[int, int]]:
    """Find a single compact drop-pin / circle marker; None if none/ambiguous.

    Alarm Phone's map screenshots come from several tools, so the marker is
    not always Google-red. Try, in order: the classic map red, then a
    high-saturation blue and an amber/orange marker, then a dark
    high-contrast teardrop. Each candidate must still be small, compact and
    isolated (see _blob_from_mask) so a basemap accent can't pass.
    """
    import numpy as np

    rgb = image.convert("RGB")
    pixels = np.asarray(rgb)
    r = pixels[:, :, 0].astype(int)
    g = pixels[:, :, 1].astype(int)
    b = pixels[:, :, 2].astype(int)
    height, width = r.shape

    for mask in (
        # classic map-pin red
        (r > 150) & (g < 110) & (b < 110) & (r - g > 60) & (r - b > 60),
        # saturated blue marker (compactness check rejects the water body)
        (b > 150) & (r < 120) & (g < 150) & (b - r > 55) & (b - g > 25),
        # amber / orange marker
        (r > 180) & (g > 90) & (g < 190) & (b < 100) & (r - b > 90) & (r - g > 25),
        # bright yellow circular incident marker
        (r > 205) & (g > 205) & (b < 135) & (r - b > 80) & (g - b > 80),
    ):
        tip = _blob_from_mask(np.asarray(mask), width, height)
        if tip is not None:
            return tip
    return None


def _ocr_pass(image, *, executable: str, block_prefix: str) -> list[dict]:
    """One tesseract TSV word-box pass over a (sub)image, in that image's
    own local pixel space (offset 0,0). `block_prefix` keeps this pass's
    (block, par, line) keys distinct from any other pass/tile so
    `_match_landmarks` never joins words across pass/tile boundaries.

    Empirically (verified against real Alarm Phone map screenshots), `--psm
    11` (sparse text) fragments scattered map labels into unusable garbage —
    treating dozens of stray coastline/road pixels as isolated "words" — no
    matter how much the image is scaled or sharpened. `--psm 6` (uniform
    text block) reads real labels ("Heraklion", "Chrisi", ...) cleanly at or
    near native resolution; a modest 2x upscale surfaces a few more without
    the artefacts that heavier scaling + sharpening introduced in testing.
    """
    from PIL import Image, ImageOps

    if image.width < 1 or image.height < 1:
        return []
    scaled = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
    scaled = ImageOps.autocontrast(scaled.convert("RGB"))
    buf = io.BytesIO()
    scaled.save(buf, format="PNG")
    scale = 2

    try:
        result = subprocess.run(
            [executable, "stdin", "stdout", "--psm", "6", "-l", "eng", "tsv"],
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
                "block": f"{block_prefix}-{block}", "par": par, "line": line_num,
                "word": int(word_num),
            })
        except ValueError:
            continue
    return boxes


def _tile_regions(width: int, height: int) -> list[tuple[int, int, int, int]]:
    """A 2x2 grid with ~15% overlap so a label straddling a naive cut line
    still lands wholly inside at least one tile."""
    half_w, half_h = width / 2, height / 2
    ow, oh = int(half_w * 0.15), int(half_h * 0.15)
    return [
        (0, 0, int(half_w) + ow, int(half_h) + oh),
        (int(half_w) - ow, 0, width, int(half_h) + oh),
        (0, int(half_h) - oh, int(half_w) + ow, height),
        (int(half_w) - ow, int(half_h) - oh, width, height),
    ]


def _ocr_word_boxes(image, *, executable: str) -> list[dict]:
    """Word-level OCR boxes (pixel-space), merged from two passes.

    A single whole-image `--psm 6` pass treats the entire screenshot as one
    text block, which — verified against real screenshots — reads a strong
    label or two cleanly but garbles most others once several spatially
    separated labels compete for one reading order. Re-running the same pass
    on four overlapping image quadrants gives each label a much smaller,
    closer-to-uniform block to be read in, recovering labels the whole-image
    pass missed; results are merged (duplicates across tiles are harmless —
    `_match_landmarks` just keeps the first per name).
    """
    boxes = _ocr_pass(image, executable=executable, block_prefix="full")
    for index, (left, top, right, bottom) in enumerate(_tile_regions(image.width, image.height)):
        tile = image.crop((left, top, right, bottom))
        tile_boxes = _ocr_pass(tile, executable=executable, block_prefix=f"tile{index}")
        for box in tile_boxes:
            box["left"] += left
            box["top"] += top
        boxes.extend(tile_boxes)
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


def _drop_worst_landmark(
    landmarks: list[tuple[str, float, float]],
) -> list[tuple[str, float, float]]:
    """Drop one landmark if its pixel position is a clear outlier against a
    linear pixel<->geo fit of the rest; otherwise keep them all."""
    import numpy as np

    names = [n for n, _, _ in landmarks]
    px = np.array([x for _, x, _ in landmarks])
    py = np.array([y for _, _, y in landmarks])
    lon = np.array([PRECISE_PLACES[n][1] for n in names])
    lat = np.array([PRECISE_PLACES[n][0] for n in names])

    residuals: list[float] = []
    for i in range(len(landmarks)):
        keep = [j for j in range(len(landmarks)) if j != i]
        if np.ptp(lon[keep]) < 1e-6 or np.ptp(lat[keep]) < 1e-6:
            return landmarks
        sx, ix = np.polyfit(lon[keep], px[keep], 1)
        sy, iy = np.polyfit(lat[keep], py[keep], 1)
        residuals.append(
            float(abs(px[i] - (sx * lon[i] + ix)) + abs(py[i] - (sy * lat[i] + iy)))
        )

    worst = int(np.argmax(residuals))
    others = [residuals[j] for j in range(len(residuals)) if j != worst]
    median_other = float(np.median(others)) if others else 0.0
    if residuals[worst] > max(25.0, 3.0 * median_other):
        return [lm for j, lm in enumerate(landmarks) if j != worst]
    return landmarks


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _fit_axis(pixel_values: list[float], geo_values: list[float]) -> Optional[tuple[float, float]]:
    """Least-squares pixel = slope*geo + intercept; None if geo values don't spread."""
    if max(geo_values) - min(geo_values) < 1e-6:
        return None
    import numpy as np

    slope, intercept = np.polyfit(geo_values, pixel_values, 1)
    return float(slope), float(intercept)


def geolocate_pin_from_image(
    payload: bytes,
    *,
    executable: Optional[str] = None,
    word_boxes: Optional[list[dict]] = None,
) -> Optional[tuple[float, float]]:
    """Best-effort: recover the pin's real-world position from a plain map
    screenshot with no printed coordinates, using visible place labels as
    calibration points. Returns None on any missing precondition."""
    command = executable or shutil.which("tesseract")
    if not command and not word_boxes:
        return None

    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 25_000_000
    try:
        with Image.open(io.BytesIO(payload)) as source:
            image = ImageOps.exif_transpose(source)
            pin = _detect_marker_pixel(image)
            if pin is None:
                return None
            detected_word_boxes = word_boxes or _ocr_word_boxes(image, executable=command)
    except Exception:
        return None

    landmarks = _match_landmarks(detected_word_boxes)
    if len(landmarks) < _MIN_LANDMARK_MATCHES:
        return None

    # Robust to one OCR-misplaced label: with >= 4 matches, drop the single
    # landmark whose position is the worst fit if it is a clear outlier.
    if len(landmarks) >= 4:
        landmarks = _drop_worst_landmark(landmarks)

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

    if not (_LAT_RANGE[0] <= lat <= _LAT_RANGE[1] and _LON_RANGE[0] <= lon <= _LON_RANGE[1]):
        return None
    nearest_km = min(
        _haversine_km(lat, lon, PRECISE_PLACES[name][0], PRECISE_PLACES[name][1])
        for name, _, _ in landmarks
    )
    if nearest_km > _MAX_KM_FROM_NEAREST_LANDMARK:
        return None

    # A linear pixel->geo fit off a handful of place labels can put the pin a
    # few km inland; the boat is at sea, so nudge onto water.
    from core.intel.landmask import nearest_sea_point

    return nearest_sea_point(round(lat, 5), round(lon, 5))
