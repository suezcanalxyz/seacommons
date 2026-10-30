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
        vessel, lat, lon, 5.0, dt(28, 11), dt(28, 11, 30), identifier,
    )


class MaritimeAttackCorrelationTests(unittest.TestCase):
    def test_contship_jet_28_october_regression(self):
        """Two original authorities + proximate AIS => corroborated attack."""
        # Primary government documents, not fictional prosecutor evidence.
        # MOD reports naval/airborne observation; MTC reports the separate
        # maritime rescue-coordination signal. Independence must be audited.
        claims = [
            IncidentClaim(
                "bg_mod_20261028", "attack", dt(28, 10),
                "bg_mod_military_observation", "https://www.mod.bg/news9664",
                JET, None, None, 25.0, None, None,
                "bg_mod_news9664",
            ),
            IncidentClaim(
                "bg_mtc_20261028", "attack", dt(28, 10),
                "bg_mtc_mrcc_signal",
                "https://www.mtc.government.bg/bg/category/1/18-chlenniyat-ekipazh-na-konteynerovoza-contship-jet-e-spasen",
                VesselRef(name="CONTSHIP JET"), None, None, 25.0,
                None, None, "bg_mtc_rescue_signal",
            ),
        ]
        ais = [AISFix(JET.mmsi, dt(28, 9, 59, 22), 43.265927, 28.814900)]
        old_gap = [AISGap(JET.mmsi, dt(26, 12, 24), "aisgap:636019532")]
        result = correlate(JET, claims, ais, old_gap)
        self.assertEqual(result.status, "corroborated")
        self.assertEqual(result.incident_type, "attack")
        self.assertEqual(result.color_token, "maritime_attack_red")
        # No invented incident coordinate: the official reports specify a
        # relative location, not a precise latitude/longitude. The AIS fix
        # is retained separately and cannot self-corroborate the attack.
        self.assertIsNone(result.nearest_ais_km)
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

    def test_same_document_cannot_be_two_independent_sources(self):
        from dataclasses import replace
        first = report("a", "publisher_one")
        second = replace(report("b", "publisher_two"), source_url=first.source_url)
        result = correlate(JET, [first, second])
        self.assertEqual(result.status, "candidate")

    def test_unrelated_anchor_cannot_bootstrap_later_claim(self):
        unrelated = report("unrelated", "source_one", VesselRef(imo="1234567", name="OTHER"))
        related = report("related", "source_two")
        result = correlate(JET, [unrelated, related])
        self.assertEqual(result.status, "no_match")

    def test_ais_far_away_not_accepted(self):
        result = correlate(JET, [report("mod", "bulgarian_mod")],
                           [AISFix(JET.mmsi, dt(28, 10), 35.59084, 28.23322)])
        self.assertIsNone(result.nearest_ais_km)

    def test_naive_datetime_rejected(self):
        bad = IncidentClaim("x", "attack", datetime(2026, 10, 28, 10),
                            "mod", "https://example.org", JET)
        with self.assertRaises(ValueError):
            correlate(JET, [bad])

    def test_unknown_original_report_provenance_cannot_corroborate(self):
        from dataclasses import replace
        a = replace(report("a", "publisher_one"), origin_report_id=None)
        b = replace(report("b", "publisher_two"), origin_report_id=None)
        result = correlate(JET, [a, b])
        self.assertEqual(result.status, "candidate")
        self.assertEqual(result.independent_groups, ())

    def test_syndicated_original_across_different_urls_and_groups(self):
        """Different publishers repeating one document are not two witnesses."""
        from dataclasses import replace
        a = report("mod", "bulgarian_mod")
        b = report("reprint", "newsroom")
        a = replace(a, origin_report_id="ministry_release_20261028")
        b = replace(b, origin_report_id="ministry_release_20261028")
        result = correlate(JET, [a, b])
        self.assertEqual(result.status, "candidate")
        self.assertEqual(len(result.independent_groups), 1)

    def test_provenance_event_publication_reception_preserved(self):
        result = correlate(JET, [report("mod", "bulgarian_mod")])
        self.assertEqual(len(result.source_evidence), 1)
        row = result.source_evidence[0]
        self.assertEqual(row["occurred_at"], dt(28, 10).isoformat())
        self.assertEqual(row["published_at"], dt(28, 11).isoformat())
        self.assertEqual(row["received_at"], dt(28, 11, 30).isoformat())
        self.assertFalse(result.publication_allowed)
        self.assertTrue(result.requires_operator_review)

    def test_impossible_publication_receipt_order_excluded(self):
        from dataclasses import replace
        a = report("mod", "bulgarian_mod")
        bad = replace(report("second", "independent"),
                      received_at=dt(28, 10, 30))
        result = correlate(JET, [a, bad])
        self.assertEqual(result.status, "candidate")
        self.assertIn("publication_after_receipt:second", result.contradicting)

    def test_distinct_attacks_three_hours_apart_not_merged(self):
        from dataclasses import replace
        a = report("first", "ministry")
        b = replace(report("second", "coast_guard"), occurred_at=dt(28, 13),
                    published_at=dt(28, 14), received_at=dt(28, 14, 30))
        result = correlate(JET, [a, b])
        self.assertEqual(result.status, "candidate")
        self.assertIn("temporal_conflict:second", result.contradicting)

    def test_approximate_time_can_overlap_with_uncertainty(self):
        from dataclasses import replace
        a = replace(report("first", "ministry"), time_uncertainty_minutes=40)
        b = replace(report("second", "coast_guard"),
                    occurred_at=dt(28, 12), time_uncertainty_minutes=40,
                    published_at=dt(28, 13), received_at=dt(28, 13, 30))
        result = correlate(JET, [a, b])
        self.assertEqual(result.status, "corroborated")
        self.assertEqual(result.source_evidence[0]["time_uncertainty_minutes"], "40")

    def test_contradictory_ais_needs_review_not_attack_disproof(self):
        a = report("first", "ministry")
        b = report("second", "coast_guard")
        distant = AISFix(JET.mmsi, dt(28, 10), 35.59084, 28.23322)
        result = correlate(JET, [a, b], [distant])
        self.assertEqual(result.status, "candidate")
        self.assertIn("ais_position_conflict_needs_review", result.contradicting)
        self.assertFalse(result.publication_allowed)

    def test_ais_conflict_outside_event_window_does_not_veto(self):
        a = report("first", "ministry")
        b = report("second", "coast_guard")
        distant = AISFix(JET.mmsi, dt(28, 12), 35.59084, 28.23322)
        result = correlate(JET, [a, b], [distant])
        self.assertEqual(result.status, "corroborated")

    def test_negative_time_uncertainty_rejected(self):
        from dataclasses import replace
        bad = replace(report("first", "ministry"), time_uncertainty_minutes=-1)
        with self.assertRaises(ValueError):
            correlate(JET, [bad])

    def test_publication_before_attack_is_rejected(self):
        from dataclasses import replace
        a = report("first", "ministry")
        b = replace(report("second", "coast_guard"),
                    occurred_at=dt(28, 12), published_at=dt(28, 11),
                    received_at=dt(28, 11, 30),
                    time_uncertainty_minutes=0)
        result = correlate(JET, [a, b])
        self.assertEqual(result.status, "candidate")
        self.assertIn("publication_before_incident:second", result.contradicting)

    def test_unlocated_anchor_cannot_join_distant_reports(self):
        from dataclasses import replace
        anchor = replace(report("anchor", "unknown"), lat=None, lon=None,
                         origin_report_id=None)
        black_sea = report("black_sea", "coast_guard", lat=43.25, lon=28.8)
        pacific = report("pacific", "navy", lat=15.0, lon=130.0)
        result = correlate(JET, [anchor, black_sea, pacific])
        self.assertEqual(result.status, "candidate")
        self.assertIn("spatial_conflict:pacific", result.contradicting)
        self.assertNotIn("pacific", result.claim_ids)

    def test_wide_anchor_time_does_not_join_distinct_attacks(self):
        from dataclasses import replace
        anchor = replace(report("anchor", "unknown"), lat=None, lon=None,
                         origin_report_id=None, time_uncertainty_minutes=180)
        early = replace(report("early", "navy"), occurred_at=dt(28, 8))
        late = replace(report("late", "coast_guard"), occurred_at=dt(28, 12),
                       published_at=dt(28, 13), received_at=dt(28, 13, 30))
        result = correlate(JET, [anchor, early, late])
        self.assertEqual(result.status, "candidate")
        self.assertIn("temporal_conflict:late", result.contradicting)

    def test_malformed_location_is_rejected(self):
        from dataclasses import replace
        for lat, lon in ((91.0, 28.8), (43.25, None), (float("nan"), 28.8),
                         (43.25, float("inf"))):
            with self.subTest(lat=lat, lon=lon):
                with self.assertRaises(ValueError):
                    correlate(JET, [replace(report("bad", "mod"), lat=lat, lon=lon)])

    def test_nonfinite_uncertainty_is_rejected(self):
        from dataclasses import replace
        for key in ("uncertainty_km", "time_uncertainty_minutes"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    correlate(JET, [replace(report("bad", "mod"), **{key: float("nan")})])

    def test_http_link_cannot_auto_corroborate(self):
        from dataclasses import replace
        a = report("mod", "bulgarian_mod")
        b = replace(report("second", "independent"),
                    source_url="http://example.org/second")
        result = correlate(JET, [a, b])
        self.assertEqual(result.status, "candidate")
        self.assertFalse(result.publication_allowed)


    def test_tracking_aliases_cannot_double_corroborate(self):
        from dataclasses import replace
        a = replace(report("first", "navy"), source_url="https://example.org/report?id=4&utm_source=x")
        b = replace(report("second", "press"), source_url="https://EXAMPLE.org/report/?id=4#top")
        result = correlate(JET, [a, b])
        self.assertEqual(result.status, "candidate")
        self.assertEqual(len(result.independent_groups), 1)

    def test_distinct_article_query_identifiers_stay_distinct(self):
        from dataclasses import replace
        a = replace(report("first", "navy"), source_url="https://example.org/report?id=4")
        b = replace(report("second", "coast_guard"), source_url="https://example.org/report?id=5")
        result = correlate(JET, [a, b])
        self.assertEqual(result.status, "corroborated")

    def test_malformed_https_without_hostname_cannot_corroborate(self):
        from dataclasses import replace
        a = report("first", "navy")
        b = replace(report("second", "coast_guard"), source_url="https://")
        result = correlate(JET, [a, b])
        self.assertEqual(result.status, "candidate")
        self.assertFalse(result.publication_allowed)

    def test_local_and_credentialed_urls_cannot_corroborate(self):
        from dataclasses import replace
        a = report("first", "navy")
        for url in ("https://localhost/news", "https://127.0.0.1/report",
                    "https://user:password@example.org/report"):
            with self.subTest(url=url):
                b = replace(report("second", "coast_guard"), source_url=url)
                result = correlate(JET, [a, b])
                self.assertEqual(result.status, "candidate")


    def test_nonfinite_ais_fix_never_becomes_spatial_support(self):
        a = report("first", "navy")
        bad = AISFix(JET.mmsi, dt(28, 10), float("nan"), 28.8)
        result = correlate(JET, [a], [bad])
        self.assertEqual(result.status, "candidate")
        self.assertIsNone(result.nearest_ais_km)
        self.assertIn("invalid_ais_fix_coordinates", result.contradicting)
        self.assertNotIn("ais_spatiotemporal_context_not_attack_proof", result.supporting)

    def test_out_of_range_ais_fix_does_not_veto_real_reports(self):
        a = report("first", "navy")
        b = report("second", "coast_guard")
        bad = AISFix(JET.mmsi, dt(28, 10), 110.0, 28.8)
        result = correlate(JET, [a, b], [bad])
        self.assertEqual(result.status, "corroborated")
        self.assertIn("invalid_ais_fix_coordinates", result.contradicting)

    def test_naive_ais_fix_is_quarantined(self):
        a = report("first", "navy")
        bad = AISFix(JET.mmsi, datetime(2026, 10, 28, 10), 43.25, 28.8)
        result = correlate(JET, [a], [bad])
        self.assertIsNone(result.nearest_ais_km)
        self.assertIn("invalid_ais_fix_timestamp", result.contradicting)


    def test_malformed_third_url_does_not_veto_two_primary_reports(self):
        from dataclasses import replace
        a = report("navy_primary", "navy")
        b = report("mrcc_primary", "coast_guard")
        bad = replace(report("bad_reprint", "untrusted"), source_url="http://example.org/incident")
        result = correlate(JET, [a, b, bad])
        self.assertEqual(result.status, "corroborated")
        self.assertEqual(len(result.independent_groups), 2)
        self.assertIn("invalid_source_url:bad_reprint", result.contradicting)
        self.assertFalse(result.publication_allowed)

    def test_unattributable_strong_identifier_cannot_launder_name_only_reports(self):
        from dataclasses import replace
        bad = replace(report("bad_id", "unknown"), source_url="http://example.org/incident")
        name = VesselRef(name="CONTSHIP JET")
        a = report("name_a", "navy", name)
        b = report("name_b", "coast_guard", name)
        result = correlate(JET, [bad, a, b])
        self.assertEqual(result.status, "candidate")
        self.assertIn("invalid_source_url:bad_id", result.contradicting)

    def test_receipt_before_incident_without_publication_is_quarantined(self):
        from dataclasses import replace
        a = report("valid", "navy")
        bad = replace(report("premature", "coast_guard"),
                      published_at=None, received_at=dt(28, 9))
        result = correlate(JET, [a, bad])
        self.assertEqual(result.status, "candidate")
        self.assertIn("receipt_before_incident:premature", result.contradicting)
        self.assertNotIn("premature", result.claim_ids)

    def test_naive_ais_gap_does_not_crash_correlation(self):
        bad = AISGap(JET.mmsi, datetime(2026, 10, 28, 10), "bad_gap")
        result = correlate(JET, [report("navy", "navy")], ais_gaps=[bad])
        self.assertEqual(result.status, "candidate")
        self.assertIn("invalid_ais_gap_timestamp:bad_gap", result.contradicting)
        self.assertEqual(result.related_gap_ids, ())


    def test_unattributed_reprint_cannot_reserve_primary_origin(self):
        from dataclasses import replace
        unlabelled = replace(report("unlabelled", ""), origin_report_id="origin_a")
        primary = replace(report("primary", "navy"), origin_report_id="origin_a")
        independent = replace(report("independent", "mrcc"), origin_report_id="origin_b")
        result = correlate(JET, [unlabelled, primary, independent])
        self.assertEqual(result.status, "corroborated")
        self.assertEqual(result.independent_groups, ("mrcc", "navy"))
        self.assertFalse(result.publication_allowed)

    def test_unattributed_same_url_cannot_reserve_document(self):
        from dataclasses import replace
        unlabelled = replace(report("unlabelled", ""), source_url="https://example.org/primary",
                             origin_report_id="origin_a")
        primary = replace(report("primary", "navy"), source_url="https://example.org/primary",
                          origin_report_id="origin_a")
        independent = report("independent", "mrcc")
        result = correlate(JET, [unlabelled, primary, independent])
        self.assertEqual(result.status, "corroborated")
        self.assertEqual(result.independent_groups, ("mrcc", "navy"))
        self.assertFalse(result.publication_allowed)


    def test_invalid_imo_cannot_establish_strong_identity(self):
        bad = VesselRef(imo="1234560", name="CONTSHIP JET")
        result = correlate(bad, [report("bad_a", "navy", bad),
                                 report("bad_b", "mrcc", bad)])
        self.assertEqual(result.status, "candidate")
        self.assertNotIn("strong_vessel_identifier", result.supporting)

    def test_placeholder_mmsi_cannot_establish_strong_identity(self):
        bad = VesselRef(mmsi="000000000", name="CONTSHIP JET")
        result = correlate(bad, [report("bad_a", "navy", bad),
                                 report("bad_b", "mrcc", bad)])
        self.assertEqual(result.status, "candidate")
        self.assertNotIn("strong_vessel_identifier", result.supporting)


class SourceObservationAdapterTests(unittest.TestCase):
    """Pure adapter tests; no DB credentials, network, writes or schedulers."""

    @staticmethod
    def observation(identifier, *, verified=True, authority="navy",
                    report="navy-20261028", published="2026-10-28T11:00:00+00:00"):
        from types import SimpleNamespace
        return SimpleNamespace(
            observation_id="obs:" + identifier,
            source_url="https://example.org/" + identifier,
            received_at="2026-10-28T11:30:00",  # DB's documented naive UTC
            provenance={
                "origin_authority_verified": verified,
                "originating_authority_id": authority,
                "original_report_id": report,
                "published_at": published,
            },
        )

    @staticmethod
    def extraction():
        return {"kind": "attack", "occurred_at": "2026-10-28T10:00:00Z",
                "imo": "9348625", "mmsi": "636019532",
                "vessel_name": "CONTSHIP JET"}

    def test_verified_independent_observations_corroborate_without_ais(self):
        from core.intel.maritime_attack_correlation import claim_from_source_observation
        a = claim_from_source_observation(self.observation("navy"), self.extraction())
        b = claim_from_source_observation(
            self.observation("mrcc", authority="mrcc", report="mrcc-20261028"),
            self.extraction())
        result = correlate(JET, [a, b])
        self.assertEqual(result.status, "corroborated")
        self.assertEqual(result.related_gap_ids, ())
        self.assertFalse(result.publication_allowed)

    def test_unverified_extracted_publisher_does_not_create_independence(self):
        from core.intel.maritime_attack_correlation import claim_from_source_observation
        a = claim_from_source_observation(
            self.observation("navy", verified=False), self.extraction())
        b = claim_from_source_observation(
            self.observation("mrcc", verified=False, authority="mrcc"), self.extraction())
        result = correlate(JET, [a, b])
        self.assertEqual(result.status, "candidate")
        self.assertEqual(result.independent_groups, ())

    def test_canonical_naive_utc_receipt_is_normalized(self):
        from core.intel.maritime_attack_correlation import claim_from_source_observation
        claim = claim_from_source_observation(self.observation("navy"), self.extraction())
        self.assertEqual(claim.received_at, dt(28, 11, 30))
        self.assertEqual(claim.published_at, dt(28, 11))
        self.assertEqual(claim.claim_id, "obs:navy")

    def test_naive_event_time_fails_closed(self):
        from core.intel.maritime_attack_correlation import claim_from_source_observation
        extracted = {**self.extraction(), "occurred_at": "2026-10-28T10:00:00"}
        with self.assertRaises(ValueError):
            claim_from_source_observation(self.observation("navy"), extracted)

    def test_invalid_extracted_geometry_fails_closed(self):
        from core.intel.maritime_attack_correlation import claim_from_source_observation
        extracted = {**self.extraction(), "lat": 110.0, "lon": 28.8}
        with self.assertRaises(ValueError):
            claim_from_source_observation(self.observation("navy"), extracted)

    def test_context_advisory_and_unidentified_vessel_do_not_become_claims(self):
        from core.intel.maritime_attack_correlation import claim_from_source_observation
        self.assertIsNone(claim_from_source_observation(
            self.observation("navy"), {**self.extraction(), "kind": "advisory"}))
        self.assertIsNone(claim_from_source_observation(
            self.observation("navy"), {"kind": "attack",
                "occurred_at": "2026-10-28T10:00:00Z"}))


    def test_imo_and_mmsi_labels_are_normalized(self):
        from core.intel.maritime_attack_correlation import claim_from_source_observation
        extraction = {**self.extraction(), "imo": "IMO: 9348625",
                      "mmsi": "MMSI 636019532"}
        claim = claim_from_source_observation(self.observation("navy"), extraction)
        self.assertEqual(claim.vessel.imo, "9348625")
        self.assertEqual(claim.vessel.mmsi, "636019532")

    def test_invalid_imo_checksum_fails_closed(self):
        from core.intel.maritime_attack_correlation import claim_from_source_observation
        extraction = {**self.extraction(), "imo": "9348624"}
        with self.assertRaisesRegex(ValueError, "Invalid IMO"):
            claim_from_source_observation(self.observation("navy"), extraction)

    def test_placeholder_mmsi_fails_closed(self):
        from core.intel.maritime_attack_correlation import claim_from_source_observation
        extraction = {**self.extraction(), "mmsi": "000000000"}
        with self.assertRaisesRegex(ValueError, "Invalid MMSI"):
            claim_from_source_observation(self.observation("navy"), extraction)

    def test_incomplete_or_unicode_mmsi_fails_closed(self):
        from core.intel.maritime_attack_correlation import claim_from_source_observation
        for mmsi in ("63601953", "６３６０１９５３２"):
            with self.subTest(mmsi=mmsi):
                extraction = {**self.extraction(), "mmsi": mmsi}
                with self.assertRaisesRegex(ValueError, "Invalid MMSI"):
                    claim_from_source_observation(self.observation("navy"), extraction)


if __name__ == "__main__":
    unittest.main()
