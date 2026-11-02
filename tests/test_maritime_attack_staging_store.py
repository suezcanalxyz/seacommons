# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline regressions: no production database or network required."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
from unittest import TestCase

from core.intel.maritime_attack_staging_store import (
    append_staging_review_snapshot,
    prepare_staging_review_snapshot,
)


def review() -> dict:
    ledger = [{
        "role": "attack_candidate",
        "canonical_observation_id": "obs:contship-jet",
        "original_report_id": "BG_MOD:news9664",
        "source_url": "https://www.mod.bg/news9664",
        "source_kind": "attack",
        "occurred_at_utc": "2026-10-28T10:00:00+00:00",
        "published_at_utc": None,
        "publication_date": "2026-10-28",
        "received_at_utc": "2026-11-02T14:00:00+00:00",
        "independent_attack_witness_verified": False,
        "publication_allowed": False,
        "republication_approved": False,
        "reported_location": None,
    }]
    canonical = json.dumps(
        ledger, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return {
        "case_review_id": "staging-case-review:obs:contship-jet",
        "attack_observation_id": "obs:contship-jet",
        "attack_report_id": "BG_MOD:news9664",
        "source_evidence_ledger": ledger,
        "evidence_ledger_snapshot_sha256": sha256(canonical.encode()).hexdigest(),
        "evidence_ledger_digest_is_original_document_proof": False,
        "proposed_incident_type": "maritime_attack",
        "review_color": "#ff6b35",
        "attack_reported_location": None,
        "review_blockers": ["origin_independence_unverified"],
        "independent_origins_verified": 0,
        "ais_as_attack_proof": False,
        "publication_allowed": False,
        "staging_only": True,
    }


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class _FakeStagingConnection:
    def __init__(self, database="seacommons_attack_staging", readonly="off",
                 dialect="postgresql", inserted=True, unsafe_role=False):
        self.engine = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
        self.database = database
        self.readonly = readonly
        self.inserted = inserted
        self.unsafe_role = unsafe_role
        self.sql = []
        self.stored_sha = None

    def execute(self, statement, params=None):
        sql = str(statement)
        self.sql.append(sql)
        if "current_database()" in sql:
            return _Scalar(self.database)
        if "transaction_read_only" in sql:
            return _Scalar(self.readonly)
        if "to_regclass" in sql:
            return _Scalar("attack_review_staging.review_snapshots")
        if "staging_review_role_privileges" in sql:
            return _Scalar(1 if self.unsafe_role else 0)
        if "INSERT INTO" in sql:
            return _Scalar(params["snapshot_id"] if self.inserted else None)
        if "SELECT snapshot_sha256" in sql:
            return _Scalar(self.stored_sha)
        raise AssertionError("unexpected SQL")


class StagingReviewStoreTests(TestCase):
    def test_snapshot_deterministic_and_append_only(self):
        one = prepare_staging_review_snapshot(review())
        two = prepare_staging_review_snapshot(deepcopy(review()))
        self.assertEqual(one, two)
        self.assertEqual(len(one.snapshot_id), 64)
        self.assertIn("BG_MOD:news9664", one.payload_json)
        self.assertNotIn("UPDATE", one.payload_json)

    def test_any_evidence_revision_creates_new_snapshot(self):
        baseline = prepare_staging_review_snapshot(review())
        changed = review()
        changed["review_blockers"].append("manual_review_required")
        self.assertNotEqual(
            baseline.snapshot_id, prepare_staging_review_snapshot(changed).snapshot_id
        )

    def test_tampered_ledger_cannot_reuse_digest(self):
        changed = review()
        changed["source_evidence_ledger"][0]["source_url"] = "https://example.org/fake"
        with self.assertRaisesRegex(ValueError, "evidence_digest_mismatch"):
            prepare_staging_review_snapshot(changed)

    def test_rejects_promotion_and_humanitarian_visual_category(self):
        for change in (
            {"publication_allowed": True},
            {"independent_origins_verified": 2},
            {"ais_as_attack_proof": True},
            {"staging_only": False},
            {"proposed_incident_type": "humanitarian_drift"},
            {"review_color": "#000000"},
            {"evidence_ledger_digest_is_original_document_proof": True},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_staging_review_snapshot(review() | change)

    def test_rejects_fake_witness_independence_and_missing_blocker(self):
        for field in ("independent_attack_witness_verified",
                      "publication_allowed", "republication_approved"):
            item = review()
            item["source_evidence_ledger"][0][field] = True
            item["evidence_ledger_snapshot_sha256"] = sha256(
                json.dumps(item["source_evidence_ledger"], sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False).encode()
            ).hexdigest()
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "untrusted_source_evidence"
            ):
                prepare_staging_review_snapshot(item)
        item = review()
        item["review_blockers"] = []
        with self.assertRaisesRegex(ValueError, "independence_blocker_required"):
            prepare_staging_review_snapshot(item)

    def test_rejects_mismatched_case_and_duplicate_source(self):
        with self.assertRaisesRegex(ValueError, "case_id_conflict"):
            prepare_staging_review_snapshot(
                review() | {"case_review_id": "staging-case-review:obs:other"}
            )
        item = review()
        item["source_evidence_ledger"].append({**deepcopy(item["source_evidence_ledger"][0]), "role": "followup_context"})
        item["evidence_ledger_snapshot_sha256"] = sha256(
            json.dumps(item["source_evidence_ledger"], sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "duplicate_source"):
            prepare_staging_review_snapshot(item)

    def test_staging_insert_is_parameterized_and_does_not_commit(self):
        snapshot = prepare_staging_review_snapshot(review())
        conn = _FakeStagingConnection()
        self.assertTrue(append_staging_review_snapshot(
            conn, snapshot, expected_database="seacommons_attack_staging"
        ))
        self.assertEqual(sum("INSERT INTO" in s for s in conn.sql), 1)
        self.assertTrue(all("DELETE FROM" not in s and "UPDATE " not in s
                            for s in conn.sql))
        self.assertIn(":payload_json", next(s for s in conn.sql if "INSERT INTO" in s))

    def test_rejects_privileged_role_before_any_insert(self):
        snapshot = prepare_staging_review_snapshot(review())
        conn = _FakeStagingConnection(unsafe_role=True)
        with self.assertRaisesRegex(ValueError, "role_not_append_only"):
            append_staging_review_snapshot(
                conn, snapshot, expected_database="seacommons_attack_staging"
            )
        self.assertFalse(any("INSERT INTO" in sql for sql in conn.sql))
        privilege_sql = next(sql for sql in conn.sql
                             if "staging_review_role_privileges" in sql)
        for required in ("is_superuser", "has_database_privilege",
                         "has_schema_privilege", "SELECT", "INSERT",
                         "UPDATE", "DELETE", "TRUNCATE", "TRIGGER"):
            with self.subTest(privilege=required):
                self.assertIn(required, privilege_sql)

    def test_idempotent_replay_without_update(self):
        snapshot = prepare_staging_review_snapshot(review())
        conn = _FakeStagingConnection(inserted=False)
        conn.stored_sha = snapshot.snapshot_sha256
        self.assertFalse(append_staging_review_snapshot(
            conn, snapshot, expected_database="seacommons_attack_staging"
        ))
        conn.stored_sha = "f" * 64
        with self.assertRaisesRegex(ValueError, "conflicting_replay"):
            append_staging_review_snapshot(
                conn, snapshot, expected_database="seacommons_attack_staging"
            )

    def test_rejects_forged_snapshot_before_database_access(self):
        original = prepare_staging_review_snapshot(review())
        for forged in (
            replace(original, payload_json='{"publication_allowed":true}'),
            replace(original, snapshot_sha256="0" * 64),
            replace(original, evidence_ledger_sha256="0" * 64),
        ):
            conn = _FakeStagingConnection()
            with self.subTest(forged=forged.snapshot_sha256), self.assertRaisesRegex(
                ValueError, "snapshot_integrity"
            ):
                append_staging_review_snapshot(
                    conn, forged, expected_database="seacommons_attack_staging"
                )
            self.assertEqual(conn.sql, [])

    def test_fail_closed_for_production_database_and_readonly(self):
        snapshot = prepare_staging_review_snapshot(review())
        for database, expected, readonly, dialect in (
            ("seacommons", "seacommons", "off", "postgresql"),
            ("seacommons", "seacommons_attack_staging", "off", "postgresql"),
            ("seacommons_attack_staging", "seacommons_attack_staging", "on", "postgresql"),
            ("seacommons_attack_staging", "seacommons_attack_staging", "off", "sqlite"),
        ):
            conn = _FakeStagingConnection(database, readonly, dialect)
            with self.subTest(database=database, readonly=readonly, dialect=dialect):
                with self.assertRaises(ValueError):
                    append_staging_review_snapshot(
                        conn, snapshot, expected_database=expected
                    )
                self.assertFalse(any("INSERT INTO" in s for s in conn.sql))
