# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline, metadata-only staging preview regression tests."""
import json
import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from core.intel.maritime_attack_staging_manifest import prepare_staging_bulletin_manifest
from core.intel.maritime_attack_staging_preview import build_staging_attack_previews
from core.intel.official_maritime_bulletin import prepare_official_bulletin

MANIFEST = Path(__file__).resolve().parents[1] / "docs/research/maritime-attack-source-check-2026-11-01.json"


def fixtures():
    records = prepare_staging_bulletin_manifest(json.loads(MANIFEST.read_text()))
    observations = []
    for r in records:
        e = r.envelope
        delivery_key = f'{e["source_name"]}:{e["source_id"]}'
        observations.append(SimpleNamespace(
            observation_id="obs:" + hashlib.blake2s(delivery_key.encode(), digest_size=16).hexdigest(),
            service=e["service"], lane=e["lane"],
            observation_type=e["observation_type"],
            source_policy=e["source_policy"],
            source_name=e["source_name"], source_id=e["source_id"],
            source_url=e["source_url"], raw_payload_hash=hashlib.sha256(
                e["raw_payload"].encode("utf-8")).hexdigest(),
            subject_refs=e["subject_refs"], provenance=e["provenance"],
            observed_at=e["observed_at"], lat=e["lat"], lon=e["lon"],
            uncertainty_m=e["uncertainty_m"], location_precision=None,
            received_at=datetime(2026, 11, 2, 0, tzinfo=timezone.utc),
        ))
    return records, observations


