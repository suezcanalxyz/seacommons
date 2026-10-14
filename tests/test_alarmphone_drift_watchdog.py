from datetime import datetime, timedelta, timezone
from core.intel.drift_watchdog import _age, STUCK_AFTER, RETRY_AFTER


def test_retry_age_parses_offset_and_naive():
    now = datetime(2026, 10, 14, 10, tzinfo=timezone.utc)
    assert _age('2026-10-14T09:45:00Z', now) == timedelta(minutes=15)
    assert _age('2026-10-14T09:45:00', now) == timedelta(minutes=15)


def test_bad_timestamp_does_not_trigger_immediate_retries():
    assert _age('bogus', datetime.now(timezone.utc)) is None
    assert STUCK_AFTER > RETRY_AFTER
