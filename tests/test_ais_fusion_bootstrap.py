# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime, timezone

from core.vessels.ais_provider import AISPositionObservation

_NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def _obs(provider="aiscast", upstream="volunteer"):
    return AISPositionObservation(
        mmsi="258479000", ship_name="OCEAN VIKING",
        lat=35.0, lon=15.0, sog=8.0, cog=90.0, heading=90.0,
        nav_status=0, observed_at=_NOW, received_at=_NOW,
        provider=provider, upstream_source=upstream,
        station_id="mt-01" if provider == "aiscast" else None,
        source_terms="CC0-1.0" if provider == "aiscast" else None,
        raw_message_id="event-1",
    )


def test_shadow_mode_never_writes_aiscast_to_canonical_sink():
    from core.vessels.ais_runtime import AISFusionRuntime

    writes = []
    runtime = AISFusionRuntime(mode="shadow", canonical_sink=writes.append)
    runtime.ingest(_obs())

    assert writes == []
    assert runtime.status()["shadow_comparisons"] == 1


def test_fused_mode_writes_only_accepted_reconciled_fix():
    from core.vessels.ais_runtime import AISFusionRuntime

    writes = []
    runtime = AISFusionRuntime(mode="fused", canonical_sink=writes.append)
    runtime.ingest(_obs("aisstream", "aisstream"))
    runtime.ingest(_obs("aiscast", "aisstream"))

    assert len(writes) == 1
    assert writes[0].selected_upstream == "aisstream"
    assert runtime.status()["canonical_writes"] == 1


def test_legacy_mode_rejects_non_aisstream_ingest():
    from core.vessels.ais_runtime import AISFusionRuntime

    writes = []
    runtime = AISFusionRuntime(mode="legacy", canonical_sink=writes.append)
    runtime.ingest(_obs("aiscast", "volunteer"))
    assert writes == []
    assert runtime.status()["shadow_comparisons"] == 0


def test_invalid_runtime_mode_fails_closed():
    import pytest
    from core.vessels.ais_runtime import AISFusionRuntime

    with pytest.raises(ValueError):
        AISFusionRuntime(mode="experimental")


def test_start_sources_legacy_never_constructs_aiscast():
    from core.vessels.ais_runtime import start_sources

    calls = []
    made = []
    start_sources(
        mode="legacy", aisstream_key="key", aiscast_enabled=True,
        aisstream_start=lambda key, **kw: calls.append((key, kw)),
        aiscast_factory=lambda **kw: made.append(kw),
    )
    assert calls == [("key", {"ngo_api_key": ""})]
    assert made == []


def test_start_sources_shadow_keeps_aisstream_legacy_writes_and_starts_aiscast():
    from core.vessels.ais_runtime import start_sources

    calls = []
    made = []

    class FakeAiscast:
        def __init__(self, **kw):
            made.append(kw)
            self.started = False
        def start(self):
            self.started = True

    runtime = start_sources(
        mode="shadow", aisstream_key="key", aiscast_enabled=True,
        aisstream_start=lambda key, **kw: calls.append((key, kw)),
        aiscast_factory=FakeAiscast,
    )
    assert calls[0][1]["publish_legacy"] is True
    assert callable(calls[0][1]["on_observation"])
    assert made and made[0]["mmsis"]
    assert runtime.status()["aiscast_started"] is True


def test_start_sources_fused_disables_direct_aisstream_legacy_writes():
    from core.vessels.ais_runtime import start_sources

    calls = []
    runtime = start_sources(
        mode="fused", aisstream_key="key", aiscast_enabled=False,
        aisstream_start=lambda key, **kw: calls.append((key, kw)),
    )
    assert calls[0][1]["publish_legacy"] is False
    assert callable(calls[0][1]["on_observation"])
    assert runtime.status()["mode"] == "fused"


def test_config_defaults_to_legacy_cutover():
    from core.config import SuezCanalConfig

    cfg = SuezCanalConfig(_env_file=None)
    assert cfg.AIS_FUSION_MODE == "legacy"


def test_bootstrap_routes_ais_start_through_runtime(monkeypatch):
    from core.config import config
    from core.vessels import ais_runtime

    from core import bootstrap

    calls = []
    monkeypatch.setattr(config, "AISSTREAM_KEY", "key")
    monkeypatch.setattr(config, "AISSTREAM_NGO_KEY", "")
    monkeypatch.setattr(config, "AIS_FUSION_MODE", "shadow")
    monkeypatch.setattr(config, "AISCAST_ENABLED", True)
    monkeypatch.setattr(config, "AISCAST_BBOX", "32,12,38,22")
    monkeypatch.setattr(ais_runtime, "start_sources", lambda **kw: calls.append(kw))

    bootstrap._start_ais_feeds()

    assert len(calls) == 1
    assert calls[0]["mode"] == "shadow"
    assert calls[0]["aiscast_enabled"] is True


def test_runtime_health_updates_shared_coverage_state(monkeypatch):
    from core.vessels import ais_coverage
    from core.vessels.ais_provider import AISProviderHealth
    from core.vessels.ais_runtime import AISFusionRuntime

    seen = []
    monkeypatch.setattr(ais_coverage.coverage_state, "update_health", seen.append)
    runtime = AISFusionRuntime(mode="shadow")
    health = AISProviderHealth(
        provider="aiscast", connected=False, last_message_at=None,
        messages_received=0, error="timeout",
    )
    runtime.update_health(health)
    assert seen == [health]


def test_start_sources_passes_health_callback_to_both_providers():
    from core.vessels.ais_runtime import start_sources

    calls = []
    made = []

    class FakeAiscast:
        def __init__(self, **kw): made.append(kw)
        def start(self): pass

    start_sources(
        mode="shadow", aisstream_key="key", aiscast_enabled=True,
        aisstream_start=lambda key, **kw: calls.append(kw),
        aiscast_factory=FakeAiscast,
    )
    assert callable(calls[0]["on_health"])
    assert callable(made[0]["on_health"])


def test_intel_engine_status_exposes_ais_runtime_mode(monkeypatch):
    from core.intel.engine import IntelEngine
    from core.vessels import ais_runtime

    runtime = ais_runtime.AISFusionRuntime(mode="shadow")
    runtime._aiscast_started = True
    monkeypatch.setattr(ais_runtime, "_runtime", runtime)

    status = IntelEngine().status()
    assert status["ais_fusion_mode"] == "shadow"
    assert status["aiscast_started"] is True


def test_health_transition_appends_one_coverage_break(monkeypatch):
    from core.intel import coverage_change_log
    from core.vessels.ais_provider import AISProviderHealth
    from core.vessels.ais_runtime import AISFusionRuntime

    changes = []
    monkeypatch.setattr(
        coverage_change_log, "record_coverage_change",
        lambda source_name, event_type, rationale=None: changes.append(
            (source_name, event_type, rationale)
        ),
    )
    runtime = AISFusionRuntime(mode="shadow")
    runtime.update_health(AISProviderHealth("aiscast", True, _NOW, 5, None))
    runtime.update_health(AISProviderHealth("aiscast", False, _NOW, 5, "timeout"))
    runtime.update_health(AISProviderHealth("aiscast", False, _NOW, 5, "timeout"))

    assert len(changes) == 1
    assert changes[0][0:2] == ("aiscast", "coverage_break")
