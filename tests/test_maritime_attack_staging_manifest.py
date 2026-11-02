# SPDX-License-Identifier: AGPL-3.0-or-later
"""Source-checked October 2026 manifest: offline, no production connections."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from core.intel.maritime_attack_correlation import claim_from_source_observation
from core.intel.maritime_attack_staging_manifest import (
    prepare_staging_bulletin_manifest,
)
from core.intel.official_maritime_bulletin import prepare_official_bulletin

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

    def test_late_report_mscio_163_preserves_day_only_and_unknown_vessel(self):
        path = MANIFEST.parent / "maritime-attack-mscio-163-2026-11-02.json"
        records = prepare_staging_bulletin_manifest(
            json.loads(path.read_text(encoding="utf-8"))
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.bulletin.bulletin_id, "163/26")
        self.assertIsNone(record.bulletin.occurred_at)
        self.assertEqual(record.bulletin.event_date.isoformat(), "2026-10-28")
        self.assertEqual(record.bulletin.publication_date.isoformat(), "2026-10-30")
        self.assertEqual(record.envelope["provenance"]["event_time_precision"], "day")
        self.assertEqual(record.envelope["provenance"]["vessel_name"], "")
        self.assertEqual(record.envelope["provenance"]["vessel_imo"], "")
        self.assertEqual(record.envelope["provenance"]["vessel_mmsi"], "")
        self.assertFalse(record.origin_independence_verified)
        self.assertFalse(record.publication_allowed)
        # A late, unnamed bulletin cannot acquire LOUISE 1 or any other
        # identity merely because a downstream article mentions that ship.
        obs = SimpleNamespace(
            observation_id="synthetic:163", observation_type="official_maritime_bulletin",
            source_url=record.envelope["source_url"],
            provenance=record.envelope["provenance"],
            received_at=None, lat=None, lon=None, uncertainty_m=None,
        )
        with self.assertRaisesRegex(ValueError, "vessel identity differs"):
            claim_from_source_observation(obs, {
                "kind": "attack", "occurred_at": "2026-10-28T00:00:00Z",
                "vessel_name": "LOUISE 1", "imo": "9290323",
            })

    def test_mscio_164_mayday_relay_is_unnamed_and_not_independent(self):
        path = MANIFEST.parent / "maritime-attack-mscio-164-2026-11-02.json"
        records = prepare_staging_bulletin_manifest(
            json.loads(path.read_text(encoding="utf-8"))
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.bulletin.bulletin_id, "164/26")
        self.assertEqual(
            record.bulletin.occurred_at.isoformat(), "2026-11-01T15:09:00+00:00"
        )
        self.assertEqual(record.bulletin.publication_date.isoformat(), "2026-11-01")
        self.assertEqual(record.envelope["provenance"]["event_time_precision"], "approximate")
        self.assertEqual(record.envelope["provenance"]["vessel_name"], "")
        self.assertEqual(record.envelope["provenance"]["vessel_imo"], "")
        self.assertEqual(record.envelope["provenance"]["vessel_mmsi"], "")
        self.assertEqual(record.envelope["subject_refs"], [])
        self.assertFalse(record.origin_independence_verified)
        self.assertFalse(record.publication_allowed)
        self.assertFalse(record.envelope["provenance"]["origin_authority_verified"])
        self.assertEqual(record.source_rights, "restricted_republication")
        # A relay of another ship's Mayday is not the Master's own attack
        # testimony, nor does it identify UKMTO 192/26's different tanker.
        obs = SimpleNamespace(
            observation_id="synthetic:164", observation_type="official_maritime_bulletin",
            source_url=record.envelope["source_url"],
            provenance=record.envelope["provenance"],
            received_at=None, lat=None, lon=None, uncertainty_m=None,
        )
        with self.assertRaisesRegex(ValueError, "vessel identity differs"):
            claim_from_source_observation(obs, {
                "kind": "attack", "occurred_at": record.bulletin.occurred_at,
                "vessel_name": "LOUISE 1", "imo": "9290323",
            })

    def test_mscio_164_and_october_alerts_have_distinct_source_ids(self):
        november = json.loads(
            (MANIFEST.parent / "maritime-attack-mscio-164-2026-11-02.json")
            .read_text(encoding="utf-8")
        )
        payload = sample()
        payload["source_checked_on_utc"] = "2026-11-02"
        payload["records"].extend(november["records"])
        prepared = prepare_staging_bulletin_manifest(payload)
        self.assertEqual(len(prepared), 7)
        self.assertEqual(len({r.envelope["source_id"] for r in prepared}), 7)
        self.assertFalse(prepared[-1].origin_independence_verified)
        self.assertFalse(prepared[-1].publication_allowed)

    def test_mscio_146_late_report_keeps_unnamed_container_and_uncertainty(self):
        path = MANIFEST.parent / "maritime-attack-mscio-146-2026-11-02.json"
        records = prepare_staging_bulletin_manifest(
            json.loads(path.read_text(encoding="utf-8"))
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.bulletin.bulletin_id, "146/26")
        self.assertEqual(
            record.bulletin.occurred_at.isoformat(),
            "2026-10-13T17:00:00+00:00",
        )
        self.assertEqual(record.bulletin.publication_date.isoformat(), "2026-10-14")
        self.assertEqual(record.envelope["provenance"]["event_time_precision"], "approximate")
        self.assertEqual(record.envelope["provenance"]["vessel_name"], "")
        self.assertEqual(record.envelope["provenance"]["vessel_imo"], "")
        self.assertEqual(record.envelope["provenance"]["vessel_mmsi"], "")
        self.assertFalse(record.origin_independence_verified)
        self.assertFalse(record.publication_allowed)

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

    def test_day_only_source_chronology_and_direct_adapter_are_fail_closed(self):
        payload = sample()
        report = payload["records"][1]
        # The source's reported attack is 29 October. A 27 October
        # publication cannot be explained by any publisher time zone.
        report["publication_date"] = "2026-10-27"
        with self.assertRaisesRegex(ValueError, "publication day precedes"):
            prepare_staging_bulletin_manifest(payload)
        # One-day difference is permitted for publisher-local dates.
        report["publication_date"] = "2026-10-28"
        accepted = prepare_staging_bulletin_manifest(payload)[1]
        self.assertFalse(accepted.publication_allowed)
        # Bypassing the manifest must not bypass the chronology gate.
        with self.assertRaisesRegex(ValueError, "publication day precedes"):
            prepare_official_bulletin(replace(
                accepted.bulletin, publication_date=date(2026, 10, 27)
            ))
        with self.assertRaisesRegex(ValueError, "publication precedes"):
            prepare_official_bulletin(replace(
                accepted.bulletin, publication_date=None,
                published_at=datetime(2026, 10, 29, 15, 59, tzinfo=timezone.utc),
            ))
        # A documented approximate clock may overlap publication by minutes.
        valid = prepare_official_bulletin(replace(
            accepted.bulletin, publication_date=None,
            published_at=datetime(2026, 10, 29, 15, 57, tzinfo=timezone.utc),
            reported_time_uncertainty_minutes=5,
        ))
        self.assertFalse(valid["provenance"]["attack_corroboration_allowed"])

    def test_source_publication_cannot_precede_event_clock(self):
        payload = sample()
        payload["records"][1].pop("publication_date")
        payload["records"][1]["published_at_utc"] = "2026-10-29T15:59:00Z"
        with self.assertRaisesRegex(ValueError, "publication precedes"):
            prepare_staging_bulletin_manifest(payload)
        payload["records"][1]["published_at_utc"] = "2026-10-29T16:00:00Z"
        records = prepare_staging_bulletin_manifest(payload)
        self.assertEqual(records[1].bulletin.bulletin_id, "158/26")

    def test_approximate_publication_chronology_uses_only_documented_bound(self):
        payload = sample()
        report = payload["records"][1]
        report.pop("publication_date", None)
        report["published_at_utc"] = "2026-10-29T15:57:00Z"
        report["reported_time_uncertainty_minutes"] = 5
        prepared = prepare_staging_bulletin_manifest(payload)
        self.assertEqual(prepared[1].bulletin.reported_time_uncertainty_minutes, 5)
        self.assertFalse(prepared[1].publication_allowed)
        report["published_at_utc"] = "2026-10-29T15:54:59Z"
        with self.assertRaisesRegex(ValueError, "publication precedes"):
            prepare_staging_bulletin_manifest(payload)
        report["published_at_utc"] = "2026-10-29T15:57:00Z"
        report.pop("reported_time_uncertainty_minutes")
        with self.assertRaisesRegex(ValueError, "publication precedes"):
            prepare_staging_bulletin_manifest(payload)

    def test_azini_post_hijack_positions_are_not_attack_geometry(self):
        record = next(
            r for r in prepare_staging_bulletin_manifest(sample())
            if r.bulletin.bulletin_id == "161/26"
        )
        self.assertEqual(record.bulletin.kind, "piracy")
        self.assertEqual(record.bulletin.vessel_name, "AZINI")
        self.assertEqual(record.bulletin.occurred_at.isoformat(),
                         "2026-10-29T09:00:00+00:00")
        self.assertIsNone(record.bulletin.lat)
        self.assertIsNone(record.bulletin.lon)
        self.assertEqual(record.bulletin.imo, "")
        self.assertEqual(record.bulletin.mmsi, "")
        self.assertFalse(record.publication_allowed)
        self.assertFalse(record.origin_independence_verified)

    def test_mscio_148_tanker_rpg_is_unidentified_and_not_promotable(self):
        path = MANIFEST.parent / "maritime-attack-mscio-148-2026-11-02.json"
        records = prepare_staging_bulletin_manifest(
            json.loads(path.read_text(encoding="utf-8"))
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.bulletin.bulletin_id, "148/26")
        self.assertEqual(
            record.bulletin.occurred_at.isoformat(),
            "2026-10-16T19:22:00+00:00",
        )
        self.assertEqual(record.bulletin.publication_date.isoformat(), "2026-10-17")
        self.assertEqual(record.envelope["provenance"]["event_time_precision"], "approximate")
        self.assertEqual(record.envelope["provenance"]["vessel_name"], "")
        self.assertEqual(record.envelope["provenance"]["vessel_imo"], "")
        self.assertEqual(record.envelope["provenance"]["vessel_mmsi"], "")
        self.assertEqual(record.envelope["subject_refs"], [])
        self.assertEqual(record.source_rights, "restricted_republication")
        self.assertFalse(record.origin_independence_verified)
        self.assertFalse(record.publication_allowed)
        self.assertFalse(record.envelope["provenance"]["origin_authority_verified"])
