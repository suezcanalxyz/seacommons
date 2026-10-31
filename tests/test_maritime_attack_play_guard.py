# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging regressions for attack corroboration in PLAY, with no DB access."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from core.intel.maritime_attack_play_guard import (
    episode_corroborated_for_play, has_distinct_independence_groups,
)


_DEFAULT_GROUPS = object()


def episode(family="maritime_attack_episode", status="multi_source_corroborated",
            groups=_DEFAULT_GROUPS):
    return SimpleNamespace(
        episode_family=family,
        verification_status=status,
        independence_groups=(
            ["bulgarian_mod", "independent_rescue"]
            if groups is _DEFAULT_GROUPS else groups
        ),
    )


class AttackPlayGuardTests(unittest.TestCase):
    def test_contship_jet_two_labels_without_audit_fail_closed(self):
        self.assertFalse(episode_corroborated_for_play(episode()))

    def test_contship_jet_verified_audit_allows_display_label_only(self):
        self.assertTrue(episode_corroborated_for_play(
            episode(), independence_verified=True))

    def test_truthy_non_boolean_audit_is_rejected(self):
        self.assertFalse(episode_corroborated_for_play(
            episode(), independence_verified=1))

    def test_attack_single_source_status_is_not_corroborated(self):
        self.assertFalse(episode_corroborated_for_play(
            episode(status="single_source_observed")
        ))

    def test_attack_contested_status_is_not_corroborated(self):
        self.assertFalse(episode_corroborated_for_play(
            episode(status="contested")
        ))

    def test_attack_two_reprints_of_same_lineage_are_not_independent(self):
        self.assertFalse(episode_corroborated_for_play(
            episode(groups=["UKMTO", " ukmto "])
        ))

    def test_attack_two_labels_without_second_lineage_are_not_enough(self):
        self.assertFalse(episode_corroborated_for_play(
            episode(groups=["bulgarian_mod", "bulgarian_mod"])
        ))

    def test_attack_only_one_lineage_is_not_corroborated(self):
        self.assertFalse(episode_corroborated_for_play(
            episode(groups=["bulgarian_mod"])
        ))

    def test_attack_malformed_groups_fail_closed(self):
        for groups in (None, [], ["source_a", 9, "source_b"],
                       ["source_a", "", "source_b"], "source_a,source_b"):
            with self.subTest(groups=groups):
                self.assertFalse(episode_corroborated_for_play(
                    episode(groups=groups)
                ))

    def test_attack_family_aliases_all_use_strict_guard(self):
        for family in ("attack_episode", "maritime_attack_episode", "maritime_attack"):
            with self.subTest(family=family):
                self.assertFalse(episode_corroborated_for_play(
                    episode(family=family, status="single_source_observed")
                ))

    def test_unrelated_episode_projection_preserves_legacy_semantics(self):
        self.assertTrue(episode_corroborated_for_play(
            episode(family="gap_episode", status="single_source_observed",
                    groups=["ais_sensor", "derived_feed"])
        ))

    def test_missing_episode_is_never_corroborated(self):
        self.assertFalse(episode_corroborated_for_play(None))

    def test_lineage_group_casefold_and_whitespace(self):
        self.assertFalse(has_distinct_independence_groups(
            [" Bulgarian MOD ", "bulgarian mod"]
        ))
        self.assertTrue(has_distinct_independence_groups(
            ["bulgarian_mod", "independent_rescue"]
        ))

    @staticmethod
    def _actual_play_audit_function():
        # Exercise the real route function without importing FastAPI or
        # opening a database. Compile only its AST with the pure guard.
        path = Path(__file__).resolve().parents[1] / "apps/api/core/api/routes/play.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        node = next(
            item for item in tree.body
            if isinstance(item, ast.FunctionDef)
            and item.name == "_apply_attack_provenance_audit"
        )
        isolated = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
        namespace = {
            "_ATTACK_FAMILIES": frozenset({
                "attack_episode", "maritime_attack_episode", "maritime_attack",
            }),
            "episode_corroborated_for_play": episode_corroborated_for_play,
            "Any": object,
        }
        exec(compile(isolated, str(path), "exec"), namespace)
        return namespace["_apply_attack_provenance_audit"]

    def test_play_failed_audit_does_not_leak_canonical_corroborated_status(self):
        projection = {
            "verification_status": "multi_source_corroborated",
            "independence_groups": ["bulgarian_mod", "bulgarian_transport"],
            "corroborated": False, "evidence_stage": "derived",
        }
        result = self._actual_play_audit_function()(projection, episode(), None)
        self.assertFalse(result["corroborated"])
        self.assertEqual(result["verification_status"], "provenance_review_required")
        self.assertEqual(result["canonical_verification_status"], "multi_source_corroborated")
        self.assertEqual(result["independence_groups"], [])
        self.assertEqual(result["reported_independence_groups"],
                         ["bulgarian_mod", "bulgarian_transport"])
        self.assertEqual(result["provenance_audit_reason"], "audit_unavailable")

    def test_play_verified_audit_keeps_corroboration_and_status(self):
        projection = {
            "verification_status": "multi_source_corroborated",
            "independence_groups": ["bulgarian_mod", "independent_rescue"],
            "corroborated": False, "evidence_stage": "derived",
        }
        audit = SimpleNamespace(verified=True, reason="")
        result = self._actual_play_audit_function()(projection, episode(), audit)
        self.assertTrue(result["corroborated"])
        self.assertEqual(result["verification_status"], "multi_source_corroborated")
        self.assertEqual(result["evidence_stage"], "corroborated")
        self.assertEqual(result["provenance_audit_status"], "verified")
        self.assertNotIn("reported_independence_groups", result)

    def test_play_contested_attack_remains_contested(self):
        projection = {
            "verification_status": "contested",
            "independence_groups": ["navy", "news"],
            "evidence_stage": "derived",
        }
        result = self._actual_play_audit_function()(
            projection, episode(status="contested"),
            SimpleNamespace(verified=False, reason="shared_original_source"),
        )
        self.assertEqual(result["verification_status"], "contested")
        self.assertEqual(result["provenance_audit_reason"], "shared_original_source")
        self.assertFalse(result["independence_groups"])

    def test_play_humanitarian_projection_unchanged(self):
        projection = {
            "verification_status": "multi_source_corroborated",
            "independence_groups": ["source_a", "source_b"],
            "evidence_stage": "corroborated",
        }
        result = self._actual_play_audit_function()(
            projection, episode(family="gap_episode"), None,
        )
        self.assertIs(result, projection)
        self.assertNotIn("canonical_verification_status", result)

    def test_both_play_projection_paths_use_strict_guard(self):
        # A lightweight integration contract without importing FastAPI or DB.
        path = Path(__file__).resolve().parents[1] / "apps/api/core/api/routes/play.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {"_episode_projection", "_investigation_projection"}
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name not in names:
                continue
            calls = [
                child for child in ast.walk(node)
                if isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "episode_corroborated_for_play"
            ]
            self.assertEqual(len(calls), 1, node.name)
            names.remove(node.name)
        self.assertFalse(names, f"Missing projection guards: {names}")


if __name__ == "__main__":
    unittest.main()
