# SPDX-License-Identifier: AGPL-3.0-or-later
"""Official 13 Oct Black Sea notices: two vessels, no invented UTC clock."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase

from core.intel.maritime_attack_staging_lineage import (
    build_staging_attack_lineage_review,
)
from core.intel.maritime_attack_staging_manifest import (
    prepare_staging_bulletin_manifest,
)

DOCS = Path(__file__).resolve().parents[1] / "docs/research"


def source(slug: str):
    path = DOCS / f"maritime-attack-bg-transport-{slug}-2026-11-02.json"
    return prepare_staging_bulletin_manifest(json.loads(path.read_text()))[0]


def preview(record):
    e = record.envelope
    p = e["provenance"]
    return {
        "staging_only": True,
        "publication_allowed": False,
        "independent_origins_verified": 0,
        "review_status": "candidate",
        "source_kind": "attack",
        "canonical_observation_id": "obs:" + p["original_report_id"],
        "original_report_id": p["original_report_id"],
        "source_url": e["source_url"],
        "event_time_precision": "day",
        "event_date": p["event_date"],
        "occurred_at_utc": None,
        "vessel_name_as_reported": p["vessel_name"],
        "vessel_imo_as_reported": "",
        "vessel_mmsi_as_reported": "",
        "reported_location": None,
    }


class BlackSeaOctoberOfficialSourceTests(TestCase):
    def test_two_distinct_attack_candidates_no_false_utc_or_identity(self):
        chelsea, dignity = source("chelsea-3"), source("hs-dignity")
        for record, name in ((chelsea, "CHELSEA-3"), (dignity, "HS Dignity")):
            with self.subTest(name=name):
                p = record.envelope["provenance"]
                self.assertEqual(p["bulletin_kind"], "attack")
                self.assertEqual(p["event_date"], "2026-10-13")
                self.assertEqual(p["event_time_precision"], "day")
                self.assertIsNone(p["occurred_at_utc"])
                self.assertEqual(p["vessel_name"], name)
                self.assertEqual(p["vessel_imo"], "")
                self.assertEqual(p["vessel_mmsi"], "")
                self.assertEqual(record.envelope["subject_refs"], [])
                self.assertFalse(record.publication_allowed)
                self.assertFalse(record.origin_independence_verified)
        self.assertNotEqual(
            chelsea.envelope["provenance"]["original_report_id"],
            dignity.envelope["provenance"]["original_report_id"],
        )
        self.assertEqual(chelsea.envelope["source_url"], dignity.envelope["source_url"])

    def test_one_ministry_page_does_not_merge_two_different_vessels(self):
        chelsea, dignity = source("chelsea-3"), source("hs-dignity")
        first, second = preview(chelsea), preview(dignity)
        independent = build_staging_attack_lineage_review([first, second])
        self.assertEqual(independent["independent_origins_verified"], 0)
        self.assertEqual(independent["provisional_origin_groups"], 2)
        with self.assertRaisesRegex(ValueError, "lineage_vessel_name_conflict"):
            build_staging_attack_lineage_review(
                [first, second],
                [{
                    "left_report_id": first["original_report_id"],
                    "right_report_id": second["original_report_id"],
                    "basis": "same_original_document",
                    "supporting_source_url": first["source_url"],
                }],
            )
