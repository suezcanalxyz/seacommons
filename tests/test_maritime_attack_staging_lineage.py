# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed regressions for independent-source lineage in staging."""
from __future__ import annotations

from copy import deepcopy
from unittest import TestCase

from core.intel.maritime_attack_staging_lineage import (
    build_staging_attack_lineage_review,
)


def notice(report_id: str, when: str | None = "2026-11-01T15:09:00+00:00",
           **changes: object) -> dict[str, object]:
    item: dict[str, object] = {
        "original_report_id": report_id,
        "canonical_observation_id": "obs:" + report_id,
        "source_url": "https://example.org/notice/" + report_id,
        "source_kind": "attack",
        "review_status": "candidate",
        "event_time_precision": "exact" if when else "day",
        "event_date": "2026-11-01",
        "occurred_at_utc": when,
        "vessel_name_as_reported": "",
        "vessel_imo_as_reported": "",
        "vessel_mmsi_as_reported": "",
        "reported_location": None,
        "independent_origins_verified": 0,
        "publication_allowed": False,
        "staging_only": True,
    }
    item.update(changes)
    return item


def shared(a: str, b: str, **changes: str) -> dict[str, str]:
    link = {
        "left_report_id": a,
        "right_report_id": b,
        "basis": "shared_vhf_mayday",
        "supporting_source_url": "https://mscio.eu/alerts/200",
    }
    link.update(changes)
    return link


