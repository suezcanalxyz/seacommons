# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed tests for canonical attack provenance, no database access."""
import unittest
from types import SimpleNamespace

from core.intel.maritime_attack_independence_readonly import (
    audit_attack_episode_independence,
)


def episode(**changes):
    values = dict(
        episode_family="maritime_attack_episode",
        verification_status="multi_source_corroborated",
        independence_groups=["navy", "rescue"],
        observation_ids=["mod", "mrcc"],
    )
    values.update(changes)
    return SimpleNamespace(**values)


def observation(identifier, authority, document, url=None, *, verified=True, service="intel"):
    return SimpleNamespace(
        observation_id=identifier, service=service,
        source_url=url or "https://example.org/" + identifier,
        provenance={
            "origin_authority_verified": verified,
            "originating_authority_id": authority,
            "original_report_id": document,
        },
    )


def edge(child, parent, method="operator_verified", relation="derived_from"):
    return SimpleNamespace(
        from_observation_id=child, to_observation_id=parent,
        relation=relation, method_version=method, confidence=0.99,
    )


def audit(rows, edges=(), ep=None):
    return audit_attack_episode_independence(
        ep or episode(),
        lambda ids: [row for row in rows if row.observation_id in ids],
        lambda ids: [row for row in edges if row.from_observation_id in ids],
    )


class IndependenceAuditTests(unittest.TestCase):
    def test_two_independent_verified_origins(self):
        result = audit([
            observation("mod", "bulgarian_navy", "mod-2026-28"),
            observation("mrcc", "independent_rescue", "rescue-2026-28"),
        ])
        self.assertTrue(result.verified)
        self.assertEqual(len(result.groups), 2)

    def test_two_labels_do_not_prove_independence(self):
        result = audit([
            observation("mod", "bulgarian_navy", "mod-2026-28"),
            observation("mrcc", "bulgarian_navy", "other-document"),
        ])
        self.assertFalse(result.verified)
        self.assertEqual(result.reason, "shared_original_source")

    def test_syndicated_articles_share_one_root(self):
        ep = episode(observation_ids=["news_a", "news_b"])
        rows = [
            observation("news_a", "publisher_a", "a"),
            observation("news_b", "publisher_b", "b"),
        ]
        edges = [edge("news_a", "wire_a"), edge("wire_a", "original"),
                 edge("news_b", "wire_b"), edge("wire_b", "original")]
        self.assertEqual(audit(rows, edges, ep).reason, "shared_original_source")

    def test_unverified_origin_fails_closed(self):
        rows = [
            observation("mod", "mod", "1", verified=False),
            observation("mrcc", "mrcc", "2"),
        ]
        self.assertEqual(audit(rows).reason, "origin_not_verified")

    def test_missing_observation_fails_closed(self):
        self.assertEqual(audit([observation("mod", "mod", "1")]).reason,
                         "missing_or_duplicate_observations")

    def test_humanitarian_is_not_relabelled_attack(self):
        rows = [observation("mod", "mod", "1", service="humanitarian"),
                observation("mrcc", "mrcc", "2")]
        self.assertEqual(audit(rows).reason, "humanitarian_domain_excluded")

    def test_cycle_blocks_even_distinct_authorities(self):
        rows = [observation("mod", "mod", "1"), observation("mrcc", "mrcc", "2")]
        self.assertEqual(audit(rows, [edge("mod", "x"), edge("x", "mod")]).reason,
                         "lineage_cycle_detected")

    def test_unverified_quotation_blocks(self):
        rows = [observation("mod", "mod", "1"), observation("mrcc", "mrcc", "2")]
        self.assertEqual(audit(rows, [edge("mrcc", "mod", relation="quotes")]).reason,
                         "unverified_lineage_edge")

    def test_same_url_not_two_sources(self):
        rows = [observation("mod", "mod", "1", "https://a.test/report?ref=1"),
                observation("mrcc", "mrcc", "2", "https://a.test/report?ref=2")]
        self.assertEqual(audit(rows).reason, "shared_original_source")

    def test_malformed_episode_labels_block_without_fetch(self):
        calls = []
        result = audit_attack_episode_independence(
            episode(independence_groups=["mod", " mod "]),
            lambda ids: calls.append(ids) or [],
            lambda ids: [],
        )
        self.assertFalse(result.verified)
        self.assertEqual(calls, [])

    def test_non_attack_episode_never_passes(self):
        self.assertEqual(audit([], ep=episode(episode_family="gap_episode")).reason,
                         "not_attack_episode")

    def test_duplicated_observation_ids_block_without_fetch(self):
        result = audit([], ep=episode(observation_ids=["mod", "mod"]))
        self.assertEqual(result.reason, "duplicate_observation_ids")


if __name__ == "__main__":
    unittest.main()
