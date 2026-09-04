# SPDX-License-Identifier: AGPL-3.0-or-later
"""Synthetic Alarm Phone map/screenshot fixtures with ground truth.

`docs/prompt.md` sections 11 and 13 ask for a controlled evaluation set that
covers the real shapes Alarm Phone posts take -- a coordinate popup, tiny
coordinate text, a dark popup, a quoted-tweet map, coloured drop pins, a map
with only place labels, an image with unrelated numbers, a map without enough
landmarks, a low-resolution preview, and a label that OCRs to the wrong
place. Committing third-party screenshots is a licensing problem
(`docs/prompt.md` section 11), so these are rendered programmatically with
Pillow and are fully deterministic.

Each `Case` carries the ground truth the benchmark needs: the image type,
whether a printed coordinate / pin is present, the expected coordinate and a
km tolerance. Map cases place their town labels and pin at pixel positions
derived from a real Web-Mercator projection of a chosen bbox, so a correct
geolocator recovers the pin and an incorrect (linear) one does not.
"""
from __future__ import annotations

import io
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

_FONT_REGULAR = "DejaVuSans.ttf"
_FONT_BOLD = "DejaVuSans-Bold.ttf"
_FONT_MONO = "DejaVuSansMono.ttf"

ImageKind = Literal["map_screenshot", "text_card", "infographic", "photo", "unknown"]


# ── Web Mercator (the projection every slippy map uses) ──────────────────────
def _merc_x(lon: float) -> float:
    return math.radians(lon)


def _merc_y(lat: float) -> float:
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


@dataclass(frozen=True)
class _Viewport:
    """A geographic bbox mapped to a pixel canvas, north-up, Mercator."""

    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    width: int
    height: int

    def to_pixel(self, lat: float, lon: float) -> tuple[int, int]:
        x0, x1 = _merc_x(self.lon_min), _merc_x(self.lon_max)
        y0, y1 = _merc_y(self.lat_max), _merc_y(self.lat_min)  # y grows downward
        px = (_merc_x(lon) - x0) / (x1 - x0) * self.width
        py = (_merc_y(lat) - y0) / (y1 - y0) * self.height
        return round(px), round(py)


@dataclass(frozen=True)
class Case:
    name: str
    image_kind: ImageKind
    has_coordinate_text: bool
    has_pin: bool
    expected_coordinate: tuple[float, float] | None  # (lat, lon)
    tolerance_km: float
    render: Callable[[], bytes] = field(repr=False)
    pin_color: str | None = None
    quoted_tweet: bool = False
    notes: str = ""

    def as_ground_truth(self) -> dict:
        return {
            "name": self.name,
            "image_kind": self.image_kind,
            "has_coordinate_text": self.has_coordinate_text,
            "has_pin": self.has_pin,
            "expected_coordinate": list(self.expected_coordinate)
            if self.expected_coordinate
            else None,
            "tolerance_km": self.tolerance_km,
            "pin_color": self.pin_color,
            "quoted_tweet": self.quoted_tweet,
            "notes": self.notes,
        }


def _font(name: str, size: int):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(name, size)
    except OSError:  # pragma: no cover - Pillow always ships DejaVu
        return ImageFont.load_default()


def _basemap(width: int, height: int, *, sea: bool = True):
    """A plausible slippy-map background: pale land, blue sea band, a few
    coastline strokes and grid lines so OCR/pin detection see realistic
    clutter rather than a flat colour."""
    from PIL import Image, ImageDraw

    land = (233, 229, 220)
    image = Image.new("RGB", (width, height), land)
    draw = ImageDraw.Draw(image)
    if sea:
        draw.rectangle([0, int(height * 0.45), width, height], fill=(168, 204, 226))
        draw.line(
            [(0, int(height * 0.45)), (width, int(height * 0.42))],
            fill=(120, 150, 170),
            width=3,
        )
    for gx in range(0, width, 90):
        draw.line([(gx, 0), (gx, height)], fill=(214, 210, 201), width=1)
    for gy in range(0, height, 90):
        draw.line([(0, gy), (width, gy)], fill=(214, 210, 201), width=1)
    for rx in range(40, width, 160):
        draw.line([(rx, 20), (rx + 70, height - 30)], fill=(206, 190, 170), width=2)
    return image, draw


