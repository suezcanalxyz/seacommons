from __future__ import annotations

import json

import pytest

from core.radio.provider import ReceiverCapability


def _capability() -> ReceiverCapability:
    return ReceiverCapability(
        frequency_min_hz=100_000,
        frequency_max_hz=30_000_000,
        modes=("am", "usb"),
    )


def _descriptor(
    *,
    provider: str = "kiwisdr",
    frontend_url: str = "https://rx.example/",
    physical_lineage: str = "site-rx-1",
    enabled: bool = True,
    terms_status: str = "allowed",
):
    from core.radio.registry import ReceiverDescriptor

    return ReceiverDescriptor(
        provider=provider,
        frontend_url=frontend_url,
        physical_lineage=physical_lineage,
        capabilities=(_capability(),),
        source_terms="https://provider.example/terms",
        terms_status=terms_status,
        enabled=enabled,
        latitude=35.8,
        longitude=14.5,
        operator_note="configured test receiver",
    )


def test_receiver_id_is_deterministic_for_provider_and_frontend():
    from core.radio.registry import receiver_id_for

    first = receiver_id_for("Kiwi SDR", "HTTPS://RX.EXAMPLE/")
    second = receiver_id_for("kiwi-sdr", "https://rx.example")

    assert first == second
    assert first.startswith("radio_rx_kiwi_sdr_")
    assert first != receiver_id_for("openwebrx", "https://rx.example")


def test_runnable_receivers_collapse_duplicate_physical_lineage():
    from core.radio.registry import ReceiverRegistry

    kiwi = _descriptor(frontend_url="https://kiwi.example", physical_lineage="shared-rx")
    openwebrx = _descriptor(
        provider="openwebrx",
        frontend_url="https://owrx.example",
        physical_lineage="shared-rx",
    )
    registry = ReceiverRegistry((kiwi, openwebrx), max_receivers=4)

    assert len(registry.all()) == 2
    assert registry.runnable() == (kiwi,)
    assert kiwi.receiver_id != openwebrx.receiver_id
    assert kiwi.physical_lineage == openwebrx.physical_lineage == "shared_rx"


def test_disabled_and_unclear_terms_receivers_are_not_runnable():
    from core.radio.registry import ReceiverRegistry

    disabled = _descriptor(frontend_url="https://disabled.example", enabled=False)
    unknown_terms = _descriptor(
        frontend_url="https://unknown.example",
        physical_lineage="site-rx-2",
        terms_status="unknown",
    )
    allowed = _descriptor(
        frontend_url="https://allowed.example",
        physical_lineage="site-rx-3",
        terms_status="allowed",
    )
    registry = ReceiverRegistry((disabled, unknown_terms, allowed), max_receivers=4)

    assert registry.runnable() == (allowed,)


def test_registry_rejects_configured_receiver_count_above_bound():
    from core.radio.registry import ReceiverRegistry

    descriptors = tuple(
        _descriptor(
            frontend_url=f"https://rx-{index}.example",
            physical_lineage=f"rx-{index}",
        )
        for index in range(3)
    )

    with pytest.raises(ValueError, match="maximum"):
        ReceiverRegistry(descriptors, max_receivers=2)


def test_inline_json_and_file_loading_are_explicit_and_bounded(tmp_path):
    from core.radio.registry import load_receiver_descriptors

    payload = [
        {
            "provider": "kiwisdr",
            "frontend_url": "https://rx.example",
            "physical_lineage": "central-med-rx",
            "capabilities": [
                {
                    "frequency_min_hz": 100000,
                    "frequency_max_hz": 30000000,
                    "modes": ["am", "usb"],
                }
            ],
            "source_terms": "https://provider.example/terms",
            "terms_status": "allowed",
            "enabled": True,
        }
    ]
    inline = load_receiver_descriptors(raw_json=json.dumps(payload), max_receivers=2)
    assert len(inline.all()) == 1

    config_file = tmp_path / "receivers.json"
    config_file.write_text(json.dumps(payload))
    from_file = load_receiver_descriptors(file_path=str(config_file), max_receivers=2)
    assert from_file.all() == inline.all()

    with pytest.raises(ValueError, match="either"):
        load_receiver_descriptors(
            raw_json=json.dumps(payload),
            file_path=str(config_file),
            max_receivers=2,
        )
