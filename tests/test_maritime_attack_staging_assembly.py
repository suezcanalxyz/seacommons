# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging assembly regressions using source-faithful persisted-row fixtures."""
from unittest import TestCase

from core.intel.maritime_attack_staging_assembly import assemble_staging_review
from test_maritime_attack_staging_preview import fixtures


class StagingAssemblyTests(TestCase):
    def test_contship_jet_remains_review_only(self):
        records, rows = fixtures()
        result = assemble_staging_review(records, rows, {}, now_utc="2026-11-03T12:00:00Z")
        self.assertEqual(len(result), 6)
        jet = result[0]
        self.assertEqual(jet["preview"]["vessel_name_as_reported"], "CONTSHIP JET")
        self.assertEqual(jet["routing"]["destination"], "review_queue")
        self.assertFalse(jet["publication_allowed"])
        self.assertIsNone(jet["origin_review"])

    def test_origin_review_does_not_promote_candidate(self):
        records, rows = fixtures()
        from datetime import datetime
        observation_id = rows[0].observation_id
        report = {
            "publisher": "BG_MOD", "publisher_item_id": "news9664",
            "source_url": "https://www.mod.bg/news9664",
            "origin_key": "ministry-report", "origin_verified": True,
            "retrieved_at_utc": "2026-11-02T12:00:00Z",
            "evidence_kind": "authority",
        }
        result = assemble_staging_review(
            records, rows, {observation_id: [report]},
            now_utc="2026-11-03T12:00:00Z",
        )
        self.assertEqual(result[0]["origin_review"]["independent_testimonial_origins"], 1)
        self.assertEqual(result[0]["routing"]["destination"], "review_queue")

    def test_reject_foreign_report_mapping(self):
        records, rows = fixtures()
        with self.assertRaisesRegex(ValueError, "foreign_review_report"):
            assemble_staging_review(records, rows, {"obs:unknown": []}, now_utc="2026-11-03T12:00:00Z")
