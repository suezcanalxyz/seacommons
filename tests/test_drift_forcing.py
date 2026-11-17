from core.drift.forcing import classify_forcing_quality


def test_total_grid_failure_is_degraded_constant_even_when_reader_exists():
    result = classify_forcing_quality(
        wind_coverage=0.0,
        current_coverage=0.0,
        cmems_current=False,
        grid_reader=True,
    )
    assert result == ("degraded-constant", False)


def test_complete_provider_coverage_is_operational_spatiotemporal():
    result = classify_forcing_quality(
        wind_coverage=1.0,
        current_coverage=1.0,
        cmems_current=False,
        grid_reader=True,
    )
    assert result == ("observed-spatiotemporal", True)


def test_cmems_can_supply_current_but_not_missing_wind():
    assert classify_forcing_quality(
        wind_coverage=0.0,
        current_coverage=0.0,
        cmems_current=True,
        grid_reader=True,
    ) == ("degraded-constant", False)


def test_partial_required_coverage_is_mixed_and_not_operational():
    assert classify_forcing_quality(
        wind_coverage=0.7,
        current_coverage=1.0,
        cmems_current=False,
        grid_reader=True,
    ) == ("mixed", False)


def test_copernicus_overwrite_keyword_uses_current_client_signature():
    from core.drift.opendrift_pool import _copernicus_overwrite_kwargs

    def subset(*, overwrite=False):
        return overwrite

    assert _copernicus_overwrite_kwargs(subset) == {"overwrite": True}


def test_copernicus_overwrite_keyword_keeps_legacy_client_compatibility():
    from core.drift.opendrift_pool import _copernicus_overwrite_kwargs

    def subset(*, overwrite_output_data=False):
        return overwrite_output_data

    assert _copernicus_overwrite_kwargs(subset) == {"overwrite_output_data": True}


def test_reader_time_gate_rejects_provider_outside_simulation_start():
    from datetime import datetime, timezone
    from core.drift.opendrift_pool import _reader_covers_time

    class Reader:
        def covers_time(self, value):
            return value.hour == 0

    assert _reader_covers_time(Reader(), datetime(2026, 10, 24, 0, tzinfo=timezone.utc)) is True
    assert _reader_covers_time(Reader(), datetime(2026, 10, 24, 10, tzinfo=timezone.utc)) is False