def _draw_pin(draw, x: int, y: int, color: tuple[int, int, int]) -> None:
    """A teardrop drop-pin whose tip is exactly (x, y)."""
    for dy in range(26):
        half = max(1, int((26 - dy) * 0.55))
        draw.line([(x - half, y - dy), (x + half, y - dy)], fill=color)
    draw.ellipse([x - 6, y - 34, x + 6, y - 22], fill=(255, 255, 255))


def _to_png(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ── Coordinate-popup cases ──────────────────────────────────────────────────
def _render_coordinate_popup(
    text: str,
    *,
    width: int = 900,
    height: int = 640,
    dark: bool = False,
    font_size: int = 30,
) -> bytes:
    from PIL import ImageOps

    image, draw = _basemap(width, height)
    _draw_pin(draw, int(width * 0.52), int(height * 0.60), (211, 47, 47))
    box_w, box_h = int(width * 0.66), 92
    bx, by = (width - box_w) // 2, 26
    bg = (28, 30, 34) if dark else (255, 255, 255)
    fg = (238, 238, 238) if dark else (24, 24, 24)
    draw.rectangle([bx, by, bx + box_w, by + box_h], fill=bg, outline=(90, 90, 90), width=2)
    draw.text((bx + 18, by + 14), "Position", font=_font(_FONT_BOLD, 20), fill=fg)
    draw.text((bx + 18, by + 44), text, font=_font(_FONT_MONO, font_size), fill=fg)
    if dark:  # Alarm Phone dark-mode cards need an inverted pass to be legible
        return _to_png(image)
    return _to_png(ImageOps.autocontrast(image))


def _render_text_card(lines: list[str], *, width: int = 820, height: int = 520) -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (width, height), (250, 249, 246))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, 8], fill=(211, 47, 47))
    draw.text((36, 34), "ALARM PHONE", font=_font(_FONT_BOLD, 26), fill=(180, 30, 30))
    y = 96
    for line in lines:
        draw.text((36, y), line, font=_font(_FONT_REGULAR, 24), fill=(28, 28, 28))
        y += 44
    return _to_png(image)


# ── Landmark map cases (geometrically consistent) ────────────────────────────
# A Central-Med viewport with towns the gazetteer knows (geoextract.PRECISE_PLACES).
_LANDMARKS = {
    "Lampedusa": (35.50, 12.60),
    "Linosa": (35.87, 12.86),
    "Lampione": (35.53, 12.32),
    "Malta": (35.90, 14.51),
    "Pozzallo": (36.73, 14.85),
}
_MAP_VIEWPORT = _Viewport(
    lat_min=34.2, lat_max=37.1, lon_min=11.4, lon_max=15.2, width=960, height=720
)


def _render_landmark_map(
    *,
    pin_latlon: tuple[float, float] | None,
    pin_color_name: str = "red",
    labels: list[str] | None = None,
    corrupt_label: tuple[str, str] | None = None,
    width: int | None = None,
    height: int | None = None,
) -> bytes:
    viewport = _MAP_VIEWPORT
    if width or height:
        viewport = _Viewport(
            viewport.lat_min,
            viewport.lat_max,
            viewport.lon_min,
            viewport.lon_max,
            width or viewport.width,
            height or viewport.height,
        )
    image, draw = _basemap(viewport.width, viewport.height)
    names = labels if labels is not None else list(_LANDMARKS)
    label_font = _font(_FONT_BOLD, 22)
    for name in names:
        lat, lon = _LANDMARKS[name]
        px, py = viewport.to_pixel(lat, lon)
        draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(70, 70, 70))
        shown = name
        if corrupt_label and corrupt_label[0] == name:
            shown = corrupt_label[1]
        draw.text((px + 8, py - 12), shown, font=label_font, fill=(40, 40, 40))
    colors = {
        "red": (211, 47, 47),
        "blue": (33, 118, 232),
        "yellow": (247, 220, 40),
        "amber": (240, 150, 30),
    }
    if pin_latlon is not None:
        px, py = viewport.to_pixel(*pin_latlon)
        if pin_color_name == "yellow":  # a circular incident marker, not a teardrop
            draw.ellipse([px - 13, py - 13, px + 13, py + 13], fill=colors["yellow"])
            draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(120, 100, 0))
        else:
            _draw_pin(draw, px, py, colors[pin_color_name])
    return _to_png(image)


