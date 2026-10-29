# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests for the staging-only maritime incident correlator."""
from datetime import datetime, timezone
import unittest

from core.intel.maritime_attack_correlation import (
    AISFix, AISGap, IncidentClaim, VesselRef, correlate,
)

UTC = timezone.utc
def dt(day, hour, minute=0, second=0):
    return datetime(2026, 10, day, hour, minute, second, tzinfo=UTC)

JET = VesselRef("9348625", "636019532", "CONTSHIP JET")


def report(identifier, group, vessel=JET, *, kind="attack", lat=43.25, lon=28.8,
           when=None, url=None):
    return IncidentClaim(
        identifier, kind, when or dt(28, 10), group,
        url or "https://example.org/" + identifier,
        vessel, lat, lon, 5.0, dt(28, 11), dt(28, 11, 30),
    )


class MaritimeAttackCorrelationTests(unittest.TestCase):
    def test_contship_jet_28_october_regression(self):
        """Two original authorities + proximate AIS => corroborated attack."""
        claims = [
            report("bulgarian_mod", "bulgarian_mod"),
            report("bulgarian_prosecutor", "bulgarian_prosecutor",
                   VesselRef(name="CONTSHIP JET")),
        ]
        ais = [AISFix(JET.mmsi, dt(28, 9, 59, 22), 43.265927, 28.814900)]
        old_gap = [AISGap(JET.mmsi, dt(26, 12, 24), "aisgap:636019532")]
        result = correlate(JET, claims, ais, old_gap)
        self.assertEqual(result.status, "corroborated")
        self.assertEqual(result.incident_type, "attack")
        self.assertEqual(result.color_token, "maritime_attack_red")
        self.assertIsNotNone(result.nearest_ais_km)
        self.assertLess(result.nearest_ais_km, 4)
        self.assertEqual(result.related_gap_ids, ())
        self.assertEqual(len(result.independent_groups), 2)

    def test_one_official_source_and_ais_is_not_corroboration(self):
        result = correlate(JET, [report("mod", "bulgarian_mod")],
                           [AISFix(JET.mmsi, dt(28, 9, 59), 43.25, 28.8)])
        self.assertEqual(result.status, "candidate")
        self.assertEqual(result.color_token, "maritime_incident_candidate_orange")

    def test_two_syndicated_stories_same_underlying_source(self):
        result = correlate(JET, [report("news_a", "bulgarian_mod"),
                                 report("news_b", "bulgarian_mod")])
        self.assertEqual(result.status, "candidate")

    def test_gap_without_attack_claim_is_not_an_attack(self):
        result = correlate(JET, [], ais_gaps=[AISGap(JET.mmsi, dt(28, 10), "gap")])
        self.assertEqual(result.status, "no_match")

    def test_proximate_gap_never_promotes_candidate(self):
        result = correlate(JET, [report("mod", "bulgarian_mod")],
                           ais_gaps=[AISGap(JET.mmsi, dt(28, 10), "gap")])
        self.assertEqual(result.status, "candidate")
        self.assertEqual(result.related_gap_ids, ("gap",))

    def test_contradictory_imo_is_vetoed_even_if_name_matches(self):
        result = correlate(JET, [
            report("good", "bulgarian_mod"),
            report("wrong", "second", VesselRef(imo="1234567", name="CONTSHIP JET")),
        ])
        self.assertEqual(result.status, "candidate")
        self.assertIn("identity_conflict:wrong", result.contradicting)

    def test_distant_coordinates_not_merged(self):
        result = correlate(JET, [report("a", "mod"),
                                 report("b", "prosecutor", lat=42.0, lon=30.0)])
        self.assertEqual(result.status, "candidate")
        self.assertIn("spatial_conflict:b", result.contradicting)

    def test_separate_sinking_update_not_same_attack_episode(self):
        result = correlate(JET, [report("attack", "mod"),
                                 report("sinking", "prosecutor", kind="sinking")])
        self.assertEqual(result.status, "candidate")
        self.assertIn("different_incident_kind:sinking", result.contradicting)

    def test_duplicate_claim_ids_do_not_count_twice(self):
        result = correlate(JET, [report("one", "mod"), report("one", "another")])
        self.assertEqual(result.status, "candidate")
        self.assertEqual(result.claim_ids, ("one",))

    def test_name_only_reports_do_not_prove_identity(self):
        name_only = VesselRef(name="CONTSHIP JET")
        result = correlate(JET, [report("a", "mod", name_only),
                                 report("b", "prosecutor", name_only)])
        self.assertEqual(result.status, "candidate")

    def test_ais_far_away_not_accepted(self):
        result = correlate(JET, [report("mod", "bulgarian_mod")],
                           [AISFix(JET.mmsi, dt(28, 10), 35.59084, 28.23322)])
        self.assertIsNone(result.nearest_ais_km)

    def test_naive_datetime_rejected(self):
        bad = IncidentClaim("x", "attack", datetime(2026, 10, 28, 10),
                            "mod", "https://example.org", JET)
        with self.assertRaises(ValueError):
            correlate(JET, [bad])


if __name__ == "__main__":
    unittest.main()
