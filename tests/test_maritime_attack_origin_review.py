# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests for independent origin counting and fail-closed review."""
from copy import deepcopy
from unittest import TestCase

from core.intel.maritime_attack_origin_review import prepare_origin_review


def report(publisher="UKMTO", report_id="191-2026", origin=None, verified=False, kind="relay"):
    return {
        "publisher": publisher, "publisher_item_id": report_id,
        "source_url": "https://www.ukmto.org/recent-incidents" if publisher == "UKMTO" else "https://mscio.eu/alerts/200",
        "origin_key": origin, "origin_verified": verified,
        "retrieved_at_utc": "2026-11-03T10:00:00Z", "evidence_kind": kind,
    }


class OriginReviewTests(TestCase):
    def review(self, reports):
        return prepare_origin_review(reports, reviewed_at_utc="2026-11-03T11:00:00Z")

    def test_mscio_ukmto_same_unknown_mayday_is_not_two_origins(self):
        result = self.review([report(), report("MSCIO", "164/26")])
        self.assertEqual(result["independent_testimonial_origins"], 0)
        self.assertEqual(len(result["unresolved_reports"]), 2)
        self.assertFalse(result["publication_allowed"])

    def test_two_publishers_one_verified_origin_count_once(self):
        result = self.review([
            report(origin="master:relay-1", verified=True, kind="first_hand"),
            report("MSCIO", "164/26", origin="master:relay-1", verified=True, kind="authority"),
        ])
        self.assertEqual(result["independent_testimonial_origins"], 1)

    def test_two_truly_distinct_verified_origins(self):
        result = self.review([
            report(origin="master:A", verified=True, kind="first_hand"),
            report("MSCIO", "164/26", origin="coastguard:B", verified=True, kind="authority"),
        ])
        self.assertEqual(result["independent_testimonial_origins"], 2)
        self.assertFalse(result["publication_allowed"])

    def test_ais_signal_is_not_a_second_witness(self):
        with self.assertRaisesRegex(ValueError, "ais_is_not_witness"):
            self.review([report(origin="ais:gap", verified=True, kind="ais_signal")])

    def test_same_warning_id_different_publishers_not_global_collision(self):
        result = self.review([report("UKMTO", "192-26"), report("MSCIO", "192-26")])
        self.assertEqual(len(result["reports"]), 2)

    def test_duplicate_publisher_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate_publisher_report"):
            self.review([report(), report()])

    def test_unverified_origin_key_never_counts(self):
        result = self.review([report(origin="master:A", verified=False, kind="first_hand")])
        self.assertEqual(result["independent_testimonial_origins"], 0)

    def test_reject_future_retrieval(self):
        item = report()
        item["retrieved_at_utc"] = "2026-11-04T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "future_retrieval"):
            self.review([item])

    def test_deterministic_and_input_immutable(self):
        batch = [report(), report("MSCIO", "164/26")]
        before = deepcopy(batch)
        self.assertEqual(self.review(batch), self.review(batch))
        self.assertEqual(batch, before)

    def test_reject_unreviewed_fields(self):
        with self.assertRaisesRegex(ValueError, "invalid_report_schema"):
            self.review([dict(report(), attacker="unknown")])

    def test_different_ids_same_publisher_url_are_not_independent(self):
        with self.assertRaisesRegex(ValueError, "duplicate_publisher_source_url"):
            self.review([report("UKMTO", "191-2026"), report("UKMTO", "192-2026")])

    def test_reject_url_credentials_and_fragments(self):
        for url in ("https://user:pass@www.ukmto.org/recent-incidents",
                    "https://www.ukmto.org/recent-incidents#claim",
                    "https://www.ukmto.org:8443/recent-incidents"):
            item = report()
            item["source_url"] = url
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "invalid_source_url"):
                self.review([item])
