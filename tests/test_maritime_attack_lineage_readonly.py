# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging regression tests for bounded, read-only maritime lineage loading."""
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from core.intel.maritime_attack_correlation import IncidentClaim, VesselRef
from core.intel.maritime_attack_lineage_readonly import (
    correlate_with_verified_lineage, load_verified_lineage,
)

UTC = timezone.utc
JET = VesselRef("9348625", "636019532", "CONTSHIP JET")
OCCURRED = datetime(2026, 10, 28, 10, tzinfo=UTC)


def claim(identifier, authority):
    return IncidentClaim(
        claim_id=identifier, kind="attack", occurred_at=OCCURRED,
        source_group=authority, source_url="https://example.org/" + identifier,
        vessel=JET, origin_report_id="original:" + identifier,
    )


def edge(derived, original, *, relation="derived_from",
         method="v0_exact_payload_hash_match", confidence=0.9):
    return SimpleNamespace(
        from_observation_id=derived, to_observation_id=original,
        relation=relation, method_version=method, confidence=confidence,
    )


def reader(rows, calls=None):
    def fetch(frontier):
        if calls is not None:
            calls.append(frontier)
        return [r for r in rows if r.from_observation_id in frontier]
    return fetch


class MaritimeAttackLineageReadOnlyTests(unittest.TestCase):
    def test_no_lineage_preserves_two_verified_origins(self):
        result = correlate_with_verified_lineage(
            JET, [claim("mod", "mod"), claim("mrcc", "mrcc")], reader([]))
        self.assertEqual(result.status, "corroborated")
        self.assertFalse(result.publication_allowed)

    def test_direct_syndication_blocks_false_independence(self):
        result = correlate_with_verified_lineage(
            JET, [claim("mod", "mod"), claim("news", "news")],
            reader([edge("news", "mod")]))
        self.assertEqual(result.status, "candidate")
        self.assertEqual(len(result.independent_groups), 1)

    def test_intermediate_not_in_claims_still_collapses_origins(self):
        rows = [
            edge("news_a", "wire_a"), edge("wire_a", "original"),
            edge("news_b", "wire_b"), edge("wire_b", "original"),
        ]
        result = correlate_with_verified_lineage(
            JET, [claim("news_a", "publisher_a"), claim("news_b", "publisher_b")],
            reader(rows))
        self.assertEqual(result.status, "candidate")
        self.assertEqual(len(result.independent_groups), 1)

    def test_unverified_quotation_fails_closed(self):
        result = correlate_with_verified_lineage(
            JET, [claim("mod", "mod"), claim("news", "news")],
            reader([edge("news", "mod", relation="quotes")]))
        self.assertEqual(result.status, "candidate")
        self.assertIn("unverified_lineage_edge", result.contradicting)

    def test_low_confidence_fails_closed(self):
        result = correlate_with_verified_lineage(
            JET, [claim("mod", "mod"), claim("news", "news")],
            reader([edge("news", "mod", confidence=0.5)]))
        self.assertEqual(result.status, "candidate")
        self.assertIn("unverified_lineage_edge", result.contradicting)

    def test_depth_limit_fails_closed_instead_of_promoting(self):
        result = correlate_with_verified_lineage(
            JET, [claim("mod", "mod"), claim("news", "news")],
            reader([edge("news", "intermediate"), edge("intermediate", "mod")]),
            max_depth=1)
        self.assertEqual(result.status, "candidate")
        self.assertIn("lineage_depth_limit", result.contradicting)

    def test_node_limit_fails_closed(self):
        result = correlate_with_verified_lineage(
            JET, [claim("mod", "mod"), claim("news", "news")],
            reader([edge("news", "intermediate")]), max_nodes=2)
        self.assertEqual(result.status, "candidate")
        self.assertIn("lineage_node_limit", result.contradicting)

    def test_edge_limit_fails_closed(self):
        rows = [edge("news", "parent1"), edge("news", "parent2")]
        result = correlate_with_verified_lineage(
            JET, [claim("mod", "mod"), claim("news", "news")],
            reader(rows), max_edges=1)
        self.assertEqual(result.status, "candidate")
        self.assertIn("lineage_edge_limit", result.contradicting)

    def test_cycle_terminates_and_cannot_create_independence(self):
        result = correlate_with_verified_lineage(
            JET, [claim("mod", "mod"), claim("news", "news")],
            reader([edge("news", "mod"), edge("mod", "news")]))
        self.assertEqual(result.status, "candidate")
        self.assertEqual(len(result.independent_groups), 1)

    def test_read_scope_only_claims_and_ancestors(self):
        calls = []
        lineage = load_verified_lineage(
            ["mod", "news"], reader([edge("news", "mod"),
                                    edge("unrelated", "other")], calls))
        self.assertTrue(lineage.complete)
        self.assertEqual(lineage.edges, (("news", "mod"),))
        self.assertEqual(calls, [("mod", "news")])

    def test_empty_claims_do_not_query_database(self):
        calls = []
        result = correlate_with_verified_lineage(JET, [], reader([], calls))
        self.assertEqual(result.status, "no_match")
        self.assertEqual(calls, [])

    def test_database_read_failure_is_not_silenced(self):
        def unavailable(_frontier):
            raise RuntimeError("database unavailable")
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            correlate_with_verified_lineage(
                JET, [claim("mod", "mod"), claim("mrcc", "mrcc")], unavailable)


if __name__ == "__main__":
    unittest.main()
