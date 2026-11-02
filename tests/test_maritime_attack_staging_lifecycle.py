# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed lifecycle regressions: AZINI closure is not another attack."""
from __future__ import annotations

from copy import deepcopy
from unittest import TestCase

from core.intel.maritime_attack_staging_lifecycle import (
    prepare_staging_lifecycle_update,
)


def original() -> dict[str, object]:
    return {
        "original_report_id": "MSCIO:161/26",
        "canonical_observation_id": "obs:MSCIO:161/26",
        "source_url": "https://mscio.eu/alerts/197",
        "source_kind": "piracy",
        "event_date": "2026-10-29",
        "occurred_at_utc": "2026-10-29T09:00:00+00:00",
        "independent_origins_verified": 0,
        "publication_allowed": False,
        "staging_only": True,
    }


def closure() -> dict[str, object]:
    return {
        "issuer": "MSCIO",
        "original_report_id": "MSCIO:161/26",
        "source_update_id": "UPDATE02",
        "source_url": "https://www.mscio.eu/alerts/197/",
        "source_checked_at_utc": "2026-11-02T22:20:00+00:00",
        # MSCIO confirms liberation but does not print its effective UTC clock.
        "status_effective_at_utc": None,
        "source_published_at_utc": None,
        "status": "closed",
        "source_rights": "restricted_republication",
        "independent_origins_verified": 0,
        "publication_allowed": False,
        "staging_only": True,
    }


