# SPDX-License-Identifier: AGPL-3.0-or-later
"""Source-checked October 2026 manifest: offline, no production connections."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from core.intel.maritime_attack_correlation import claim_from_source_observation
from core.intel.maritime_attack_staging_manifest import (
    prepare_staging_bulletin_manifest,
)

MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "docs/research/maritime-attack-source-check-2026-11-01.json"
)


def sample():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


class StagingBulletinManifestTests(TestCase):
    def test_six_real_source_links_prepare_without_publication(self):
        records = prepare_staging_bulletin_manifest(sample())
        self.assertEqual(len(records), 6)
        self.assertEqual(len({r.envelope["source_id"] for r in records}), 6)
        self.assertEqual(sum(r.bulletin.kind == "attack" for r in records), 4)
        self.assertEqual(sum(r.bulletin.kind == "suspicious_activity" for r in records), 1)
        self.assertEqual(sum(r.bulletin.kind == "piracy" for r in records), 1)
        for record in records:
            self.assertFalse(record.publication_allowed)
            self.assertFalse(record.origin_independence_verified)
            self.assertFalse(record.envelope["provenance"]["attack_corroboration_allowed"])
            self.assertFalse(record.envelope["provenance"]["origin_authority_verified"])
            self.assertFalse(record.envelope["provenance"]["reuse_rights_verified"])
            self.assertEqual(record.envelope["service"], "maritime")
            self.assertEqual(record.envelope["lane"], "safety")
            self.assertNotIn("publication_allowed", record.envelope)
            self.assertNotIn("source_text", record.envelope["raw_payload"])
            self.assertEqual(record.envelope["provenance"]["source_rights"], record.source_rights)
            self.assertEqual(record.envelope["provenance"]["source_checked_on_utc"], "2026-11-01")
            raw = json.loads(record.envelope["raw_payload"])
            self.assertEqual(raw["source_rights"], record.source_rights)
            # Check date is review metadata, not a source-document revision.
            self.assertNotIn("source_checked_on_utc", raw)

    def test_bulgarian_report_name_only_and_identity_must_stay_separate(self):
        record = prepare_staging_bulletin_manifest(sample())[0]
        self.assertEqual(record.envelope["source_url"], "https://www.mod.bg/news9664")
        self.assertEqual(record.envelope["subject_refs"], [])
        self.assertEqual(record.envelope["provenance"]["vessel_name"], "CONTSHIP JET")
        self.assertEqual(record.envelope["provenance"]["vessel_imo"], "")
        self.assertEqual(record.envelope["provenance"]["vessel_mmsi"], "")
        self.assertEqual(record.source_rights, "public_with_attribution")
        self.assertEqual(record.envelope["provenance"]["event_time_precision"], "exact")
        self.assertIsNone(record.envelope["provenance"]["published_at_utc"])

    def test_approximate_mscio_clock_retained_but_not_minute_precise(self):
        records = prepare_staging_bulletin_manifest(sample())
        attack = next(r for r in records if r.bulletin.bulletin_id == "159/26")
        self.assertEqual(attack.envelope["observed_at"], "2026-10-29T22:12:00+00:00")
        self.assertEqual(attack.envelope["provenance"]["event_time_precision"], "approximate")
        self.assertIsNone(attack.envelope["provenance"]["reported_time_uncertainty_minutes"])
        self.assertEqual(attack.source_rights, "restricted_republication")
        self.assertIsNone(attack.envelope["provenance"]["published_at_utc"])
        # A name-free report cannot be promoted to a ship-specific attack
        # by pretending an external MMSI appeared in the original bulletin.
        obs = SimpleNamespace(
            observation_id="synthetic:159", observation_type="official_maritime_bulletin",
            source_url=attack.envelope["source_url"],
            provenance=attack.envelope["provenance"],
            received_at=None, lat=None, lon=None, uncertainty_m=None,
        )
        with self.assertRaisesRegex(ValueError, "vessel identity differs"):
            claim_from_source_observation(obs, {
                "kind": "attack", "occurred_at": attack.bulletin.occurred_at,
                "imo": "9348625", "vessel_name": "CONTSHIP JET",
                "time_uncertainty_minutes": 0,
            })

    def test_suspicious_activity_is_not_relabelled_as_attack(self):
        records = prepare_staging_bulletin_manifest(sample())
        suspicious = next(r for r in records if r.bulletin.bulletin_id == "160/26")
        self.assertEqual(suspicious.bulletin.kind, "suspicious_activity")
        self.assertEqual(suspicious.envelope["provenance"]["bulletin_kind"], "suspicious_activity")

    def test_duplicate_source_and_fake_mod_identifiers_fail_closed(self):
        payload = sample()
        payload["records"].append(deepcopy(payload["records"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            prepare_staging_bulletin_manifest(payload)
        payload = sample()
        payload["records"][0]["imo"] = "9348625"
        with self.assertRaisesRegex(ValueError, "identifiers absent"):
            prepare_staging_bulletin_manifest(payload)
        payload = sample()
        payload["records"][0]["mmsi"] = "636019532"
        with self.assertRaisesRegex(ValueError, "identifiers absent"):
            prepare_staging_bulletin_manifest(payload)

    def test_unknown_fields_forged_rights_and_host_fail_closed(self):
        for key, value in (
            ("origin_authority_verified", True),
            ("attack_corroboration_allowed", True),
            ("publication_allowed", True),
        ):
            payload = sample()
            payload["records"][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Unexpected"):
                prepare_staging_bulletin_manifest(payload)
        payload = sample()
        payload["records"][0]["source_url"] = "https://www.mod.bg.evil.example/news9664"
        with self.assertRaises(ValueError):
            prepare_staging_bulletin_manifest(payload)
        payload = sample()
        payload["records"][1]["source_rights"] = "open_license"
        with self.assertRaisesRegex(ValueError, "rights"):
            prepare_staging_bulletin_manifest(payload)

    def test_canonical_url_alias_and_unhashable_fields_fail_closed(self):
        payload = sample()
        alias = deepcopy(payload["records"][1])
        alias["bulletin_id"] = "synthetic-alias-158"
        alias["source_url"] += "?utm_source=copy#repost"
        payload["records"].append(alias)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            prepare_staging_bulletin_manifest(payload)
        for key, bad in (
            ("source_rights", ["restricted_republication"]),
            ("imo", 9348625),
            ("source_document_sha256", None),
            ("lat", True),
        ):
            payload = sample()
            payload["records"][0][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                prepare_staging_bulletin_manifest(payload)
        payload = sample()
        payload["records"][0]["bulletin_id"] = "alias-of-news9664"
        payload["records"][0]["source_url"] += "?utm_source=mirror"
        payload["records"][0]["imo"] = "9348625"
        with self.assertRaisesRegex(ValueError, "identifiers absent"):
            prepare_staging_bulletin_manifest(payload)

    def test_future_source_dates_and_naive_clocks_fail_closed(self):
        payload = sample()
        payload["records"][1]["occurred_at_utc"] = "2026-11-03T10:00:00Z"
        with self.assertRaisesRegex(ValueError, "after check date"):
            prepare_staging_bulletin_manifest(payload)
        payload = sample()
        payload["records"][1]["occurred_at_utc"] = "2026-10-29T16:00:00"
        with self.assertRaisesRegex(ValueError, "Timezone"):
            prepare_staging_bulletin_manifest(payload)
        payload = sample()
        payload["records"][1]["event_time_approximate"] = False
        payload["records"][1]["reported_time_uncertainty_minutes"] = 20
        with self.assertRaises(ValueError):
            prepare_staging_bulletin_manifest(payload)
