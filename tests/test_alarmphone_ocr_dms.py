"""Regression: Alarm Phone's 13 Oct 2026 Limnos map label mis-OCRs seconds quote as degree."""
from core.intel.x_media_utils import _parse_ocr_coordinate


def test_dms_seconds_quote_read_as_degree():
    assert _parse_ocr_coordinate("39°57'51.1°N\n25°38'53.8'E") == (39.964194, 25.648278)


def test_dms_corrected_format_still_valid():
    assert _parse_ocr_coordinate('39°57\'51.1"N 25°38\'53.8"E') == (39.964194, 25.648278)


def test_isolated_degree_label_not_repaired_as_seconds():
    assert _parse_ocr_coordinate("39°N 25°E") == (39.0, 25.0)
