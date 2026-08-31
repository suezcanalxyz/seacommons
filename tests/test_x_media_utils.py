# SPDX-License-Identifier: AGPL-3.0-or-later
"""EasyOCR/Tesseract cross-check in _ocr_photo (x_media_utils.py).

User follow-up ("fix humanitarian tesseract piu preciso"): EasyOCR and
Tesseract were never cross-checked against each other -- if EasyOCR found a
coordinate, Tesseract never even ran, so a wrong EasyOCR read was trusted at
face value. These tests exercise the new cross-check branching directly,
independent of how twikit_monitor.py maps its method string to metadata
(covered separately in test_twikit_monitor.py).
"""
from __future__ import annotations

import io
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from core.intel import x_media_utils


@contextmanager
def _fake_response(headers: dict, payload: bytes):
    yield SimpleNamespace(
        headers=headers,
        read=lambda *_args, **_kwargs: payload,
    )


def _patch_download(monkeypatch, payload: bytes = b"fake-image-bytes"):
    monkeypatch.setattr(
        x_media_utils.urllib.request,
        "urlopen",
        lambda *a, **k: _fake_response({"Content-Type": "image/png"}, payload),
    )


def test_ocr_photo_confirms_when_tesseract_agrees_with_easyocr(monkeypatch):
    monkeypatch.setattr(x_media_utils, "shutil", x_media_utils.shutil)
    monkeypatch.setattr(x_media_utils.shutil, "which", lambda name: "/usr/bin/tesseract")
    _patch_download(monkeypatch)
    monkeypatch.setattr(
        x_media_utils, "_easyocr_image", lambda payload: ((35.500, 24.900), [], True)
    )
    monkeypatch.setattr(
        x_media_utils, "_tesseract_cross_check", lambda payload, executable: (35.501, 24.899)
    )

    coord, attempted, method = x_media_utils._ocr_photo(
        "https://pbs.twimg.com/media/map.jpg"
    )

    assert coord == (35.500, 24.900)
    assert attempted is True
    assert method == "easyocr_tesseract_consensus"


def test_ocr_photo_flags_dispute_when_tesseract_disagrees_with_easyocr(monkeypatch):
    monkeypatch.setattr(x_media_utils.shutil, "which", lambda name: "/usr/bin/tesseract")
    _patch_download(monkeypatch)
    monkeypatch.setattr(
        x_media_utils, "_easyocr_image", lambda payload: ((35.5, 24.9), [], True)
    )
    # Materially different coordinate -- well outside the 0.03 deg tolerance.
    monkeypatch.setattr(
        x_media_utils, "_tesseract_cross_check", lambda payload, executable: (36.2, 25.6)
    )

    coord, attempted, method = x_media_utils._ocr_photo(
        "https://pbs.twimg.com/media/map.jpg"
    )

    assert coord == (35.5, 24.9)  # EasyOCR's read is kept, just flagged
    assert method == "easyocr_text_disputed"


def test_ocr_photo_keeps_legacy_method_when_tesseract_finds_nothing(monkeypatch):
    monkeypatch.setattr(x_media_utils.shutil, "which", lambda name: "/usr/bin/tesseract")
    _patch_download(monkeypatch)
    monkeypatch.setattr(
        x_media_utils, "_easyocr_image", lambda payload: ((35.5, 24.9), [], True)
    )
    monkeypatch.setattr(x_media_utils, "_tesseract_cross_check", lambda payload, executable: None)

    coord, attempted, method = x_media_utils._ocr_photo(
        "https://pbs.twimg.com/media/map.jpg"
    )

    assert coord == (35.5, 24.9)
    assert method == "easyocr_text"


def test_ocr_photo_skips_cross_check_when_tesseract_binary_missing(monkeypatch):
    monkeypatch.setattr(x_media_utils.shutil, "which", lambda name: None)
    # The initial availability guard also accepts "easyocr importable" as an
    # alternative to a tesseract binary; force that branch regardless of
    # whether the real (heavy, optional) easyocr package is installed here.
    monkeypatch.setattr(
        x_media_utils.importlib.util, "find_spec", lambda name: object() if name == "easyocr" else None
    )
    _patch_download(monkeypatch)
    monkeypatch.setattr(
        x_media_utils, "_easyocr_image", lambda payload: ((35.5, 24.9), [], True)
    )

    def _boom(*_a, **_k):
        raise AssertionError("cross-check must not run without a tesseract binary")

    monkeypatch.setattr(x_media_utils, "_tesseract_cross_check", _boom)

    coord, attempted, method = x_media_utils._ocr_photo(
        "https://pbs.twimg.com/media/map.jpg"
    )

    assert coord == (35.5, 24.9)
    assert method == "easyocr_text"


def test_ocr_photo_survives_a_broken_cross_check(monkeypatch):
    """A crash in the cross-check pass must never lose an EasyOCR read that
    already succeeded."""
    monkeypatch.setattr(x_media_utils.shutil, "which", lambda name: "/usr/bin/tesseract")
    _patch_download(monkeypatch)
    monkeypatch.setattr(
        x_media_utils, "_easyocr_image", lambda payload: ((35.5, 24.9), [], True)
    )

    def _raise(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(x_media_utils, "_tesseract_cross_check", _raise)

    coord, attempted, method = x_media_utils._ocr_photo(
        "https://pbs.twimg.com/media/map.jpg"
    )

    assert coord == (35.5, 24.9)
    assert method == "easyocr_text"
