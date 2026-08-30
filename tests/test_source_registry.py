from __future__ import annotations

from core.intel.source_registry import SourceRegistry


def test_multi_source_channel_is_degraded_when_one_handle_is_unavailable() -> None:
    registry = SourceRegistry()
    registry.register("X / Twitter (twikit)", "twitter")
    registry.register_targets(
        "X / Twitter (twikit)",
        ["@alarm_phone", "SeaEye4"],
    )

    registry.record_target_poll(
        "X / Twitter (twikit)",
        "alarm_phone",
        events_found=2,
    )
    registry.record_target_poll(
        "X / Twitter (twikit)",
        "SeaEye4",
        error="The user does not exist",
    )
    registry.record_poll("X / Twitter (twikit)", events_found=2)

    source = registry.get_all()[0]
    assert source["pipeline_status"] == "active"
    assert source["source_status"] == "degraded"
    assert source["status"] == "degraded"
    assert source["configured"] == 2
    assert source["reachable"] == 1
    assert {handle["name"]: handle["status"] for handle in source["handles"]} == {
        "alarm_phone": "healthy",
        "SeaEye4": "unavailable",
    }


def test_multi_source_channel_recovers_when_every_handle_is_reachable() -> None:
    registry = SourceRegistry()
    registry.register("Official NGO RSS", "rss")
    registry.register_targets("Official NGO RSS", ["msf", "sos_mediterranee"])
    registry.record_target_poll("Official NGO RSS", "msf")
    registry.record_target_poll("Official NGO RSS", "sos_mediterranee")
    registry.record_poll("Official NGO RSS")

    source = registry.get_all()[0]
    assert source["pipeline_status"] == "active"
    assert source["source_status"] == "healthy"
    assert source["status"] == "active"
    assert source["reachable"] == source["configured"] == 2
