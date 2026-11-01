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

    def test_capture_before_relay_publication_is_quarantined(self):
        early = datetime(2026, 10, 28, 10, tzinfo=UTC)
        result = reviewed_relay_edges(
            self.claims, [fixture(captured_at=early)]
        )
        self.assertEqual(result.edges, ())
        self.assertIn("capture_predates_relay_publication", result.rejected[0])

    def test_two_competing_originals_are_flagged_and_collapsed(self):
        third = claim(
            "other", "synthetic_third", "https://example.org/other"
        )
        claims = self.claims + [third]
        competing = fixture(
            origin_claim_id="other", origin_source_url=third.source_url
        )
        review = reviewed_relay_edges(claims, [fixture(), competing])
        self.assertEqual(len(review.edges), 2)
        self.assertIn(
            "conflicting_relay_origins:charterer", review.rejected
        )
        self.assertFalse(review.publication_allowed)
        result = correlate(JET, claims, lineage_edges=review.edges)
        self.assertEqual(result.status, "candidate")
        self.assertEqual(len(result.independent_groups), 1)

    def test_dependency_cycle_flagged_without_creating_independence(self):
        reverse = fixture(
            relay_claim_id="owner", origin_claim_id="charterer",
            relay_source_url=ORIGIN_URL, origin_source_url=RELAY_URL,
            evidence_url=ORIGIN_URL,
        )
        review = reviewed_relay_edges(self.claims, [fixture(), reverse])
        self.assertEqual(len(review.edges), 2)
        self.assertIn("dependency_cycle", review.rejected)
        self.assertFalse(review.publication_allowed)
        result = correlate(JET, self.claims, lineage_edges=review.edges)
        self.assertEqual(result.status, "candidate")
        self.assertEqual(len(result.independent_groups), 1)

    def test_long_documentary_chain_does_not_recurse_or_invent_origins(self):
        # A lengthy syndication chain must not exhaust Python's recursion
        # limit or be misidentified as a cycle.
        count = 1100
        claims = [
            claim(str(i), "synthetic_" + str(i),
                  "https://example.org/relay/" + str(i))
            for i in range(count)
        ]
        relays = [
            ReviewedRelay(
                relay_claim_id=str(i), origin_claim_id=str(i - 1),
                relay_source_url=claims[i].source_url,
                origin_source_url=claims[i - 1].source_url,
                evidence_url=claims[i].source_url,
                document_sha256="a" * 64,
                relation="reprinted_from", reviewed_by="synthetic-reviewer",
                captured_at=datetime(2026, 11, 1, 16, tzinfo=UTC),
                reviewed_at=datetime(2026, 11, 1, 17, tzinfo=UTC),
            )
            for i in range(1, count)
        ]
        review = reviewed_relay_edges(claims, relays)
        self.assertEqual(len(review.edges), count - 1)
        self.assertEqual(review.rejected, ())
        self.assertFalse(review.publication_allowed)

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

    def test_later_owner_press_release_cannot_be_charterer_original(self):
        # The real ZIM update is dated 28 Oct and the Contships company
        # page 29 Oct. This is NOT proof that ZIM copied that later page.
        later = replace(self.claims[0], published_at=when(13))
        result = reviewed_relay_edges([later, self.claims[1]], [fixture()])
        self.assertEqual(result.edges, ())
        self.assertIn("origin_document_postdates_relay", result.rejected[0])

    def test_unknown_or_naive_publication_clock_cannot_verify_lineage(self):
        for published, reason in (
            (None, "dependency_publication_clock_missing"),
            (datetime(2026, 10, 28, 11), "invalid_dependency_publication_clock"),
        ):
            with self.subTest(published=published):
                changed = replace(self.claims[0], published_at=published)
                result = reviewed_relay_edges([changed, self.claims[1]], [fixture()])
                self.assertEqual(result.edges, ())
                self.assertIn(reason, result.rejected[0])

    def test_unsupported_relation_and_conflicting_claim_ids_fail_closed(self):
        result = reviewed_relay_edges(self.claims, [fixture(relation="guessed_similar_text")])
        self.assertEqual(result.edges, ())
        self.assertIn("unsupported_dependency_relation", result.rejected[0])
        altered = replace(self.claims[0], source_group="different")
        result = reviewed_relay_edges(self.claims + [altered], [fixture()])
        self.assertEqual(result.edges, ())
        self.assertEqual(result.rejected, ("conflicting_claim_identifiers",))
