import json

import pytest

from core.radio.multichannel_plan import MARITIME_CHANNEL_TARGETS, configure_opt_in_channels
from core.radio.provider import ReceiverCapability
from core.radio.registry import ReceiverDescriptor


def receiver(name, lineage, *, terms="allowed", bands=(100_000, 30_000_000), modes=("usb", "am")):
    return ReceiverDescriptor(
        provider="kiwisdr", receiver_id=name,
        frontend_url=f"https://{name}.example.org",
        physical_lineage=lineage,
        capabilities=(ReceiverCapability(*bands, modes),),
        source_terms="operator approved" if terms == "allowed" else "",
        terms_status=terms,
        channel_kind="monitor", frequency_hz=2_187_500, mode="usb",
    )


def manifest(*items):
    return json.dumps(list(items))


def assignment(name, kind, hz, **kwargs):
    return {"receiver_id": name, "channel_kind": kind, "frequency_hz": hz,
            "operator_authorized": True, **kwargs}


def test_contract_has_six_mfhf_dsc_and_two_mf_navtex_not_vhf():
    assert len(MARITIME_CHANNEL_TARGETS) == 8
    assert MARITIME_CHANNEL_TARGETS[("dsc", 8_414_500)] == "usb"
    assert MARITIME_CHANNEL_TARGETS[("navtex", 518_000)] == "am"
    assert ("dsc", 156_525_000) not in MARITIME_CHANNEL_TARGETS


def test_opt_in_can_allocate_distinct_consented_devices_across_channels():
    available = [receiver("cagliari", "lineage_cagliari"), receiver("thess", "lineage_thess")]
    output = configure_opt_in_channels(available, manifest(
        assignment("cagliari", "dsc", 8_414_500),
        assignment("thess", "navtex", 518_000),
    ))
    assert [(row.receiver_id, row.channel_kind, row.frequency_hz, row.mode)
            for row in output] == [
                ("cagliari", "dsc", 8_414_500, "usb"),
                ("thess", "navtex", 518_000, "am"),
            ]
    assert available[0].frequency_hz == 2_187_500


@pytest.mark.parametrize("data", [
    manifest({"receiver_id": "cagliari", "channel_kind": "dsc", "frequency_hz": 8_414_500}),
    manifest(assignment("missing", "dsc", 8_414_500)),
    manifest(assignment("cagliari", "dsc", 156_525_000)),
    manifest(assignment("cagliari", "navtex", 4_209_500)),
    manifest(assignment("cagliari", "dsc", 8_414_500),
             assignment("cagliari", "navtex", 518_000)),
    "not json",
])
def test_multichannel_rejects_unsafe_or_unsupported_assignments(data):
    with pytest.raises(ValueError):
        configure_opt_in_channels([receiver("cagliari", "one")], data)


def test_multichannel_rejects_unapproved_or_wrong_band():
    with pytest.raises(ValueError):
        configure_opt_in_channels([receiver("cagliari", "one", terms="unknown")],
                                   manifest(assignment("cagliari", "dsc", 8_414_500)))
    with pytest.raises(ValueError):
        configure_opt_in_channels([receiver("vlf", "two", bands=(0, 1_000_000), modes=("am",))],
                                   manifest(assignment("vlf", "dsc", 8_414_500)))


def test_multichannel_deduplicates_physical_hardware_not_url():
    with pytest.raises(ValueError):
        configure_opt_in_channels(
            [receiver("ea3hru_1", "shared"), receiver("ea3hru_2", "shared")],
            manifest(assignment("ea3hru_1", "dsc", 8_414_500),
                     assignment("ea3hru_2", "dsc", 4_207_500)),
        )
