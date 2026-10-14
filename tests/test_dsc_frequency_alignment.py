from core.radio.dsc_tuning import (
    HF_DSC_ASSIGNED_FREQUENCIES_HZ, DSC_AUDIO_CENTER_HZ,
    DSC_MARK_HZ, DSC_SPACE_HZ, receiver_carrier_hz,
)


def test_every_mf_hf_dsc_usb_channel_produces_correct_afsk_tones():
    for nominal in HF_DSC_ASSIGNED_FREQUENCIES_HZ:
        tune = receiver_carrier_hz(nominal, "usb")
        assert tune == nominal - DSC_AUDIO_CENTER_HZ
        assert (nominal - 85) - tune == DSC_MARK_HZ
        assert (nominal + 85) - tune == DSC_SPACE_HZ


def test_non_dsc_and_non_usb_tuning_remains_unchanged():
    assert receiver_carrier_hz(518000, "am") == 518000
    assert receiver_carrier_hz(156525000, "nbfm") == 156525000
    assert receiver_carrier_hz(2187500, "lsb") == 2187500
