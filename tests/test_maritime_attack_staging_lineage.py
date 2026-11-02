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

    def test_cross_midnight_same_event_is_not_false_negative(self):
        a = notice("MSCIO:late", "2026-10-31T23:58:00+00:00",
                   event_date="2026-10-31")
        b = notice("UKMTO:early", "2026-11-01T00:03:00+00:00",
                   event_date="2026-11-01")
        result = build_staging_attack_lineage_review(
            [a, b], [shared("MSCIO:late", "UKMTO:early")]
        )
        self.assertEqual(result["provisional_origin_groups"], 1)
        self.assertEqual(result["suspected_duplicate_publications"], 1)
        self.assertEqual(result["independent_origins_verified"], 0)
        self.assertFalse(result["publication_allowed"])

    def test_cross_midnight_distant_events_stay_distinct(self):
        a = notice("A", "2026-10-31T22:00:00+00:00",
                   event_date="2026-10-31")
        b = notice("B", "2026-11-01T01:00:01+00:00",
                   event_date="2026-11-01")
        with self.assertRaisesRegex(ValueError, "lineage_temporal_conflict"):
            build_staging_attack_lineage_review([a, b], [shared("A", "B")])

    def test_cross_midnight_conflicting_imo_still_blocks_merge(self):
        a = notice("A", "2026-10-31T23:58:00+00:00",
                   event_date="2026-10-31",
                   vessel_imo_as_reported="9348625")
        b = notice("B", "2026-11-01T00:03:00+00:00",
                   event_date="2026-11-01",
                   vessel_imo_as_reported="9001136")
        with self.assertRaisesRegex(ValueError, "lineage_vessel_identity_conflict"):
            build_staging_attack_lineage_review([a, b], [shared("A", "B")])

    def test_cross_midnight_distant_locations_still_block_merge(self):
        a = notice("A", "2026-10-31T23:58:00+00:00",
                   event_date="2026-10-31",
                   reported_location={"lat": 43.0, "lon": 29.0,
                                      "role": "incident_site", "uncertainty_km": 5})
        b = notice("B", "2026-11-01T00:03:00+00:00",
                   event_date="2026-11-01",
                   reported_location={"lat": 26.0, "lon": 56.0,
                                      "role": "incident_site", "uncertainty_km": 5})
        with self.assertRaisesRegex(ValueError, "lineage_spatial_conflict"):
            build_staging_attack_lineage_review([a, b], [shared("A", "B")])

    def test_day_only_cross_midnight_is_not_assumed_identical(self):
        a = notice("A", None, event_date="2026-10-31")
        b = notice("B", "2026-11-01T00:01:00+00:00",
                   event_date="2026-11-01")
        with self.assertRaisesRegex(ValueError, "lineage_event_day_conflict"):
            build_staging_attack_lineage_review([a, b], [shared("A", "B")])

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

    def test_rejects_extra_location_metadata_outside_snapshot(self):
        with self.assertRaisesRegex(ValueError, "lineage_non_incident_geometry"):
            build_staging_attack_lineage_review([notice(
                "A", reported_location={
                    "lat": 26.0, "lon": 56.0, "role": "incident_site",
                    "uncertainty_km": None, "unfingerprinted_precision": 1,
                }
            )])

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

    def test_digest_changes_when_source_evidence_changes(self):
        base = notice(
            "MSCIO:164/26",
            reported_location={
                "lat": 26.0, "lon": 56.0, "role": "incident_site",
                "uncertainty_km": None,
            },
            source_document_sha256="a" * 64,
            received_at_utc="2026-11-02T12:00:00+00:00",
        )
        baseline = build_staging_attack_lineage_review([base])
        for changed in (
            {"occurred_at_utc": "2026-11-01T15:10:00+00:00"},
            {"source_url": "https://mscio.eu/alerts/201"},
            {"vessel_imo_as_reported": "9348625"},
            {"source_document_sha256": "b" * 64},
            {"received_at_utc": "2026-11-02T12:01:00+00:00"},
            {"source_rights": "restricted_republication"},
            {"reported_location": {
                "lat": 26.1, "lon": 56.0, "role": "incident_site",
                "uncertainty_km": None,
            }},
            {"reported_location": {
                "lat": 26.0, "lon": 56.0, "role": "incident_site",
                "uncertainty_km": 0,
            }},
        ):
            with self.subTest(changed=changed):
                updated = build_staging_attack_lineage_review(
                    [notice("MSCIO:164/26", **(base | changed))]
                )
                self.assertNotEqual(
                    baseline["lineage_snapshot_sha256"],
                    updated["lineage_snapshot_sha256"],
                )
                self.assertFalse(updated["publication_allowed"])
        self.assertEqual(
            baseline["lineage_snapshot_sha256"],
            build_staging_attack_lineage_review([deepcopy(base)])[
                "lineage_snapshot_sha256"
            ],
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

    def test_boolean_or_coerced_witness_count_cannot_pass_as_zero(self):
        for count in (False, 0.0, "0", None):
            with self.subTest(count=count), self.assertRaisesRegex(
                ValueError, "lineage_untrusted_or_publishable_candidate"
            ):
                build_staging_attack_lineage_review([
                    notice("A", independent_origins_verified=count)
                ])

    def test_source_and_lineage_links_require_safe_https_urls(self):
        for url in (
            "https://", "https://user:pass@example.org/notice",
            "https://example.org/notice#untracked",
            "https://example.org/notice\\n", "https://example.org:99999/notice",
            "http://example.org/notice",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(
                ValueError, "lineage_invalid_source_url"
            ):
                build_staging_attack_lineage_review([notice("A", source_url=url)])
            with self.subTest(link=url), self.assertRaisesRegex(
                ValueError, "lineage_link_source_required"
            ):
                build_staging_attack_lineage_review(
                    [notice("A"), notice("B")],
                    [shared("A", "B", supporting_source_url=url)],
                )

    def test_rejects_invalid_source_clocks_dates_and_digests(self):
        for change, error in (
            ({"received_at_utc": "2026-11-02"}, "lineage_exact_clock_required"),
            ({"published_at_utc": "not-a-clock"}, "lineage_exact_clock_required"),
            ({
                "received_at_utc": "2026-11-02T12:00:00+00:00",
                "published_at_utc": "2026-11-02T12:01:00+00:00",
            }, "lineage_publication_after_receipt"),
            ({
                "received_at_utc": "2026-11-02T12:00:00+00:00",
                "source_checked_on_utc": "2026-11-03",
            }, "lineage_source_day_after_receipt"),
            ({"publication_date": "20261101"}, "lineage_invalid_source_day"),
            ({"raw_payload_hash": "not-a-hash"}, "lineage_invalid_source_digest"),
            ({"source_document_sha256": "f" * 63}, "lineage_invalid_source_digest"),
        ):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, error):
                build_staging_attack_lineage_review([notice("A", **change)])

    def test_rejects_noncanonical_day_only_event(self):
        with self.assertRaisesRegex(ValueError, "lineage_invalid_event_day"):
            build_staging_attack_lineage_review([
                notice("A", None, event_date="20261101")
            ])

    def test_valid_source_provenance_remains_unverified(self):
        result = build_staging_attack_lineage_review([
            notice(
                "MSCIO:164/26",
                published_at_utc="2026-11-01T21:36:00+00:00",
                received_at_utc="2026-11-02T12:00:00+00:00",
                source_checked_on_utc="2026-11-02",
                publication_date="2026-11-01",
                raw_payload_hash="a" * 64,
                source_document_sha256="b" * 64,
            )
        ])
        self.assertEqual(result["independent_origins_verified"], 0)
        self.assertFalse(result["publication_allowed"])
        self.assertEqual(result["provisional_origin_groups"], 1)
