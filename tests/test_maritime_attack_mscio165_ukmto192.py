# SPDX-License-Identifier: AGPL-3.0-or-later
"""MSCIO 165/26 and UKMTO 192-26: two notices, not two proven witnesses."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest import TestCase

from core.intel.maritime_attack_staging_manifest import prepare_staging_bulletin_manifest
from core.intel.maritime_attack_staging_lineage import build_staging_attack_lineage_review
from core.intel.official_maritime_bulletin import prepare_official_bulletin

ROOT = Path(__file__).resolve().parents[1] / "docs/research"
UKMTO_URL = "https://www.ukmto.org/-/media/ukmto/products/20261102-ukmto_warning-192-26.pdf"
MSCIO_URL = "https://mscio.eu/alerts/201"


def _record(source: str):
    path = ROOT / f"maritime-attack-{source}-2026-11-03.json"
    (record,) = prepare_staging_bulletin_manifest(
        json.loads(path.read_text(encoding="utf-8"))
    )
    return record


def _preview(record):
    env = record.envelope
    p = env["provenance"]
    return {
        "original_report_id": p["original_report_id"],
        "canonical_observation_id": env["source_id"],
        "source_url": env["source_url"],
        "source_kind": p["bulletin_kind"],
        "source_rights": record.source_rights,
        "source_checked_on_utc": record.source_checked_on_utc.isoformat(),
        "review_status": "candidate",
        "occurred_at_utc": p["occurred_at_utc"],
        "event_date": p["event_date"],
        "event_time_precision": p["event_time_precision"],
        "reported_time_uncertainty_minutes": p["reported_time_uncertainty_minutes"],
        "publication_date": p["publication_date"],
        "published_at_utc": p["published_at_utc"],
        "vessel_name_as_reported": p["vessel_name"],
        "vessel_imo_as_reported": p["vessel_imo"],
        "vessel_mmsi_as_reported": p["vessel_mmsi"],
        "reported_location": None,
        "independent_origins_verified": 0,
        "publication_allowed": False,
        "staging_only": True,
    }


def _link():
    return {
        "left_report_id": "UKMTO:192-26",
        "right_report_id": "MSCIO:165/26",
        "basis": "matching_event_details_unverified_origin",
        "supporting_source_url": UKMTO_URL,
    }


class GulfNovemberFirstPrimarySourceTests(TestCase):
    def test_both_primary_documents_keep_identifiers_and_geometry_unknown(self):
        ukmto, mscio = _record("ukmto-192"), _record("mscio-165")
        self.assertEqual(ukmto.envelope["provenance"]["original_report_id"], "UKMTO:192-26")
        self.assertEqual(mscio.envelope["provenance"]["original_report_id"], "MSCIO:165/26")
        self.assertEqual(ukmto.bulletin.occurred_at.isoformat(), "2026-11-01T23:47:00+00:00")
        self.assertEqual(mscio.bulletin.occurred_at.isoformat(), "2026-11-01T23:47:00+00:00")
        self.assertFalse(ukmto.bulletin.event_time_approximate)
        self.assertTrue(mscio.bulletin.event_time_approximate)
        self.assertIsNone(mscio.bulletin.reported_time_uncertainty_minutes)
        for record in (ukmto, mscio):
            with self.subTest(issuer=record.bulletin.issuer):
                self.assertEqual(record.bulletin.vessel_name, "")
                self.assertEqual(record.bulletin.imo, "")
                self.assertEqual(record.bulletin.mmsi, "")
                self.assertIsNone(record.bulletin.lat)
                self.assertIsNone(record.bulletin.lon)
                self.assertEqual(record.envelope["subject_refs"], [])
                self.assertFalse(record.origin_independence_verified)
                self.assertFalse(record.publication_allowed)
                self.assertFalse(record.envelope["provenance"]["attack_corroboration_allowed"])
        self.assertEqual(ukmto.source_rights, "public_with_attribution")
        self.assertEqual(mscio.source_rights, "restricted_republication")

    def test_secondary_vessel_identity_cannot_be_injected(self):
        for source in ("ukmto-192", "mscio-165"):
            item = _record(source)
            for patch in ({"vessel_name": "LOUISE 1"},
                          {"imo": "9348625"}, {"mmsi": "636019532"}):
                with self.subTest(source=source, patch=patch), self.assertRaisesRegex(
                    ValueError, "primary bulletin does not identify vessel"
                ):
                    prepare_official_bulletin(replace(item.bulletin, **patch))

    def test_report_id_cannot_be_swapped_with_another_url(self):
        for source, bad in (
            ("mscio-165", {"source_url": "https://mscio.eu/alerts/200"}),
            ("mscio-165", {"source_url": MSCIO_URL + "?vessel=x"}),
            ("mscio-165", {"bulletin_id": "164/26"}),
            ("ukmto-192", {"source_url": UKMTO_URL + "#ship"}),
            ("ukmto-192", {"bulletin_id": "191-26"}),
        ):
            with self.subTest(source=source, bad=bad), self.assertRaisesRegex(
                ValueError, "source bulletin ID/URL mismatch"
            ):
                prepare_official_bulletin(replace(_record(source).bulletin, **bad))

    def test_matching_notices_are_one_suspected_origin_not_two_witnesses(self):
        a, b = _preview(_record("ukmto-192")), _preview(_record("mscio-165"))
        result = build_staging_attack_lineage_review([a, b], [_link()])
        self.assertEqual(result["source_count"], 2)
        self.assertEqual(result["provisional_origin_groups"], 1)
        self.assertEqual(result["suspected_duplicate_publications"], 1)
        self.assertEqual(result["independent_origins_verified"], 0)
        self.assertFalse(result["publication_allowed"])
        self.assertEqual(result["lineage_groups"][0]["report_ids"],
                         ["MSCIO:165/26", "UKMTO:192-26"])

    def test_nearby_clock_alone_does_not_create_a_link(self):
        a, b = _preview(_record("ukmto-192")), _preview(_record("mscio-165"))
        unlinked = build_staging_attack_lineage_review([a, b])
        self.assertEqual(unlinked["provisional_origin_groups"], 2)
        self.assertEqual(unlinked["independent_origins_verified"], 0)

    def test_matching_details_requires_strict_clock_and_real_source_url(self):
        a, b = _preview(_record("ukmto-192")), _preview(_record("mscio-165"))
        b["occurred_at_utc"] = "2026-11-01T23:53:00+00:00"
        with self.assertRaisesRegex(ValueError, "lineage_matching_details_clock_mismatch"):
            build_staging_attack_lineage_review([a, b], [_link()])
        b["occurred_at_utc"] = None
        b["event_date"] = "2026-11-01"
        b["event_time_precision"] = "day"
        with self.assertRaisesRegex(ValueError, "lineage_matching_details_clock_mismatch"):
            build_staging_attack_lineage_review([a, b], [_link()])
        b = _preview(_record("mscio-165"))
        bad = dict(_link(), supporting_source_url="https://example.org/other")
        with self.assertRaisesRegex(ValueError, "lineage_matching_details_sources_required"):
            build_staging_attack_lineage_review([a, b], [bad])
        b["source_url"] = "https://www.ukmto.org/another-warning"
        with self.assertRaisesRegex(ValueError, "lineage_matching_details_sources_required"):
            build_staging_attack_lineage_review([a, b], [_link()])

    def test_distant_event_or_conflicting_imo_cannot_merge(self):
        a, b = _preview(_record("ukmto-192")), _preview(_record("mscio-165"))
        b["occurred_at_utc"] = "2026-11-01T15:09:00+00:00"
        with self.assertRaisesRegex(ValueError, "lineage_matching_details_clock_mismatch"):
            build_staging_attack_lineage_review([a, b], [_link()])
        b = _preview(_record("mscio-165"))
        a["vessel_imo_as_reported"] = "9348625"
        b["vessel_imo_as_reported"] = "9001136"
        with self.assertRaisesRegex(ValueError, "lineage_vessel_identity_conflict"):
            build_staging_attack_lineage_review([a, b], [_link()])
