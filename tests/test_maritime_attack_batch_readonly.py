# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure regression tests for bounded batch audits; no DB or network."""
import ast
from pathlib import Path
import unittest
from types import SimpleNamespace as Row

from core.intel.maritime_attack_batch_readonly import (
    audit_attack_episodes_independence,
)


def episode(key, *ids, family="maritime_attack_episode"):
    return Row(
        episode_id=key, episode_family=family,
        verification_status="multi_source_corroborated",
        independence_groups=["navy", "independent_rescue"],
        observation_ids=list(ids),
    )


def obs(key, authority, report, *, verified=True):
    return Row(
        observation_id=key, service="intel",
        source_url="https://example.org/" + key,
        provenance={
            "origin_authority_verified": verified,
            "originating_authority_id": authority,
            "original_report_id": report,
        },
    )


def edge(child, parent):
    return Row(
        from_observation_id=child, to_observation_id=parent,
        relation="derived_from", method_version="operator_verified",
        confidence=0.99,
    )


def batch(episodes, observations, edges=()):
    calls = {"observations": [], "lineage": []}

    def get_observations(ids):
        calls["observations"].append(ids)
        return [row for row in observations if row.observation_id in ids]

    def get_lineage(ids):
        calls["lineage"].append(ids)
        return [row for row in edges if row.from_observation_id in ids]

    return audit_attack_episodes_independence(
        episodes, get_observations, get_lineage,
    ), calls


