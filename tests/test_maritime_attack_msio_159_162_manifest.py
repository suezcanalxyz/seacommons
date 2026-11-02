# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two primary-source candidates; never import secondary ship identities."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest import TestCase

from core.intel.maritime_attack_staging_manifest import (
    prepare_staging_bulletin_manifest,
)
from core.intel.official_maritime_bulletin import prepare_official_bulletin

ROOT = Path(__file__).resolve().parents[1] / "docs/research"


def _manifest(number: int) -> dict:
    return json.loads((ROOT / (
        f"maritime-attack-mscio-{number}-2026-11-02.json"
    )).read_text(encoding="utf-8"))


class MSCIO159And162Tests(TestCase):
    def test_source_envelopes_remain_unidentified_unlocated_unverified(self):
        for number, clock, source_path in (
            (159, "2026-10-29T22:12:00+00:00", "/alerts/195"),
            (162, "2026-10-30T18:00:00+00:00", "/alerts/198"),
        ):
            with self.subTest(bulletin=number):
                (item,) = prepare_staging_bulletin_manifest(_manifest(number))
                self.assertEqual(item.bulletin.occurred_at.isoformat(), clock)
                self.assertTrue(item.bulletin.event_time_approximate)
                self.assertIsNone(item.bulletin.reported_time_uncertainty_minutes)
                self.assertEqual(item.bulletin.source_url.split(".eu")[-1], source_path)
                self.assertEqual(item.bulletin.vessel_name, "")
                self.assertEqual(item.bulletin.imo, "")
                self.assertEqual(item.bulletin.mmsi, "")
                self.assertIsNone(item.bulletin.lat)
                self.assertIsNone(item.bulletin.lon)
                self.assertEqual(item.source_rights, "restricted_republication")
                self.assertFalse(item.origin_independence_verified)
                self.assertFalse(item.publication_allowed)
                self.assertFalse(item.envelope["provenance"]["origin_authority_verified"])
                self.assertFalse(item.envelope["provenance"]["attack_corroboration_allowed"])
                self.assertEqual(item.envelope["subject_refs"], [])

    def test_source_locked_identity_rejects_secondary_reuters_ship_id(self):
        for number in (159, 162):
            (item,) = prepare_staging_bulletin_manifest(_manifest(number))
            for patch in (
                {"vessel_name": "LOUISE 1"},
                {"imo": "9290323"},
                {"mmsi": "636019532"},
            ):
                expected = self.assertRaisesRegex(ValueError, "does not identify vessel")
                with self.subTest(bulletin=number, patch=patch), expected:
                    prepare_official_bulletin(replace(item.bulletin, **patch))

    def test_known_bulletin_cannot_be_swapped_onto_other_page(self):
        (item,) = prepare_staging_bulletin_manifest(_manifest(159))
        for patch in (
            {"source_url": "https://mscio.eu/alerts/198"},
            {"source_url": "https://mscio.eu/alerts/195?ship=LOUISE1"},
            {"source_url": "https://mscio.eu/alerts/195#update"},
            {"bulletin_id": "162/26"},
        ):
            expected = self.assertRaisesRegex(ValueError, "ID/URL mismatch")
            with self.subTest(patch=patch), expected:
                prepare_official_bulletin(replace(item.bulletin, **patch))

    def test_both_candidates_are_distinct_but_not_two_verified_witnesses(self):
        combined = _manifest(159)
        combined["records"] += _manifest(162)["records"]
        records = prepare_staging_bulletin_manifest(combined)
        self.assertEqual(len(records), 2)
        self.assertNotEqual(records[0].envelope["source_id"],
                            records[1].envelope["source_id"])
        self.assertEqual({r.envelope["provenance"]["original_report_id"]
                          for r in records}, {"MSCIO:159/26", "MSCIO:162/26"})
        self.assertFalse(any(r.origin_independence_verified for r in records))
        self.assertFalse(any(r.publication_allowed for r in records))
