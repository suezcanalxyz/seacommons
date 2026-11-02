# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression tests for staging-only AIS contextual correlation."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase

from core.intel.maritime_attack_correlation import VesselRef
from core.intel.maritime_attack_staging_ais_context import build_staging_ais_context


def _dt(clock: str) -> datetime:
    return datetime.fromisoformat(clock.replace("Z", "+00:00"))


def _row(clock: str, sog: float, *, mmsi: str = "636019532",
         lat: float = 43.259, lon: float = 28.815):
    stamp = _dt(clock)
    return SimpleNamespace(
        mmsi=mmsi, ts=stamp.replace(tzinfo=None),
        received_at=stamp.replace(tzinfo=None),
        sog=sog, lat=lat, lon=lon,
    )


def _preview():
    return {
        "preview_id": "staging-attack-preview:jet",
        "canonical_observation_id": "obs:jet",
        "staging_only": True,
        "publication_allowed": False,
        "review_status": "candidate",
        "proposed_incident_type": "maritime_attack",
        "vessel_name_as_reported": "CONTSHIP JET",
        # The Bulgarian MOD primary document does not assert IMO/MMSI.
        "vessel_imo_as_reported": "",
        "vessel_mmsi_as_reported": "",
        "occurred_at_utc": "2026-10-28T10:00:00+00:00",
        "event_time_precision": "exact",
        "reported_location": None,
        "review_blockers": ["incident_location_unverified",
                            "strong_vessel_identity_unverified"],
    }


CROSSWALK = VesselRef(imo="9348625", mmsi="636019532", name="CONTSHIP JET")
URL = "https://example.org/ships/9348625"


