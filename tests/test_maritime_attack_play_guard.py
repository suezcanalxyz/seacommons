# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging regressions for attack corroboration in PLAY, with no DB access."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from core.intel.maritime_attack_play_guard import (
    episode_corroborated_for_play, has_distinct_independence_groups,
)


def episode(family="maritime_attack_episode", status="multi_source_corroborated",
            groups=None):
    return SimpleNamespace(
        episode_family=family,
        verification_status=status,
        independence_groups=["bulgarian_mod", "independent_rescue"] if groups is None else groups,
    )


class AttackPlayGuardTests(unittest.TestCase):
    def test_contship_jet_valid_two_lineages_is_only_a_label(self):
        self.assertTrue(episode_corroborated_for_play(episode()))

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