class MaritimeAttackLineageTests(TestCase):
    def test_mscio_164_and_ukmto_191_are_one_suspected_lineage(self):
        first = notice("MSCIO:164/26", event_time_precision="approximate")
        second = notice("UKMTO:191/26")
        third = notice("UKMTO:192/26", "2026-11-01T23:47:00+00:00")
        result = build_staging_attack_lineage_review(
            [first, second, third], [shared("MSCIO:164/26", "UKMTO:191/26")]
        )
        self.assertEqual(result["source_count"], 3)
        self.assertEqual(result["provisional_origin_groups"], 2)
        self.assertEqual(result["suspected_duplicate_publications"], 1)
        self.assertEqual(result["independent_origins_verified"], 0)
        self.assertFalse(result["publication_allowed"])
        self.assertTrue(result["staging_only"])
        self.assertEqual(
            result["lineage_groups"][0]["report_ids"],
            ["MSCIO:164/26", "UKMTO:191/26"],
        )
        self.assertEqual(
            result["suspected_shared_origin_links"][0]["status"],
            "suspected_shared_origin_not_verified",
        )

    def test_192_cannot_merge_with_191_by_temporal_proximity(self):
        with self.assertRaisesRegex(ValueError, "lineage_temporal_conflict"):
            build_staging_attack_lineage_review(
                [notice("UKMTO:191/26"),
                 notice("UKMTO:192/26", "2026-11-01T23:47:00+00:00")],
                [shared("UKMTO:191/26", "UKMTO:192/26")],
            )

    def test_no_link_does_not_prove_independence(self):
        result = build_staging_attack_lineage_review(
            [notice("MOD:JET", "2026-10-28T10:00:00+00:00",
                    event_date="2026-10-28"),
             notice("REUTERS:JET", "2026-10-28T10:01:00+00:00",
                    event_date="2026-10-28")]
        )
        self.assertEqual(result["provisional_origin_groups"], 2)
        self.assertEqual(result["independent_origins_verified"], 0)
        self.assertIn("origin_independence_unverified", result["review_blockers"])

    def test_unidentified_day_only_notice_retains_date(self):
        result = build_staging_attack_lineage_review(
            [notice("MSCIO:163/26", None, event_date="2026-10-28")]
        )
        self.assertEqual(result["source_count"], 1)
        self.assertFalse(result["publication_allowed"])

    def test_named_vessel_conflict_blocks_false_merger(self):
        with self.assertRaisesRegex(ValueError, "lineage_vessel_name_conflict"):
            build_staging_attack_lineage_review(
                [notice("A", vessel_name_as_reported="CONTSHIP JET"),
                 notice("B", vessel_name_as_reported="ABLE")],
                [shared("A", "B")],
            )

    def test_imo_conflict_blocks_false_merger(self):
        with self.assertRaisesRegex(ValueError, "lineage_vessel_identity_conflict"):
            build_staging_attack_lineage_review(
                [notice("A", vessel_imo_as_reported="9348625"),
                 notice("B", vessel_imo_as_reported="9001136")],
                [shared("A", "B")],
            )

    def test_distant_positions_block_false_merger(self):
        a = notice("A", reported_location={
            "lat": 26.0, "lon": 56.0, "role": "incident_site",
            "uncertainty_km": 5,
        })
        b = notice("B", reported_location={
            "lat": 28.0, "lon": 50.0, "role": "incident_site",
            "uncertainty_km": 5,
        })
        with self.assertRaisesRegex(ValueError, "lineage_spatial_conflict"):
            build_staging_attack_lineage_review([a, b], [shared("A", "B")])

    def test_uncertain_position_does_not_create_attack_site(self):
        a = notice("A", reported_location={
            "lat": 26.0, "lon": 56.0, "role": "incident_site",
            "uncertainty_km": 500,
        })
        b = notice("B", reported_location={
            "lat": 28.0, "lon": 50.0, "role": "incident_site",
            "uncertainty_km": 500,
        })
        result = build_staging_attack_lineage_review([a, b], [shared("A", "B")])
        self.assertEqual(result["independent_origins_verified"], 0)
        self.assertNotIn("attack_location", result)

    def test_rejects_later_wreck_as_attack_source(self):
        with self.assertRaisesRegex(ValueError, "lineage_untrusted_or_publishable_candidate"):
            build_staging_attack_lineage_review(
                [notice("NAVWARN:768/26", source_kind="navigational_hazard")]
            )

    def test_rejects_publishable_or_preverified_input(self):
        for change in (
            {"publication_allowed": True},
            {"independent_origins_verified": 2},
            {"staging_only": False},
        ):
            with self.subTest(change=change), self.assertRaisesRegex(
                ValueError, "lineage_untrusted_or_publishable_candidate"
            ):
                build_staging_attack_lineage_review([notice("A", **change)])

    def test_rejects_duplicate_reports_and_observations(self):
        with self.assertRaisesRegex(ValueError, "lineage_duplicate_or_missing_source_id"):
            build_staging_attack_lineage_review([notice("A"), notice("A")])
        with self.assertRaisesRegex(ValueError, "lineage_duplicate_or_missing_source_id"):
            build_staging_attack_lineage_review([
                notice("A"), notice("B", canonical_observation_id="obs:A")
            ])

    def test_rejects_self_links_unknown_sources_and_unsourced_links(self):
        a, b = notice("A"), notice("B")
        for link in (
            shared("A", "A"),
            shared("A", "C"),
            shared("A", "B", supporting_source_url=""),
            shared("A", "B", basis="unverified_third_party_assertion"),
        ):
            with self.subTest(link=link), self.assertRaises(ValueError):
                build_staging_attack_lineage_review([a, b], [link])

    def test_rejects_duplicate_links(self):
        with self.assertRaisesRegex(ValueError, "lineage_duplicate_link"):
            build_staging_attack_lineage_review(
                [notice("A"), notice("B")],
                [shared("A", "B"), shared("B", "A")],
            )

    def test_transitive_merge_checks_every_member(self):
        # A and B are compatible, as are B and C. A and C are >2h apart.
        a = notice("A", "2026-11-01T15:00:00+00:00")
        b = notice("B", "2026-11-01T16:45:00+00:00")
        c = notice("C", "2026-11-01T18:30:00+00:00")
        with self.assertRaisesRegex(ValueError, "lineage_temporal_conflict"):
            build_staging_attack_lineage_review(
                [a, b, c], [shared("A", "B"), shared("B", "C")]
            )

    def test_digest_deterministic_and_changes_on_lineage_evidence(self):
        candidates = [notice("A"), notice("B")]
        one = build_staging_attack_lineage_review(candidates, [shared("A", "B")])
        two = build_staging_attack_lineage_review(
            list(reversed(candidates)), [shared("B", "A")]
        )
        self.assertEqual(one["lineage_snapshot_sha256"], two["lineage_snapshot_sha256"])
        changed = deepcopy(shared("A", "B"))
        changed["supporting_source_url"] = "https://www.ukmto.org/"
        three = build_staging_attack_lineage_review(candidates, [changed])
        self.assertNotEqual(one["lineage_snapshot_sha256"], three["lineage_snapshot_sha256"])
        self.assertFalse(one["lineage_digest_is_source_proof"])
