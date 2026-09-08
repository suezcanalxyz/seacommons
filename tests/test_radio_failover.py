from core.radio.provider import ReceiverCapability
from core.radio.registry import ReceiverDescriptor


def _descriptor(receiver_id, lineage, *, kind="monitor", frequency=2_187_500, mode="usb"):
    return ReceiverDescriptor(
        receiver_id=receiver_id,
        provider="kiwisdr",
        frontend_url=f"https://{receiver_id}.example.org",
        physical_lineage=lineage,
        capabilities=(ReceiverCapability(100_000, 30_000_000, ("usb", "am")),),
        source_terms="allowed-test",
        terms_status="allowed",
        public_label=receiver_id,
        channel_kind=kind,
        frequency_hz=frequency,
        mode=mode,
    )


def test_channel_target_for_requires_explicit_frequency_and_mode():
    from core.radio.failover import ChannelTarget, channel_target_for

    explicit = _descriptor("rx-a", "lineage-a", kind="dsc")
    assert channel_target_for(explicit) == ChannelTarget("dsc", 2_187_500, "usb")

    implicit = ReceiverDescriptor(
        receiver_id="rx-b", provider="kiwisdr", frontend_url="https://rx-b.example.org",
        physical_lineage="lineage-b", capabilities=(ReceiverCapability(100_000, 30_000_000, ("usb",)),),
        source_terms="allowed-test", terms_status="allowed",
    )
    assert channel_target_for(implicit) is None


def test_build_channel_plans_preserves_rank_and_slices_replicas():
    from core.radio.failover import build_channel_plans

    rows = tuple(_descriptor(f"rx-{idx}", f"lineage-{idx}") for idx in range(5))
    plans = build_channel_plans(rows, desired_replicas=3)

    assert len(plans) == 1
    plan = plans[0]
    assert [row.receiver_id for row in plan.active] == ["rx_0", "rx_1", "rx_2"]
    assert [row.receiver_id for row in plan.standby] == ["rx_3", "rx_4"]
    assert plan.desired_replicas == 3


def test_build_channel_plans_deduplicates_physical_lineage_globally():
    from core.radio.failover import build_channel_plans

    rows = (
        _descriptor("rx-first", "shared-lineage", kind="dsc"),
        _descriptor("rx-duplicate", "shared-lineage", kind="navtex", frequency=518_000, mode="am"),
        _descriptor("rx-navtex", "navtex-lineage", kind="navtex", frequency=518_000, mode="am"),
    )
    plans = build_channel_plans(rows, desired_replicas=2)
    assigned = [row.receiver_id for plan in plans for row in (*plan.active, *plan.standby)]

    assert assigned == ["rx_first", "rx_navtex"]
