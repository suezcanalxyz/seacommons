# SPDX-License-Identifier: AGPL-3.0-or-later
"""MF/HF DSC tuning contract for generic SSB web receivers."""
from __future__ import annotations

HF_DSC_ASSIGNED_FREQUENCIES_HZ = frozenset({
    2_187_500,
    4_207_500,
    6_312_000,
    8_414_500,
    12_577_000,
    16_804_500,
})

DSC_AUDIO_CENTER_HZ = 1_700
DSC_MARK_HZ = 1_615
DSC_SPACE_HZ = 1_785
DSC_BAUD = 100


def receiver_carrier_hz(assigned_frequency_hz: int, mode: str) -> int:
    """Return the SDR dial frequency, not the nominal DSC channel label.

    For a conventional USB SDR receiver the MF/HF DSC RF components are
    centred around the nominal DSC channel (+/- 85 Hz). The demodulator
    needs its USB reference 1700 Hz *below* that RF centre so that the
    decoded audio contains the expected 1615/1785 Hz AFSK pair. Keep the
    nominal frequency on all observations, evidence, and public labels.

    Only documented MF/HF DSC channels in USB mode are corrected. Other
    applications (NAVTEX AM, non-DSC, etc.) must not be retuned silently.
    """
    assigned = int(assigned_frequency_hz)
    if assigned in HF_DSC_ASSIGNED_FREQUENCIES_HZ and str(mode).strip().lower() == "usb":
        return assigned - DSC_AUDIO_CENTER_HZ
    return assigned
