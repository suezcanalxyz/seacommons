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
