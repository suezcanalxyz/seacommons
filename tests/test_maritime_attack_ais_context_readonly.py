# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure, no-DB regression for bounded AIS incident context reads."""
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from core.intel.maritime_attack_ais_context_readonly import (
    load_ais_context, load_ais_context_db,
)
from core.intel.maritime_attack_correlation import (
    IncidentClaim, VesselRef, correlate,
)

JET = VesselRef("9348625", "636019532", "CONTSHIP JET")


def at(hour, minute=0, second=0):
    return datetime(2026, 10, 28, hour, minute, second, tzinfo=timezone.utc)


def row(identifier, when, speed, lat=43.26, lon=28.815, **overrides):
    fields = dict(id=identifier, mmsi=JET.mmsi, ts=when.replace(tzinfo=None),
                  received_at=(when.replace(tzinfo=None)), lat=lat, lon=lon,
                  sog=speed)
    fields.update(overrides)
    return SimpleNamespace(**fields)


def claim():
    return IncidentClaim(
        "bg_mod", "attack", at(10), "bg_mod",
        "https://www.mod.bg/news9664", JET,
        lat=43.26, lon=28.81, uncertainty_km=5,
        published_at=at(11), received_at=at(11, 10),
        origin_report_id="bg_mod:news9664", time_uncertainty_minutes=0,
    )


class AISContextReadOnlyTests(unittest.TestCase):
    def test_realistic_jet_rows_sorted_and_context_only(self):
        before = row(101, at(9, 59, 22), 10.2, 43.265927, 28.8149)
        after = row(102, at(10, 34, 46), 0.6, 43.259197, 28.81574)
        result = load_ais_context(JET.mmsi, at(10),
                                  lambda *_: [after, before])
        self.assertTrue(result.complete)
        self.assertEqual(result.track_ids, (101, 102))
        correlation = correlate(JET, [claim()], result.fixes)
        self.assertEqual(correlation.status, "candidate")
        self.assertIn("ais_sudden_stop_context_not_attack_proof", correlation.supporting)
        self.assertFalse(correlation.publication_allowed)

    def test_limit_is_max_plus_one_and_no_partial_context(self):
        limits = []
        def fetch(mmsi, start, end, limit):
            limits.append(limit)
            return [row(i, at(9, 59, 22), 10.2) for i in range(1, 4)]
        result = load_ais_context(JET.mmsi, at(10), fetch, max_rows=2)
        self.assertFalse(result.complete)
        self.assertEqual(result.reason, "ais_context_row_limit")
        self.assertEqual(result.fixes, ())
        self.assertEqual(limits, [3])

    def test_mismatched_vessel_or_outside_window_fails_closed(self):
        for invalid in (
            row(1, at(9, 59), 10.2, mmsi="123456789"),
            row(1, at(7), 10.2),
        ):
            with self.subTest(invalid=invalid):
                result = load_ais_context(JET.mmsi, at(10), lambda *_: [invalid])
                self.assertFalse(result.complete)
                self.assertEqual(result.fixes, ())

    def test_duplicate_ids_and_missing_receipt_fail_closed(self):
        cases = (
            [row(1, at(9, 59), 10), row(1, at(10, 10), 0.6)],
            [row(1, at(9, 59), 10, received_at=None)],
        )
        for rows in cases:
            with self.subTest(rows=rows):
                result = load_ais_context(JET.mmsi, at(10), lambda *_: rows)
                self.assertFalse(result.complete)
                self.assertEqual(result.track_ids, ())

    def test_bounded_utc_window_and_timezone_required(self):
        seen = []
        def fetch(mmsi, start, end, limit):
            seen.append((mmsi, start, end, limit))
            return []
        result = load_ais_context(JET.mmsi, at(10), fetch)
        self.assertTrue(result.complete)
        self.assertEqual(seen[0], (JET.mmsi, at(9, 30), at(11, 30), 257))
        with self.assertRaises(ValueError):
            load_ais_context(JET.mmsi, datetime(2026, 10, 28, 10), fetch)
        with self.assertRaises(ValueError):
            load_ais_context(JET.mmsi, at(10), fetch, max_rows=100000)

    def test_non_postgres_db_rejected_before_query(self):
        fake = SimpleNamespace(get_bind=lambda: SimpleNamespace(
            dialect=SimpleNamespace(name="sqlite")))
        with self.assertRaises(ValueError):
            load_ais_context_db(fake, JET.mmsi, at(10))


if __name__ == "__main__":
    unittest.main()
