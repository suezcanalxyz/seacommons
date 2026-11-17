"""Safety and synthetic pixel tests for experimental SAR chip analysis."""
import numpy as np
import pytest
from tifffile import imwrite

from core.intel.sar_chip_analysis import analyze_amplitude_chip, analyze_local_tiff_chip


def test_bright_multpixel_scatterer_detected_but_not_called_a_vessel():
    rng = np.random.default_rng(20261029)
    chip = rng.normal(1.0, 0.04, (128, 128)).astype(np.float32)
    chip[60:64, 80:84] = 25.0
    result = analyze_amplitude_chip(chip, scene_id="synthetic-S1")
    assert result["scene_id"] == "synthetic-S1"
    assert result["analysis_level"] == "pixel_chip_unverified"
    assert result["georeferenced"] is False
    assert result["confirmed_vessel"] is False
    assert result["candidate_bright_scatterers"]
    assert any(60 <= t["row"] <= 64 and 80 <= t["col"] <= 84 for t in result["candidate_bright_scatterers"])
    assert all(t["classification"] == "unverified_bright_scatterer" for t in result["candidate_bright_scatterers"])
    assert all("lat" not in t and "lon" not in t for t in result["candidate_bright_scatterers"])


def test_flat_water_produces_no_bright_scatterers():
    result = analyze_amplitude_chip(np.ones((96, 96), dtype=np.float32))
    assert result["candidate_bright_scatterers"] == []


def test_single_pixel_spike_is_not_accepted_as_target():
    chip = np.ones((96, 96), dtype=np.float32)
    chip[50, 50] = 100.0
    assert analyze_amplitude_chip(chip)["candidate_bright_scatterers"] == []


def test_invalid_or_oversized_chip_is_rejected():
    with pytest.raises(ValueError, match="bounded"):
        analyze_amplitude_chip(np.ones((1025, 1025), dtype=np.float32))
    with pytest.raises(ValueError, match="insufficient"):
        analyze_amplitude_chip(np.full((64, 64), np.nan, dtype=np.float32))
    with pytest.raises(ValueError, match="2D"):
        analyze_amplitude_chip(np.ones((32, 32, 3), dtype=np.float32))


def test_local_single_band_tiff_is_actually_read_and_analyzed(tmp_path):
    chip = np.ones((96, 96), dtype=np.float32)
    chip[40:45, 50:55] = 30.0
    path = tmp_path / "sar_chip.tiff"
    imwrite(path, chip)
    result = analyze_local_tiff_chip(path, scene_id="synthetic-tiff")
    assert result["scene_id"] == "synthetic-tiff"
    assert result["candidate_bright_scatterers"]