class StagingAISContextTests(TestCase):
    def _build(self, preview=None, tracks=None, crosswalk=CROSSWALK, url=URL):
        if preview is None:
            preview = _preview()
        if tracks is None:
            tracks = [
                _row("2026-10-28T09:59:22+00:00", 10.2, lat=43.2659267, lon=28.8149),
                _row("2026-10-28T10:34:46+00:00", 0.6, lat=43.2591967, lon=28.81574),
            ]
        return build_staging_ais_context(
            preview, crosswalk, tracks, crosswalk_source_url=url
        )

    def test_contship_jet_real_ais_context_not_attack_proof(self):
        preview = _preview()
        result = self._build(preview)
        self.assertEqual(result["crosswalk"]["imo"], "9348625")
        self.assertEqual(result["crosswalk"]["mmsi"], "636019532")
        self.assertEqual(result["crosswalk"]["verification_status"],
                         "external_identity_requires_review")
        self.assertFalse(result["crosswalk"]["asserted_by_original_bulletin"])
        self.assertTrue(result["sudden_stop_signal"])
        self.assertTrue(result["ais_coverage_gap_signal"])
        self.assertAlmostEqual(result["ais_sampling_gap_minutes"], 35.4, delta=0.02)
        self.assertEqual(result["ais_fixes_in_6h_window"], 2)
        self.assertEqual(result["receipt_latency_status"], "legacy_equal_event_clock")
        self.assertEqual(result["nearest_before"]["sog_knots"], 10.2)
        self.assertEqual(result["nearest_after"]["sog_knots"], 0.6)
        self.assertEqual(result["nearest_before"]["position_role"], "ais_vessel_track_only")
        self.assertFalse(result["incident_site_from_ais"])
        self.assertFalse(result["ais_as_attack_proof"])
        self.assertEqual(result["independent_origins_verified"], 0)
        self.assertFalse(result["publication_allowed"])
        self.assertTrue(result["staging_only"])
        self.assertIsNone(preview["reported_location"])
        self.assertIn("incident_location_unverified", preview["review_blockers"])

    def test_context_only_or_publication_enabled_is_rejected(self):
        for changes in (
            {"review_status": "context_only", "proposed_incident_type": None},
            {"publication_allowed": True},
            {"staging_only": False},
            {"proposed_incident_type": "humanitarian_drift"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self._build({**_preview(), **changes})

    def test_crosswalk_conflicts_and_untrusted_url_rejected(self):
        for crosswalk in (
            VesselRef(imo="9348620", mmsi="636019532", name="CONTSHIP JET"),
            VesselRef(imo="9348625", mmsi="000000000", name="CONTSHIP JET"),
            VesselRef(imo="9348625", mmsi="636019532", name="OTHER VESSEL"),
        ):
            with self.subTest(crosswalk=crosswalk), self.assertRaises(ValueError):
                self._build(crosswalk=crosswalk)
        for url in ("http://example.org/ship", "https://localhost/ship", "file:///ship"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self._build(url=url)
        for changed in (
            {"vessel_imo_as_reported": "1234567"},
            {"vessel_mmsi_as_reported": "123456789"},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self._build({**_preview(), **changed})

    def test_foreign_or_conflicting_track_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "foreign_mmsi"):
            self._build(tracks=[_row("2026-10-28T10:00:00Z", 0, mmsi="123456789")])
        with self.assertRaisesRegex(ValueError, "conflicting_ais_fixes"):
            self._build(tracks=[
                _row("2026-10-28T10:00:00Z", 10),
                _row("2026-10-28T10:00:00Z", 0),
            ])
        with self.assertRaisesRegex(ValueError, "unbounded_ais"):
            self._build(tracks=[_row("2026-10-28T10:00:00Z", 10)] * 257)

    def test_approximate_or_missing_event_clock_cannot_make_stop_claim(self):
        for changed in (
            {"event_time_precision": "approximate"},
            {"occurred_at_utc": None, "event_time_precision": "day"},
        ):
            result = self._build({**_preview(), **changed})
            self.assertFalse(result["sudden_stop_signal"])
            self.assertFalse(result["ais_coverage_gap_signal"])
        with self.assertRaisesRegex(ValueError, "invalid_preview_event_clock"):
            self._build({**_preview(), "occurred_at_utc": "2026-10-28T10:00:00"})

    def test_no_tracks_or_slowdown_not_corroboration(self):
        empty = self._build(tracks=[])
        self.assertIsNone(empty["nearest_before"])
        self.assertIsNone(empty["nearest_after"])
        self.assertFalse(empty["sudden_stop_signal"])
        steady = self._build(tracks=[
            _row("2026-10-28T09:59:22Z", 10.2),
            _row("2026-10-28T10:34:46Z", 9.8),
        ])
        self.assertFalse(steady["sudden_stop_signal"])
        self.assertFalse(steady["ais_as_attack_proof"])
        self.assertFalse(steady["publication_allowed"])

    def test_teleporting_ais_track_cannot_support_sudden_stop(self):
        result = self._build(tracks=[
            _row("2026-10-28T09:59:22Z", 10.2, lat=43.2659, lon=28.8149),
            _row("2026-10-28T10:34:46Z", 0.6, lat=49.2592, lon=35.8157),
        ])
        self.assertTrue(result["ais_kinematic_conflict_signal"])
        self.assertFalse(result["sudden_stop_signal"])
        self.assertTrue(result["ais_coverage_gap_signal"])
        self.assertFalse(result["ais_as_attack_proof"])
        self.assertFalse(result["incident_site_from_ais"])
        self.assertFalse(result["publication_allowed"])

    def test_ais_future_relative_to_receipt_is_rejected(self):
        invalid = _row("2026-10-28T10:34:46Z", 0.6)
        invalid.received_at = _dt("2026-10-28T10:20:00Z").replace(tzinfo=None)
        with self.assertRaisesRegex(ValueError, "ais_fix_observed_after_receipt"):
            self._build(tracks=[invalid])

    def test_small_receipt_clock_skew_does_not_create_attack_proof(self):
        fix = _row("2026-10-28T10:34:46Z", 0.6)
        fix.received_at = _dt("2026-10-28T10:31:00Z").replace(tzinfo=None)
        result = self._build(tracks=[fix])
        self.assertFalse(result["ais_kinematic_conflict_signal"])
        self.assertFalse(result["sudden_stop_signal"])
        self.assertFalse(result["ais_as_attack_proof"])
        self.assertFalse(result["publication_allowed"])

    def test_duplicate_identical_fix_is_deduplicated(self):
        fix = _row("2026-10-28T09:59:22Z", 10.2)
        result = self._build(tracks=[fix, fix])
        self.assertEqual(result["ais_fixes_in_6h_window"], 1)
        self.assertFalse(result["sudden_stop_signal"])