class StagingAttackPreviewTests(TestCase):
    def test_six_metadata_only_previews_and_non_attack_negative(self):
        records, observations = fixtures()
        previews = build_staging_attack_previews(records, observations)
        self.assertEqual(len(previews), 6)
        self.assertEqual(sum(p["proposed_incident_type"] == "maritime_attack" for p in previews), 4)
        self.assertTrue(all(p["publication_allowed"] is False for p in previews))
        self.assertTrue(all(p["independent_origins_verified"] == 0 for p in previews))
        self.assertTrue(all(p["ais_as_attack_proof"] is False for p in previews))
        self.assertTrue(all("incident_type" not in p and "visual_category" not in p for p in previews))
        jet = previews[0]
        self.assertEqual(jet["vessel_name_as_reported"], "CONTSHIP JET")
        self.assertEqual(jet["vessel_imo_as_reported"], "")
        self.assertEqual(jet["vessel_mmsi_as_reported"], "")
        self.assertEqual(jet["proposed_incident_type"], "maritime_attack")
        self.assertEqual(jet["review_color"], "#ff6b35")
        self.assertEqual(jet["canonical_observed_at"], "2026-10-28T10:00:00+00:00")
        self.assertEqual(jet["observed_at_semantics"], "event")
        self.assertIsNone(jet["reported_location"])
        self.assertIn("exact_publication_time_unavailable", jet["review_blockers"])
        self.assertIn("reuse_rights_not_verified", jet["review_blockers"])
        self.assertIn("restricted_republication", previews[1]["review_blockers"])
        self.assertEqual(previews[3]["review_status"], "context_only")
        self.assertIn("not_an_attack", previews[3]["review_blockers"])
        self.assertEqual(previews[4]["proposed_incident_type"], "piracy")
        self.assertEqual(previews[4]["review_color"], "#a78bfa")
        self.assertIn("approximate_event_time_unbounded", previews[2]["review_blockers"])

    def test_canonical_naive_utc_receipt_is_normalized_not_invented(self):
        records, rows = fixtures()
        for received in ("2026-11-02T01:30:00", datetime(2026, 11, 2, 1, 30)):
            modified = [replace_like(rows[0], received_at=received), *rows[1:]]
            preview = build_staging_attack_previews(records, modified)[0]
            self.assertEqual(preview["received_at_utc"], "2026-11-02T01:30:00+00:00")
        for received in (None, "not-a-clock", "2026-11-02"):
            modified = [replace_like(rows[0], received_at=received), *rows[1:]]
            with self.assertRaises(ValueError):
                build_staging_attack_previews(records, modified)

    def test_source_clock_and_position_tampering_fail_closed(self):
        records, rows = fixtures()
        for field, bad in (
            ("observed_at", "2026-10-28T10:01:00+00:00"),
            ("observed_at", "2026-10-28"),
            ("lat", 43.25),
            ("lon", 28.8),
            ("uncertainty_m", 0.0),
            ("location_precision", "exact"),
        ):
            with self.subTest(field=field, value=bad):
                altered = [replace_like(rows[0], **{field: bad}), *rows[1:]]
                with self.assertRaisesRegex(ValueError, "canonical_source_provenance_mismatch"):
                    build_staging_attack_previews(records, altered)

    def test_source_receipt_must_follow_event_publication_and_review(self):
        records, rows = fixtures()
        for receipt in (
            "2026-10-27T23:59:59Z",  # before the 28 Oct CONTSHIP JET attack
            "2026-10-28T10:00:01Z",  # before the 1 Nov source review
            "2026-10-31T23:59:59Z",  # still before the review date
        ):
            with self.subTest(receipt=receipt):
                altered = [replace_like(rows[0], received_at=receipt), *rows[1:]]
                with self.assertRaisesRegex(ValueError, "canonical_receipt_precedes_source"):
                    build_staging_attack_previews(records, altered)

    def test_source_reported_position_retained_with_role_and_uncertainty(self):
        records, rows = fixtures()
        original = records[0]
        bulletin = replace(
            original.bulletin,
            lat=43.259, lon=28.815,
            location_role="incident_site", location_uncertainty_km=3.0,
        )
        envelope = prepare_official_bulletin(bulletin)
        revised = replace(original, bulletin=bulletin, envelope=envelope)
        key = f'{envelope["source_name"]}:{envelope["source_id"]}'
        row = replace_like(
            rows[0],
            observation_id="obs:" + hashlib.blake2s(key.encode(), digest_size=16).hexdigest(),
            source_id=envelope["source_id"],
            observed_at=envelope["observed_at"],
            raw_payload_hash=hashlib.sha256(envelope["raw_payload"].encode("utf-8")).hexdigest(),
            provenance=envelope["provenance"],
            lat=43.259, lon=28.815, uncertainty_m=3000.0,
        )
        preview = build_staging_attack_previews([revised, *records[1:]], [row, *rows[1:]])[0]
        self.assertEqual(preview["reported_location"], {
            "lat": 43.259, "lon": 28.815,
            "role": "incident_site", "uncertainty_km": 3.0,
        })
        for changed in (
            {"lat": 43.5}, {"lon": 29.0}, {"uncertainty_m": 0.0},
            {"uncertainty_m": float("nan")},
        ):
            with self.subTest(changed=changed):
                altered = [replace_like(row, **changed), *rows[1:]]
                with self.assertRaisesRegex(ValueError, "canonical_source_provenance_mismatch"):
                    build_staging_attack_previews([revised, *records[1:]], altered)

    def test_replay_order_does_not_change_preview(self):
        records, rows = fixtures()
        forward = build_staging_attack_previews(records, rows)
        reverse = build_staging_attack_previews(records, list(reversed(rows)))
        self.assertEqual(forward, reverse)

    def test_tampering_duplicate_missing_or_foreign_row_blocks_entire_preview(self):
        records, rows = fixtures()
        for mutated in (
            rows[:-1], rows + rows[:1],
            [replace_like(rows[0], provenance={**rows[0].provenance, "origin_authority_verified": True})] + rows[1:],
            [replace_like(rows[0], raw_payload_hash="0" * 64)] + rows[1:],
            [replace_like(rows[0], service="humanitarian")] + rows[1:],
            [replace_like(rows[0], subject_refs=["imo:9348625"])] + rows[1:],
        ):
            with self.subTest(case=str(len(mutated)) + str(mutated[0].service)):
                with self.assertRaises(ValueError):
                    build_staging_attack_previews(records, mutated)

    def test_forged_envelope_and_matching_forged_row_are_rejected(self):
        records, rows = fixtures()
        forged_envelope = {**records[0].envelope,
                           "provenance": {**records[0].envelope["provenance"],
                                          "origin_authority_verified": True}}
        forged_row = replace_like(rows[0], provenance=forged_envelope["provenance"])
        with self.assertRaisesRegex(ValueError, "envelope_mismatch"):
            build_staging_attack_previews(
                [replace(records[0], envelope=forged_envelope), *records[1:]],
                [forged_row, *rows[1:]],
            )

    def test_unreviewed_promotion_flag_is_rejected(self):
        records, rows = fixtures()
        with self.assertRaisesRegex(ValueError, "provenance"):
            build_staging_attack_previews(
                [replace(records[0], publication_allowed=True), *records[1:]], rows
            )


def replace_like(obj, **fields):
    return SimpleNamespace(**{**vars(obj), **fields})
