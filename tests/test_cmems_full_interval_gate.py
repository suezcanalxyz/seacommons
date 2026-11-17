from datetime import datetime, timedelta, timezone
from core.drift.opendrift_pool import _reader_covers_time

def test_reader_requires_both_start_and_end_coverage():
    start = datetime(2026, 10, 24, 0, tzinfo=timezone.utc)
    class Reader:
        def __init__(self, end):
            self.end = end
        def covers_time(self, query):
            return datetime(2026, 10, 24) <= query <= self.end
    partial = Reader(datetime(2026, 10, 24, 12))
    assert _reader_covers_time(partial, start)
    assert not _reader_covers_time(partial, start + timedelta(hours=24))
    complete = Reader(datetime(2026, 10, 25))
    assert _reader_covers_time(complete, start)
    assert _reader_covers_time(complete, start + timedelta(hours=24))
