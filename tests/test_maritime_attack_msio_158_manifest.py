# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression: October MSCIO 158 is an unnamed candidate, never a verified hit."""
import json
from pathlib import Path
from unittest import TestCase

from core.intel.maritime_attack_staging_manifest import (
    prepare_staging_bulletin_manifest,
)

MANIFEST = (Path(__file__).resolve().parents[1] / "docs/research"
            / "maritime-attack-mscio-158-2026-11-02.json")


class MSCIO158StagingTests(TestCase):
    def test_original_precision_and_identity_absence_are_preserved(self):
        records = prepare_staging_bulletin_manifest(json.loads(MANIFEST.read_text()))
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.bulletin.issuer, "MSCIO")
        self.assertEqual(record.bulletin.bulletin_id, "158/26")
        self.assertEqual(record.bulletin.vessel_name, "")
        self.assertEqual(record.bulletin.imo, "")
        self.assertEqual(record.bulletin.mmsi, "")
        self.assertTrue(record.bulletin.event_time_approximate)
        self.assertIsNone(record.bulletin.lat)
        self.assertIsNone(record.bulletin.lon)
        self.assertEqual(record.source_rights, "restricted_republication")
        self.assertFalse(record.origin_independence_verified)
        self.assertFalse(record.publication_allowed)
        self.assertFalse(record.envelope["provenance"]["attack_corroboration_allowed"])
