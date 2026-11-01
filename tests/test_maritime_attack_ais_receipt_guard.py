# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging-only regression: AIS event clocks must be checked against receipt.

AIS is contextual telemetry, not independent documentary attack evidence.
No production DB, network, cron, or incident publication is used here.
"""
from datetime import datetime, timezone
import unittest

from core.intel.maritime_attack_correlation import (
    AISFix, IncidentClaim, VesselRef, correlate,
)

UTC = timezone.utc
JET = VesselRef("9348625", "636019532", "CONTSHIP JET")


def at(hour: int, minute: int = 0, second: int = 0):
    return datetime(2026, 10, 28, hour, minute, second, tzinfo=UTC)


def claim(identifier: str, authority: str):
    return IncidentClaim(
        claim_id=identifier, kind="attack", occurred_at=at(10),
        source_group=authority,
        source_url="https://example.org/" + identifier,
        vessel=JET, lat=43.26, lon=28.81, uncertainty_km=5,
        published_at=at(11), received_at=at(11, 10),
        origin_report_id=identifier, time_uncertainty_minutes=0,
    )


def before():
    return AISFix(
        JET.mmsi, at(9, 59, 22), 43.265927, 28.814900,
        sog_knots=10.2, received_at=at(10, 0),
    )


def after(*, received_at):
    return AISFix(
        JET.mmsi, at(10, 34, 46), 43.259197, 28.815740,
        sog_knots=0.6, received_at=received_at,
    )


class AISReceiptChronologyTests(unittest.TestCase):
    def test_real_jet_speed_drop_with_plausible_receipts_remains_context_only(self):
        result = correlate(JET, [claim("mod", "bg_mod")],
                           [before(), after(received_at=at(10, 35))])
        self.assertEqual(result.status, "candidate")
        self.assertFalse(result.publication_allowed)
        self.assertIn("ais_sudden_stop_context_not_attack_proof", result.supporting)
        self.assertEqual(len(result.related_sudden_stop_fixes), 1)

    def test_future_dated_fix_cannot_create_speed_drop(self):
        result = correlate(JET, [claim("mod", "bg_mod")],
                           [before(), after(received_at=at(10, 20))])
        self.assertEqual(result.status, "candidate")
        self.assertIn("ais_fix_future_relative_to_receipt", result.contradicting)
        self.assertNotIn("ais_sudden_stop_context_not_attack_proof", result.supporting)
        self.assertEqual(result.related_sudden_stop_fixes, ())

    def test_invalid_receipt_timezone_quarantines_fix(self):
        naive = datetime(2026, 10, 28, 10, 35)
        result = correlate(JET, [claim("mod", "bg_mod")],
                           [before(), after(received_at=naive)])
        self.assertIn("invalid_ais_fix_timestamp", result.contradicting)
        self.assertEqual(result.related_sudden_stop_fixes, ())

    def test_five_minute_clock_skew_is_tolerated(self):
        result = correlate(JET, [claim("mod", "bg_mod")],
                           [before(), after(received_at=at(10, 29, 46))])
        self.assertEqual(len(result.related_sudden_stop_fixes), 1)

    def test_delayed_receipt_is_not_falsely_quarantined(self):
        result = correlate(JET, [claim("mod", "bg_mod")],
                           [before(), after(received_at=at(12))])
        self.assertEqual(len(result.related_sudden_stop_fixes), 1)

    def test_future_dated_faraway_fix_cannot_veto_two_source_claim(self):
        fake = AISFix(
            JET.mmsi, at(10, 1), 2.0, 2.0, sog_knots=0.1,
            received_at=at(9, 40),
        )
        result = correlate(
            JET, [claim("first", "bg_mod"), claim("second", "independent_mrcc")],
            [fake],
        )
        self.assertEqual(result.status, "corroborated")
        self.assertIn("ais_fix_future_relative_to_receipt", result.contradicting)
        self.assertNotIn("ais_position_conflict_needs_review", result.contradicting)
        self.assertFalse(result.publication_allowed)


if __name__ == "__main__":
    unittest.main()
