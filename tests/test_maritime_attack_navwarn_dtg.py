# SPDX-License-Identifier: AGPL-3.0-or-later
"""Varna Radio NAVWARN 768/26: original date, IMO and wreck != attack."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from core.intel.maritime_attack_navwarn_dtg import parse_navwarn_compact_dtg
from core.intel.maritime_attack_staging_manifest import prepare_staging_bulletin_manifest
from core.intel.maritime_attack_staging_preview import build_staging_attack_previews

SOURCE = (Path(__file__).resolve().parents[1] /
          "docs/research/maritime-attack-varna-navwarn-768-2026-11-02.json")


def _manifest():
    return json.loads(SOURCE.read_text())


class VarnaNAVWARNDateTimeTests(TestCase):
    def test_282030_is_28_oct_2030_not_26_oct(self):
        self.assertEqual(
            parse_navwarn_compact_dtg("AT 282030 UTC OCT 26"),
            datetime(2026, 10, 28, 20, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(
            parse_navwarn_compact_dtg("282030 UTC OCT 26"),
            datetime(2026, 10, 28, 20, 30, tzinfo=timezone.utc),
        )

    def test_malformed_and_ambiguous_dtg_rejected(self):
        for dtg in (
            "AT 282030 UTC OCT 2026", "AT 282030 OCT 26",
            "AT 322030 UTC OCT 26", "AT 282460 UTC OCT 26",
            "AT 282030 UTC XXX 26", "26 OCT 2026 20:30",
            "AT 282030 UTC OCT 26 EXTRA", None,
        ):
            with self.subTest(dtg=dtg), self.assertRaises(ValueError):
                parse_navwarn_compact_dtg(dtg)

    def test_official_manifest_preserves_imo_wreck_role_and_dtg(self):
        records = prepare_staging_bulletin_manifest(_manifest())
        self.assertEqual(len(records), 1)
        envelope = records[0].envelope
        self.assertEqual(envelope["provenance"]["original_report_id"],
                         "BG_VTMIS:NAVWARN 768/26")
        self.assertEqual(envelope["provenance"]["original_dtg"],
                         "AT 282030 UTC OCT 26")
        self.assertEqual(envelope["provenance"]["occurred_at_utc"],
                         "2026-10-28T20:30:00+00:00")
        self.assertEqual(envelope["provenance"]["vessel_imo"], "9348625")
        self.assertEqual(envelope["provenance"]["vessel_mmsi"], "")
        self.assertEqual(envelope["provenance"]["location_role"], "hazard_position")
        self.assertEqual(envelope["subject_refs"], ["imo:9348625"])
        self.assertEqual(envelope["lat"], 43.13)
        self.assertEqual(envelope["lon"], 28.756)
        self.assertIsNone(envelope["uncertainty_m"])

    def test_navwarn_wreck_is_context_not_second_attack(self):
        record = prepare_staging_bulletin_manifest(_manifest())[0]
        e = record.envelope
        key = f'{e["source_name"]}:{e["source_id"]}'
        row = SimpleNamespace(
            observation_id="obs:" + hashlib.blake2s(
                key.encode(), digest_size=16).hexdigest(),
            service=e["service"], lane=e["lane"],
            observation_type=e["observation_type"],
            source_policy=e["source_policy"],
            source_name=e["source_name"], source_id=e["source_id"],
            source_url=e["source_url"],
            raw_payload_hash=hashlib.sha256(e["raw_payload"].encode()).hexdigest(),
            observed_at=e["observed_at"], received_at="2026-11-02T05:30:00+00:00",
            lat=e["lat"], lon=e["lon"],
            uncertainty_m=e["uncertainty_m"], location_precision=None,
            subject_refs=e["subject_refs"], provenance=e["provenance"],
        )
        preview = build_staging_attack_previews([record], [row])[0]
        self.assertEqual(preview["source_kind"], "navigational_hazard")
        self.assertEqual(preview["review_status"], "context_only")
        self.assertIsNone(preview["proposed_incident_type"])
        self.assertEqual(preview["reported_location"]["role"], "hazard_position")
        self.assertEqual(preview["occurred_at_utc"], "2026-10-28T20:30:00+00:00")
        self.assertEqual(preview["vessel_imo_as_reported"], "9348625")
        self.assertIn("not_an_attack", preview["review_blockers"])
        self.assertFalse(preview["publication_allowed"])
        self.assertEqual(preview["independent_origins_verified"], 0)

    def test_wrong_day_or_missing_dtg_rejected(self):
        for change in (
            {"occurred_at_utc": "2026-10-26T20:30:00+00:00"},
            {"occurred_at_utc": "2026-10-28T10:00:00+00:00"},
            {"source_dtg": "AT 262030 UTC OCT 26"},
            {"source_dtg": None},
        ):
            manifest = _manifest()
            manifest["records"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_staging_bulletin_manifest(manifest)

    def test_dtg_cannot_be_smuggled_into_other_issuer(self):
        manifest = _manifest()
        manifest["records"][0]["issuer"] = "BG_MOD"
        with self.assertRaises(ValueError):
            prepare_staging_bulletin_manifest(manifest)
