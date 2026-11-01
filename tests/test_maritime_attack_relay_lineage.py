# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline regressions for reviewed source-dependency evidence.

The example labels are synthetic; no real witness independence is asserted.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest import TestCase

from core.intel.maritime_attack_correlation import IncidentClaim, VesselRef, correlate
from core.intel.maritime_attack_relay_lineage import (
    ReviewedRelay, reviewed_relay_edges,
)

UTC = timezone.utc
JET = VesselRef("9348625", "636019532", "CONTSHIP JET")
ORIGIN_URL = (
    "https://contships-management.com/2026/10/29/"
    "contships-management-inc-company-update/"
)
RELAY_URL = (
    "https://www.zim.com/za-hant/customer-updates/"
    "mv-contship-jet-cj5-v-74w"
)


def when(hour=10):
    return datetime(2026, 10, 28, hour, tzinfo=UTC)


def claim(identifier, group, url):
    return IncidentClaim(
        claim_id=identifier, kind="attack", occurred_at=when(),
        source_group=group, source_url=url, vessel=JET,
        published_at=when(11), received_at=when(12),
        origin_report_id=identifier,
    )


def fixture(**changes):
    return replace(ReviewedRelay(
        relay_claim_id="charterer", origin_claim_id="owner",
        relay_source_url=RELAY_URL, origin_source_url=ORIGIN_URL,
        evidence_url=RELAY_URL + "?utm_source=review",
        document_sha256="a" * 64, relation="owner_notified_charterer",
        reviewed_by="synthetic-reviewer",
        captured_at=datetime(2026, 11, 1, 16, tzinfo=UTC),
        reviewed_at=datetime(2026, 11, 1, 17, tzinfo=UTC),
    ), **changes)


class ReviewedRelayLineageTests(TestCase):
    def setUp(self):
        self.claims = [
            claim("owner", "synthetic_owner", ORIGIN_URL),
            claim("charterer", "synthetic_charterer", RELAY_URL),
        ]

    def test_documented_dependency_collapses_two_synthetic_origins(self):
        # Without a lineage edge, manually asserted distinct labels could
        # incorrectly look independent. An audited relay must count once.
        baseline = correlate(JET, self.claims)
        self.assertEqual(baseline.status, "corroborated")
        review = reviewed_relay_edges(self.claims, [fixture()])
        self.assertEqual(review.edges, (("charterer", "owner"),))
        self.assertEqual(review.rejected, ())
        self.assertFalse(review.publication_allowed)
        linked = correlate(JET, self.claims, lineage_edges=review.edges)
        self.assertEqual(linked.status, "candidate")
        self.assertEqual(len(linked.independent_groups), 1)
        self.assertIn("derived_source_not_independent", linked.contradicting)
        self.assertFalse(linked.publication_allowed)

    def test_unreviewed_or_unhashed_document_cannot_create_edge(self):
        for change in ({"reviewed_by": ""}, {"document_sha256": ""},
                       {"document_sha256": "a" * 63}):
            with self.subTest(change=change):
                result = reviewed_relay_edges(self.claims, [fixture(**change)])
                self.assertEqual(result.edges, ())
                self.assertIn("unreviewed_or_unhashed_document", result.rejected[0])

    def test_mismatched_or_forged_source_url_is_rejected(self):
        for change in (
            {"relay_source_url": "https://evil.example/zim"},
            {"origin_source_url": RELAY_URL},
            {"evidence_url": "https://unrelated.example/report"},
            {"evidence_url": "http://www.zim.com/za-hant/customer-updates/x"},
        ):
            with self.subTest(change=change):
                result = reviewed_relay_edges(self.claims, [fixture(**change)])
                self.assertEqual(result.edges, ())
                self.assertIn("source_url_provenance_mismatch", result.rejected[0])

    def test_unknown_claim_and_self_reference_rejected(self):
        for change in ({"origin_claim_id": "unknown"},
                       {"origin_claim_id": "charterer"}):
            result = reviewed_relay_edges(self.claims, [fixture(**change)])
            self.assertEqual(result.edges, ())
            self.assertIn("unknown_or_self_referential_claim", result.rejected[0])

    def test_capture_review_clock_validation(self):
        for change, reason in (
            ({"reviewed_at": datetime(2026, 11, 1, 15, tzinfo=UTC)},
             "review_predates_capture"),
            ({"captured_at": datetime(2026, 11, 1, 16)},
             "invalid_review_timestamp"),
        ):
            result = reviewed_relay_edges(self.claims, [fixture(**change)])
            self.assertEqual(result.edges, ())
            self.assertIn(reason, result.rejected[0])

    def test_duplicate_edges_are_deduplicated_without_new_origins(self):
        review = reviewed_relay_edges(self.claims, [
            fixture(), fixture(evidence_url=RELAY_URL + "#press-release")
        ])
        self.assertEqual(review.edges, (("charterer", "owner"),))
        self.assertEqual(review.rejected, ())

    def test_independent_third_origin_remains_distinct(self):
        claims = self.claims + [
            claim("third", "synthetic_independent", "https://example.org/third")
        ]
        review = reviewed_relay_edges(claims, [fixture()])
        linked = correlate(JET, claims, lineage_edges=review.edges)
        self.assertEqual(linked.status, "corroborated")
        self.assertEqual(len(linked.independent_groups), 2)
        self.assertFalse(linked.publication_allowed)

    def test_unsupported_relation_and_conflicting_claim_ids_fail_closed(self):
        result = reviewed_relay_edges(self.claims, [fixture(relation="guessed_similar_text")])
        self.assertEqual(result.edges, ())
        self.assertIn("unsupported_dependency_relation", result.rejected[0])
        altered = replace(self.claims[0], source_group="different")
        result = reviewed_relay_edges(self.claims + [altered], [fixture()])
        self.assertEqual(result.edges, ())
        self.assertEqual(result.rejected, ("conflicting_claim_identifiers",))