class StagingLifecycleTests(TestCase):
    def test_azini_update02_is_one_closed_case_not_second_attack(self):
        result = prepare_staging_lifecycle_update(original(), closure())
        self.assertEqual(result["case_observation_id"], "obs:MSCIO:161/26")
        self.assertEqual(result["lifecycle_evidence_id"], "MSCIO:161/26:UPDATE02")
        self.assertEqual(result["reported_status"], "closed")
        self.assertIsNone(result["status_effective_at_utc"])
        self.assertIsNone(result["source_published_at_utc"])
        self.assertFalse(result["new_incident"])
        self.assertFalse(result["attack_corroboration_allowed"])
        self.assertFalse(result["publication_allowed"])
        self.assertEqual(result["independent_origins_verified"], 0)
        self.assertIsNone(result["attacker_attribution"])

    def test_replay_is_deterministic_and_update_is_immutable(self):
        first, second = original(), closure()
        before = deepcopy((first, second))
        a = prepare_staging_lifecycle_update(first, second)
        b = prepare_staging_lifecycle_update(first, second)
        self.assertEqual(a, b)
        self.assertEqual((first, second), before)
        changed = dict(second, source_checked_at_utc="2026-11-02T22:21:00Z")
        c = prepare_staging_lifecycle_update(first, changed)
        self.assertNotEqual(a["lifecycle_snapshot_sha256"],
                            c["lifecycle_snapshot_sha256"])

    def test_update01_is_separate_version_not_new_incident(self):
        first = prepare_staging_lifecycle_update(
            original(), dict(closure(), source_update_id="UPDATE01",
                             status="investigating")
        )
        second = prepare_staging_lifecycle_update(original(), closure())
        self.assertNotEqual(first["lifecycle_evidence_id"],
                            second["lifecycle_evidence_id"])
        self.assertFalse(first["new_incident"])
        self.assertFalse(second["new_incident"])

    def test_unrelated_ship_or_report_cannot_inherit_closure(self):
        for changed in (
            dict(closure(), original_report_id="MSCIO:164/26"),
            dict(original(), original_report_id="MSCIO:164/26"),
            dict(original(), canonical_observation_id=""),
        ):
            with self.subTest(changed=changed):
                if "source_update_id" in changed:
                    with self.assertRaisesRegex(ValueError, "identity_conflict"):
                        prepare_staging_lifecycle_update(original(), changed)
                else:
                    with self.assertRaisesRegex(ValueError, "identity_conflict"):
                        prepare_staging_lifecycle_update(changed, closure())

    def test_rejects_different_source_page_even_same_issuer(self):
        with self.assertRaisesRegex(ValueError, "source_document_conflict"):
            prepare_staging_lifecycle_update(
                original(), dict(closure(), source_url="https://mscio.eu/alerts/200")
            )

    def test_rejects_lookalike_host_or_credentials(self):
        for url in (
            "https://mscio.eu.evil.example/alerts/197",
            "https://user:secret@mscio.eu/alerts/197",
            "http://mscio.eu/alerts/197",
            "https://mscio.eu/alerts/197?claim=closed",
            "https://mscio.eu/alerts/197#UPDATE02",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(
                ValueError, "invalid_source_url"
            ):
                prepare_staging_lifecycle_update(
                    original(), dict(closure(), source_url=url)
                )

    def test_rejects_promotion_or_false_independence(self):
        for patch in (
            {"publication_allowed": True},
            {"staging_only": False},
            {"independent_origins_verified": 1},
            {"independent_origins_verified": True},
        ):
            with self.subTest(patch=patch), self.assertRaisesRegex(
                ValueError, "publication_boundary"
            ):
                prepare_staging_lifecycle_update(original(), dict(closure(), **patch))

    def test_rejects_untrusted_original(self):
        for patch in (
            {"publication_allowed": True},
            {"source_kind": "humanitarian_drift"},
            {"independent_origins_verified": 1},
        ):
            with self.subTest(patch=patch), self.assertRaisesRegex(
                ValueError, "untrusted_original"
            ):
                prepare_staging_lifecycle_update(dict(original(), **patch), closure())

    def test_rejects_fabricated_effective_clock_after_check(self):
        with self.assertRaisesRegex(ValueError, "future_source_claim"):
            prepare_staging_lifecycle_update(original(), dict(
                closure(), status_effective_at_utc="2026-11-03T01:00:00Z"
            ))

    def test_rejects_status_before_original_attack(self):
        with self.assertRaisesRegex(ValueError, "effective_before_original"):
            prepare_staging_lifecycle_update(original(), dict(
                closure(), status_effective_at_utc="2026-10-28T23:00:00Z"
            ))

    def test_rejects_published_before_status_effective(self):
        with self.assertRaisesRegex(ValueError, "published_before_effective"):
            prepare_staging_lifecycle_update(original(), dict(
                closure(), source_published_at_utc="2026-11-02T10:00:00Z",
                status_effective_at_utc="2026-11-02T11:00:00Z"
            ))

    def test_rejects_publication_after_check(self):
        with self.assertRaisesRegex(ValueError, "future_source_claim"):
            prepare_staging_lifecycle_update(original(), dict(
                closure(), source_published_at_utc="2026-11-03T00:00:00Z"
            ))

    def test_source_digest_must_be_valid_and_changes_snapshot(self):
        with self.assertRaisesRegex(ValueError, "invalid_source_digest"):
            prepare_staging_lifecycle_update(original(), dict(
                closure(), source_document_sha256="unverified"
            ))
        a = prepare_staging_lifecycle_update(original(), closure())
        b = prepare_staging_lifecycle_update(original(), dict(
            closure(), source_document_sha256="a" * 64
        ))
        self.assertNotEqual(a["lifecycle_snapshot_sha256"],
                            b["lifecycle_snapshot_sha256"])

    def test_rejects_unreviewed_coordinates_and_attacker(self):
        for field, value in (("lat", 9.7), ("attacker", "unknown"),
                             ("new_incident", True)):
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "unreviewed_fields"
            ):
                prepare_staging_lifecycle_update(original(), dict(
                    closure(), **{field: value}
                ))

    def test_rejects_unapproved_status_and_issuer(self):
        with self.assertRaisesRegex(ValueError, "status_not_supported"):
            prepare_staging_lifecycle_update(
                original(), dict(closure(), status="confirmed_attack")
            )
        with self.assertRaisesRegex(ValueError, "unapproved_issuer"):
            prepare_staging_lifecycle_update(
                original(), dict(closure(), issuer="SOCIAL_MEDIA")
            )
