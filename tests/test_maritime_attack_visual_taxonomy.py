# SPDX-License-Identifier: AGPL-3.0-or-later
"""Attack UI taxonomy: canonical-only classification and humanitarian separation.

Pure unit/static checks: no VM, DB credentials, live feeds or publication.
"""
from pathlib import Path
import ast
import unittest

from core.domain.incident_taxonomy import taxonomy_fields, STABLE_MARITIME_INCIDENT_TYPES
from core.domain.visual_category import (
    CATEGORY_COLORS, classify_visual_category, visual_category_fields,
)

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ("attack_episode", "maritime_attack_episode", "maritime_attack")


class MaritimeAttackVisualTaxonomyTests(unittest.TestCase):
    def test_canonical_attack_episode_is_separate_from_piracy_and_sar(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                meta = {"episode_family": family}
                result = taxonomy_fields(event_type="news", maritime_domain="security", metadata=meta)
                self.assertEqual(result["main_category"], "maritime")
                self.assertEqual(result["incident_type"], "maritime_attack")
                self.assertIn(result["incident_type"], STABLE_MARITIME_INCIDENT_TYPES)
                visual = visual_category_fields(event_type="news", maritime_domain="security", metadata=meta)
                self.assertEqual(visual["visual_category"], "maritime_attack")
                self.assertEqual(visual["visual_color"], "#ff6b35")
                self.assertNotEqual(visual["visual_color"], CATEGORY_COLORS["distress"])
                self.assertNotEqual(visual["visual_color"], CATEGORY_COLORS["piracy"])

    def test_unverified_report_or_ais_gap_is_not_an_attack(self):
        for event_type, meta in (
            ("news", {"title": "SHIP ATTACKED", "linked_mmsi": "636019532"}),
            ("ais_anomaly", {"anomaly_type": "ais_gap", "linked_mmsi": "636019532"}),
            ("ais_anomaly", {"anomaly_type": "stationary_anomaly", "linked_mmsi": "636019532"}),
        ):
            with self.subTest(event_type=event_type, meta=meta):
                tax = taxonomy_fields(event_type=event_type, maritime_domain="security", metadata=meta)
                self.assertNotEqual(tax["incident_type"], "maritime_attack")
                self.assertNotEqual(classify_visual_category(
                    event_type=event_type, maritime_domain="security", metadata=meta,
                ), "maritime_attack")

    def test_humanitarian_remains_humanitarian_even_with_bad_family_metadata(self):
        meta = {"episode_family": "maritime_attack_episode"}
        tax = taxonomy_fields(event_type="distress", maritime_domain="sar",
                              humanitarian_case_type="distress", metadata=meta)
        self.assertEqual(tax["main_category"], "humanitarian")
        self.assertEqual(tax["incident_type"], "distress")
        self.assertNotEqual(classify_visual_category(
            event_type="distress", maritime_domain="sar",
            humanitarian_case_type="distress", metadata=meta,
        ), "maritime_attack")

    def test_alarm_phone_priority_remains_red(self):
        self.assertEqual(classify_visual_category(
            source="Alarm Phone", event_type="news", maritime_domain="security",
            metadata={"episode_family": "attack_episode"},
        ), "humanitarian_alarm_phone")

    def test_play_projection_uses_canonical_family_not_headline(self):
        path = ROOT / "apps/api/core/api/routes/play.py"
        code = path.read_text(encoding="utf-8")
        ast.parse(code)
        self.assertIn('is_attack_episode = str(episode.episode_family or "") in _ATTACK_FAMILIES', code)
        self.assertIn('event_meta["episode_family"] = str(episode.episode_family)', code)
        self.assertIn('taxonomy.update(visual_category_fields(', code)

    def test_frontend_selector_and_palette_match_backend(self):
        main = (ROOT / "apps/web/src/main.jsx").read_text(encoding="utf-8")
        categories = (ROOT / "apps/web/src/features/intel/categories.js").read_text(encoding="utf-8")
        self.assertIn("key: 'maritime_attack', label: 'Reported attacks', groupKey: 'signal_type_maritime_attack'", main)
        self.assertIn("key: 'maritime_attack', label: 'Reported maritime attack', color: '#ff6b35'", categories)
        self.assertIn("properties.incident_type === \"maritime_attack\"", categories)
        self.assertIn("maritime_attack: 'maritime_attack'", categories)
        self.assertEqual(CATEGORY_COLORS["maritime_attack"], "#ff6b35")


if __name__ == "__main__":
    unittest.main()