class BatchAuditTests(unittest.TestCase):
    def test_two_episodes_one_observation_fetch(self):
        cases = [episode("jet", "mod", "rescue"),
                 episode("hormuz", "ukmto", "independent_witness")]
        rows = [obs("mod", "mod", "a"), obs("rescue", "mrcc", "b"),
                obs("ukmto", "ukmto", "c"),
                obs("independent_witness", "eyewitness", "d")]
        result, calls = batch(cases, rows)
        self.assertTrue(all(audit.verified for audit in result.values()))
        self.assertEqual(len(calls["observations"]), 1)

    def test_republished_reports_fail_without_poisoning_other_episode(self):
        cases = [episode("jet", "news1", "news2"),
                 episode("hormuz", "ukmto", "witness")]
        rows = [obs("news1", "publisher1", "a"), obs("news2", "publisher2", "b"),
                obs("ukmto", "ukmto", "c"), obs("witness", "witness", "d")]
        edges = [edge("news1", "agency"), edge("news2", "agency")]
        result, _ = batch(cases, rows, edges)
        self.assertFalse(result["jet"].verified)
        self.assertEqual(result["jet"].reason, "shared_original_source")
        self.assertTrue(result["hormuz"].verified)

    def test_shared_lineage_across_intermediate_nodes(self):
        rows = [obs("a", "news_a", "1"), obs("b", "news_b", "2")]
        edges = [edge("a", "wire_a"), edge("wire_a", "original"),
                 edge("b", "wire_b"), edge("wire_b", "original")]
        result, calls = batch([episode("jet", "a", "b")], rows, edges)
        self.assertFalse(result["jet"].verified)
        self.assertGreaterEqual(len(calls["lineage"]), 2)

    def test_uncorroborated_attack_skips_all_batch_reads(self):
        case = episode("jet", "mod", "rescue")
        case.verification_status = "single_source"
        result, calls = batch([case], [])
        self.assertEqual(result["jet"].reason, "canonical_verification_incomplete")
        self.assertEqual(calls["observations"], [])
        self.assertEqual(calls["lineage"], [])

    def test_duplicate_canonical_groups_skip_all_batch_reads(self):
        case = episode("jet", "mod", "rescue")
        case.independence_groups = ["Bulgarian Navy", " bulgarian navy "]
        result, calls = batch([case], [])
        self.assertEqual(result["jet"].reason, "canonical_verification_incomplete")
        self.assertFalse(calls["observations"])
        self.assertFalse(calls["lineage"])

    def test_separator_alias_groups_skip_batch_database_reads(self):
        case = episode("jet", "mod", "rescue")
        case.independence_groups = ["Bulgarian_Navy", "bulgarian navy"]
        result, calls = batch([case], [])
        self.assertEqual(result["jet"].reason, "canonical_verification_incomplete")
        self.assertFalse(calls["observations"])
        self.assertFalse(calls["lineage"])

    def test_mixed_batch_only_fetches_eligible_attack(self):
        blocked = episode("blocked", "a", "b")
        blocked.verification_status = "candidate"
        eligible = episode("eligible", "mod", "rescue")
        result, calls = batch(
            [blocked, eligible],
            [obs("mod", "navy", "navy-1"), obs("rescue", "mrcc", "mrcc-2")],
        )
        self.assertEqual(result["blocked"].reason, "canonical_verification_incomplete")
        self.assertTrue(result["eligible"].verified)
        self.assertEqual(calls["observations"], [("mod", "rescue")])
        self.assertTrue(all("a" not in ids and "b" not in ids for ids in calls["lineage"]))

    def test_missing_observation_fails_closed(self):
        result, _ = batch([episode("jet", "a", "b")], [obs("a", "a", "1")])
        self.assertEqual(result["jet"].reason, "missing_or_duplicate_observations")

    def test_invalid_episode_ids_skip_queries(self):
        result, calls = batch([episode("", "a", "b")], [])
        self.assertFalse(next(iter(result.values())).verified)
        self.assertFalse(calls["observations"])
        self.assertFalse(calls["lineage"])

    def test_duplicate_episode_ids_block_whole_batch(self):
        cases = [episode("same", "a", "b"), episode("same", "c", "d")]
        result, calls = batch(cases, [])
        self.assertEqual(result["same"].reason, "invalid_or_duplicate_episode_id")
        self.assertEqual(calls["observations"], [])

    def test_invalid_observation_ids_skip_queries(self):
        result, calls = batch([episode("jet", "a", "a")], [])
        self.assertEqual(result["jet"].reason, "invalid_observation_ids")
        self.assertFalse(calls["observations"])

    def test_unexpected_observation_blocks_batch(self):
        result = audit_attack_episodes_independence(
            [episode("jet", "a", "b")],
            lambda ids: [obs("a", "a", "1"), obs("alien", "x", "2")],
            lambda ids: [],
        )
        self.assertEqual(result["jet"].reason, "batch_unexpected_observation")

    def test_duplicate_observation_rows_cannot_inflate_proof(self):
        result = audit_attack_episodes_independence(
            [episode("jet", "a", "b")],
            lambda ids: [obs("a", "a", "1"), obs("a", "a", "1"), obs("b", "b", "2")],
            lambda ids: [],
        )
        self.assertEqual(result["jet"].reason, "batch_observation_overflow")

    def test_invalid_lineage_row_blocks_all(self):
        result = audit_attack_episodes_independence(
            [episode("jet", "a", "b")],
            lambda ids: [obs("a", "a", "1"), obs("b", "b", "2")],
            lambda ids: [edge("not_requested", "root")],
        )
        self.assertEqual(result["jet"].reason, "batch_invalid_lineage_row")

    def test_cyclic_lineage_is_not_independent(self):
        result, _ = batch(
            [episode("jet", "a", "b")],
            [obs("a", "a", "1"), obs("b", "b", "2")],
            [edge("a", "x"), edge("x", "a")],
        )
        self.assertEqual(result["jet"].reason, "lineage_cycle_detected")

    def test_unverified_origin_blocks(self):
        result, _ = batch([episode("jet", "a", "b")],
                          [obs("a", "a", "1", verified=False), obs("b", "b", "2")])
        self.assertEqual(result["jet"].reason, "origin_not_verified")

    def test_humanitarian_never_relabelled(self):
        result, calls = batch([episode("drift", "a", "b", family="gap_episode")], [])
        self.assertEqual(result["drift"].reason, "not_attack_episode")
        self.assertFalse(calls["observations"])

    def test_batch_limit_fails_closed(self):
        result, calls = batch(
            [episode(str(i), f"a{i}", f"b{i}") for i in range(9)], [])
        self.assertEqual(len(result), 9)
        self.assertTrue(all(x.reason == "batch_episode_limit" for x in result.values()))
        self.assertFalse(calls["observations"])

    def test_play_catalog_and_dossiers_invoke_real_audit(self):
        path = Path(__file__).resolve().parents[1] / "apps/api/core/api/routes/play.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        expected = {
            "_compute_play_catalog": "audit_attack_episodes_independence_db",
            "_public_episode_dossier": "_audit_attack_projection_db",
            "play_incident_timeline": "_audit_attack_projection_db",
        }
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name not in expected:
                continue
            called = {
                child.func.id for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
            }
            self.assertIn(expected.pop(node.name), called, node.name)
        self.assertEqual(expected, {})

    def test_catalog_limits_audits_to_visible_episodes(self):
        path = Path(__file__).resolve().parents[1] / "apps/api/core/api/routes/play.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_compute_play_catalog"
        )
        visible_filter = [
            node for node in ast.walk(function)
            if isinstance(node, ast.Compare)
            and any(isinstance(item, ast.Name) and item.id == "visible_episode_ids"
                    for item in node.comparators)
        ]
        self.assertTrue(visible_filter, "Private episodes must not trigger catalog lineage reads")

    def test_dossier_evidence_audit_uses_effective_corroboration(self):
        path = Path(__file__).resolve().parents[1] / "apps/api/core/api/routes/play.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        expected = {"_public_episode_dossier", "play_incident_timeline"}
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name not in expected:
                continue
            calls = [
                child for child in ast.walk(node)
                if isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "_evidence_audit"
            ]
            self.assertEqual(len(calls), 1, node.name)
            keyword = next(
                (k for k in calls[0].keywords if k.arg == "independent_lineages"),
                None,
            )
            self.assertIsNotNone(keyword, node.name)
            self.assertIsInstance(keyword.value, ast.IfExp, node.name)
            expected.remove(node.name)
        self.assertFalse(expected)

    def test_overlarge_lineage_fails_closed(self):
        result = audit_attack_episodes_independence(
            [episode("jet", "a", "b")],
            lambda ids: [obs("a", "a", "1"), obs("b", "b", "2")],
            lambda ids: [edge("a", f"ancestor_{i}") for i in range(2050)]
            if "a" in ids else [],
        )
        self.assertEqual(result["jet"].reason, "batch_node_limit")

    def test_unknown_relation_does_not_become_proof(self):
        result = audit_attack_episodes_independence(
            [episode("jet", "a", "b")],
            lambda ids: [obs("a", "a", "1"), obs("b", "b", "2")],
            lambda ids: [Row(from_observation_id="a", to_observation_id="b",
                             relation="quotes", method_version="unverified",
                             confidence=0.1)] if "a" in ids else [],
        )
        self.assertEqual(result["jet"].reason, "unverified_lineage_edge")

    def test_no_episodes_does_not_fetch(self):
        result, calls = batch([], [])
        self.assertEqual(result, {})
        self.assertFalse(calls["observations"])


if __name__ == "__main__":
    unittest.main()