def _render_unrelated_numbers_map() -> bytes:
    image, draw = _basemap(900, 640)
    _draw_pin(draw, 470, 380, (211, 47, 47))
    draw.rectangle([30, 590, 190, 610], outline=(20, 20, 20), width=2)
    draw.text((36, 588), "0        50 km", font=_font(_FONT_REGULAR, 16), fill=(20, 20, 20))
    draw.text((640, 120), "1247", font=_font(_FONT_REGULAR, 18), fill=(60, 90, 120))  # depth
    draw.text((300, 60), "Zoom 8  ·  2026", font=_font(_FONT_REGULAR, 16), fill=(90, 90, 90))
    return _to_png(image)


# ── The committed case set ──────────────────────────────────────────────────
# Pin ground truth: a point in the sea south-west of Lampedusa, inside the
# viewport, ~40 km from the nearest labelled landmark.
_PIN_LATLON = (35.02, 12.18)

CASES: list[Case] = [
    Case(
        name="coordinate_popup_dmm",
        image_kind="map_screenshot",
        has_coordinate_text=True,
        has_pin=True,
        expected_coordinate=(34.271533, 11.9423),
        tolerance_km=1.0,
        render=lambda: _render_coordinate_popup("N 34\u00b0 16.292'  E 011\u00b0 56.538'"),
        pin_color="red",
        notes="Degrees-decimal-minutes, the most common Alarm Phone popup format.",
    ),
    Case(
        name="coordinate_popup_dms",
        image_kind="map_screenshot",
        has_coordinate_text=True,
        has_pin=True,
        expected_coordinate=(37.308694, 27.164194),
        tolerance_km=1.0,
        render=lambda: _render_coordinate_popup("37\u00b018'31.3\"N  27\u00b009'51.1\"E"),
        pin_color="red",
        notes="Degrees-minutes-seconds with hemisphere suffix.",
    ),
    Case(
        name="coordinate_popup_tiny_text",
        image_kind="map_screenshot",
        has_coordinate_text=True,
        has_pin=True,
        expected_coordinate=(33.877733, 13.175917),
        tolerance_km=1.5,
        render=lambda: _render_coordinate_popup(
            "N 33\u00b052.664'  E 013\u00b010.555'", font_size=13
        ),
        pin_color="red",
        notes="Small coordinate row -- needs ROI upscale to read.",
    ),
    Case(
        name="coordinate_popup_dark",
        image_kind="map_screenshot",
        has_coordinate_text=True,
        has_pin=True,
        expected_coordinate=(41.552528, 26.526972),
        tolerance_km=1.5,
        render=lambda: _render_coordinate_popup("41\u00b033'09.1\"N  26\u00b031'37.1\"E", dark=True),
        pin_color="red",
        notes="Dark popup, light text -- needs an inverted / high-contrast pass.",
    ),
    Case(
        name="coordinate_popup_quoted_tweet",
        image_kind="map_screenshot",
        has_coordinate_text=True,
        has_pin=True,
        expected_coordinate=(34.271533, 11.9423),
        tolerance_km=1.0,
        render=lambda: _render_coordinate_popup("N 34\u00b0 16.292'  E 011\u00b0 56.538'"),
        pin_color="red",
        quoted_tweet=True,
        notes="Same image but attached to the quoted tweet, not the caption's.",
    ),
    Case(
        name="pin_only_red",
        image_kind="map_screenshot",
        has_coordinate_text=False,
        has_pin=True,
        expected_coordinate=_PIN_LATLON,
        tolerance_km=25.0,
        render=lambda: _render_landmark_map(pin_latlon=_PIN_LATLON, pin_color_name="red"),
        pin_color="red",
        notes="No printed coordinate -- must geolocate from the pin + labels, approximate.",
    ),
    Case(
        name="pin_only_blue",
        image_kind="map_screenshot",
        has_coordinate_text=False,
        has_pin=True,
        expected_coordinate=_PIN_LATLON,
        tolerance_km=25.0,
        render=lambda: _render_landmark_map(pin_latlon=_PIN_LATLON, pin_color_name="blue"),
        pin_color="blue",
        notes="Blue marker -- the colour-mask detector must not confuse it with the sea.",
    ),
    Case(
        name="pin_only_yellow_circle",
        image_kind="map_screenshot",
        has_coordinate_text=False,
        has_pin=True,
        expected_coordinate=_PIN_LATLON,
        tolerance_km=25.0,
        render=lambda: _render_landmark_map(
            pin_latlon=_PIN_LATLON, pin_color_name="yellow"
        ),
        pin_color="yellow",
        notes="Circular incident marker -- position is the centre, not a tip.",
    ),
    Case(
        name="pin_with_three_labels",
        image_kind="map_screenshot",
        has_coordinate_text=False,
        has_pin=True,
        expected_coordinate=_PIN_LATLON,
        tolerance_km=25.0,
        render=lambda: _render_landmark_map(
            pin_latlon=_PIN_LATLON,
            pin_color_name="red",
            labels=["Lampedusa", "Malta", "Pozzallo"],
        ),
        pin_color="red",
        notes="Exactly three usable landmarks -- the minimum for a confident fit.",
    ),
    Case(
        name="pin_insufficient_landmarks",
        image_kind="map_screenshot",
        has_coordinate_text=False,
        has_pin=True,
        expected_coordinate=None,
        tolerance_km=0.0,
        render=lambda: _render_landmark_map(
            pin_latlon=_PIN_LATLON, pin_color_name="red", labels=["Lampedusa"]
        ),
        pin_color="red",
        notes="Only one label -- must return no coordinate (fail closed), not a guess.",
    ),
    Case(
        name="pin_with_misread_label",
        image_kind="map_screenshot",
        has_coordinate_text=False,
        has_pin=True,
        expected_coordinate=_PIN_LATLON,
        tolerance_km=30.0,
        render=lambda: _render_landmark_map(
            pin_latlon=_PIN_LATLON,
            pin_color_name="red",
            corrupt_label=("Linosa", "Limassol"),
        ),
        pin_color="red",
        notes="One label OCRs to a wrong far-away place -- RANSAC must drop it.",
    ),
    Case(
        name="unrelated_numbers_no_coordinate",
        image_kind="map_screenshot",
        has_coordinate_text=False,
        has_pin=True,
        expected_coordinate=None,
        tolerance_km=0.0,
        render=_render_unrelated_numbers_map,
        pin_color="red",
        notes="Scale bar '50 km' and a depth sounding must not parse as a position.",
    ),
    Case(
        name="low_res_preview_popup",
        image_kind="map_screenshot",
        has_coordinate_text=True,
        has_pin=True,
        expected_coordinate=(34.271533, 11.9423),
        tolerance_km=2.0,
        render=lambda: _render_coordinate_popup(
            "N 34\u00b0 16.292'  E 011\u00b0 56.538'", width=380, height=260, font_size=11
        ),
        pin_color="red",
        notes="A 380px card thumbnail -- the live path must fetch a larger render first.",
    ),
    Case(
        name="text_card_people_and_condition",
        image_kind="text_card",
        has_coordinate_text=False,
        has_pin=False,
        expected_coordinate=None,
        tolerance_km=0.0,
        render=lambda: _render_text_card(
            [
                "47 people on board, including 6 children.",
                "The engine has stopped. The boat is taking water.",
                "Central Mediterranean, position not confirmed.",
            ]
        ),
        notes="No map at all -- image text carries the head count and vessel condition.",
    ),
    Case(
        name="photo_not_a_map",
        image_kind="photo",
        has_coordinate_text=False,
        has_pin=False,
        expected_coordinate=None,
        tolerance_km=0.0,
        render=lambda: _to_png(_basemap(640, 480, sea=False)[0]),
        notes="A non-map image -- image_kind must not be map_screenshot.",
    ),
]

CASES_BY_NAME: dict[str, Case] = {case.name: case for case in CASES}


def render_case(name: str) -> bytes:
    return CASES_BY_NAME[name].render()


def ground_truth() -> list[dict]:
    return [case.as_ground_truth() for case in CASES]
