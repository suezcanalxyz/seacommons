# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline staging contracts for original maritime-bulletin ingestion."""
from dataclasses import replace
from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch
from types import ModuleType, SimpleNamespace

from core.intel.maritime_attack_correlation import claim_from_source_observation
from core.intel.official_maritime_bulletin import (
    OfficialMaritimeBulletin, ingest_official_bulletin, prepare_official_bulletin,
)

UTC = timezone.utc


def jet():
    return OfficialMaritimeBulletin(
        issuer="BG_MOD", bulletin_id="news9664",
        source_url="https://www.mod.bg/news9664", kind="attack",
        # The original Ministry text names the ship but omits IMO/MMSI.
        vessel_name="CONTSHIP JET",
        occurred_at=datetime(2026, 10, 28, 10, tzinfo=UTC),
        publication_date=date(2026, 10, 28),
    )


def synthetic_identified_jet():
    """Invented document for identifier guards; NOT a real BG MOD release."""
    return replace(
        jet(), bulletin_id="synthetic-identified-jet",
        source_url="https://www.mod.bg/synthetic/identified-jet",
        imo="9348625", mmsi="636019532",
    )


class OfficialBulletinTests(TestCase):
    def test_contship_jet_primary_document_is_canonical_but_not_auto_verified(self):
        result = prepare_official_bulletin(jet())
        assert result["source_name"] == "Bulgarian Ministry of Defence"
        assert result["subject_refs"] == []
        assert result["provenance"]["vessel_imo"] == ""
        assert result["provenance"]["vessel_mmsi"] == ""
        assert result["observed_at"] == "2026-10-28T10:00:00+00:00"
        assert result["provenance"]["publication_date"] == "2026-10-28"
        assert result["provenance"]["published_at_utc"] is None
        assert result["provenance"]["origin_authority_verified"] is False
        assert result["provenance"]["attack_corroboration_allowed"] is False
        assert result["provenance"]["reuse_rights_verified"] is False
        assert "three drone impacts" not in result["raw_payload"]


    def test_replay_is_stable_but_document_revision_is_append_only(self):
        first = prepare_official_bulletin(jet())
        replay = prepare_official_bulletin(jet())
        changed = prepare_official_bulletin(replace(jet(), vessel_name="CONTSHIP JET (updated)"))
        assert first["source_id"] == replay["source_id"]
        assert first["raw_payload"] == replay["raw_payload"]
        assert first["source_id"] != changed["source_id"]
        assert first["provenance"]["original_report_id"] == changed["provenance"]["original_report_id"]


    def test_source_rights_check_date_are_immutable_provenance_not_permission(self):
        import json

        legacy = prepare_official_bulletin(jet())
        # Legacy direct-call source hashes/raw payloads remain unchanged:
        # new metadata is opt-in and does not silently mutate old revisions.
        self.assertNotIn("source_rights", json.loads(legacy["raw_payload"]))
        self.assertNotIn("source_checked_on_utc", json.loads(legacy["raw_payload"]))
        self.assertEqual(legacy["provenance"]["source_rights"], "unknown")

        reviewed = prepare_official_bulletin(replace(
            jet(), source_rights="restricted_republication",
            source_checked_on_utc=date(2026, 11, 1),
        ))
        self.assertNotEqual(legacy["source_id"], reviewed["source_id"])
        self.assertEqual(reviewed["provenance"]["source_rights"], "restricted_republication")
        self.assertEqual(reviewed["provenance"]["source_checked_on_utc"], "2026-11-01")
        self.assertFalse(reviewed["provenance"]["reuse_rights_verified"])
        self.assertFalse(reviewed["provenance"]["attack_corroboration_allowed"])
        self.assertEqual(json.loads(reviewed["raw_payload"])["source_rights"], "restricted_republication")
        self.assertNotIn("source_checked_on_utc", json.loads(reviewed["raw_payload"]))
        rechecked = prepare_official_bulletin(replace(
            jet(), source_rights="restricted_republication",
            source_checked_on_utc=date(2026, 11, 2),
        ))
        self.assertEqual(reviewed["source_id"], rechecked["source_id"])
        self.assertEqual(reviewed["raw_payload"], rechecked["raw_payload"])
        self.assertEqual(rechecked["provenance"]["source_checked_on_utc"], "2026-11-02")

    def test_source_rights_and_check_date_reject_forged_values(self):
        for value in ("open_license", "PUBLIC_WITH_ATTRIBUTION", True, [], ""):
            with self.subTest(rights=value), self.assertRaises(ValueError):
                prepare_official_bulletin(replace(jet(), source_rights=value))
        for value in ("2026-11-01", datetime(2026, 11, 1, tzinfo=UTC), date(2026, 10, 27)):
            with self.subTest(check_date=value), self.assertRaises(ValueError):
                prepare_official_bulletin(replace(jet(), source_checked_on_utc=value))

    def test_bulgarian_prosecutor_filing_is_procedural_not_attack_witness(self):
        # The 29 Oct official prosecutor release confirms an investigation
        # referred by military police, not an independent observation of impact.
        filing = OfficialMaritimeBulletin(
            issuer="BG_PROSECUTOR", bulletin_id="80101",
            source_url=("https://prb.bg/bg/news/aktualno/"
                        "80101-voenno-okrazhna-prokuratura-sofiya-"
                        "obrazuva-dosadebno-proizvodstvo-za-napadeniet"),
            kind="investigation", vessel_name="CONTSHIP JET",
            publication_date=date(2026, 10, 29),
        )
        prepared = prepare_official_bulletin(filing)
        assert prepared["source_name"] == "Bulgarian Prosecutor Office"
        assert prepared["subject_refs"] == []
        assert prepared["observed_at"] == "2026-10-29"
        assert prepared["provenance"]["event_time_precision"] == "unknown"
        assert prepared["provenance"]["observed_at_semantics"] == "publication"
        assert prepared["provenance"]["origin_authority_verified"] is False
        assert prepared["provenance"]["attack_corroboration_allowed"] is False
        assert claim_from_source_observation(self.observation(filing), {
            "kind": "attack",
            "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
            "vessel_name": "CONTSHIP JET",
        }) is None


    def test_mscio_relay_cannot_manufacture_an_independent_authority(self):
        warning = OfficialMaritimeBulletin(
            issuer="MSCIO", bulletin_id="159/26",
            source_url="https://mscio.eu/alerts/195", kind="attack",
            event_date=date(2026, 10, 29),
            publication_date=date(2026, 10, 30),
        )
        result = prepare_official_bulletin(warning)
        assert result["observed_at"] == "2026-10-29"
        assert result["provenance"]["event_time_precision"] == "day"
        assert result["provenance"]["publication_date"] == "2026-10-30"
        assert result["provenance"]["published_at_utc"] is None
        assert result["provenance"]["origin_authority_verified"] is False
        assert result["subject_refs"] == []


    def test_suspicious_activity_never_becomes_attack(self):
        warning = OfficialMaritimeBulletin(
            issuer="MSCIO", bulletin_id="160/26",
            source_url="https://mscio.eu/alerts/196",
            kind="suspicious_activity",
            event_date=date(2026, 10, 30),
        )
        result = prepare_official_bulletin(warning)
        assert '"kind":"suspicious_activity"' in result["raw_payload"]
        assert result["provenance"]["attack_corroboration_allowed"] is False


    def test_ukmto_suspicious_dhow_is_not_attack_evidence(self):
        bulletin = OfficialMaritimeBulletin(
            issuer="UKMTO", bulletin_id="185/26",
            source_url="https://www.ukmto.org/recent-incidents",
            kind="suspicious_activity",
            event_date=date(2026, 10, 29),
        )
        result = prepare_official_bulletin(bulletin)
        assert result["source_name"] == "UKMTO"
        assert result["provenance"]["origin_authority_verified"] is False
        assert result["provenance"]["attack_corroboration_allowed"] is False

    def test_riti_navarea_anchorage_is_not_assumed_impact_location(self):
        warning = OfficialMaritimeBulletin(
            issuer="NAVAREA_IX", bulletin_id="420/26",
            source_url="https://hydrography.paknavy.gov.pk/navarea-ix-warnings/",
            kind="navigational_hazard", vessel_name="RITI",
            imo="9249075", mmsi="352002473",
            publication_date=date(2026, 10, 30),
            lat=26.401167, lon=56.412, location_uncertainty_km=10.0,
            location_role="anchorage",
        )
        result = prepare_official_bulletin(warning)
        assert result["observed_at"] == "2026-10-30"
        assert result["provenance"]["observed_at_semantics"] == "publication"
        assert result["uncertainty_m"] == 10000
        assert result["provenance"]["event_time_precision"] == "unknown"
        assert result["provenance"]["location_role"] == "anchorage"


    def test_untrusted_or_invalid_url_rejected(self):
        for url in (
            "http://www.mod.bg/news9664",
            "https://www.mod.bg.evil.example/news9664",
            "https://user:password@www.mod.bg/news9664",
            "https://localhost/news9664",
            "https://www.mod.bg:8443/news9664",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    prepare_official_bulletin(replace(jet(), source_url=url))

    def test_bad_or_contradictory_input_is_rejected(self):
        changes = (
            {"imo": "9348624"},
            {"mmsi": "123"},
            {"lat": 43.1},
            {"lat": float("nan"), "lon": 28.8},
            {"lat": 93.0, "lon": 28.8},
            {"location_uncertainty_km": -1.0},
            {"occurred_at": datetime(2026, 10, 28, 10)},
            {"event_date": date(2026, 10, 28)},
            {"published_at": datetime(2026, 10, 28, 11)},
            {"bulletin_id": "foo\\nbar"},
            {"kind": "confirmed_attacker_russia"},
            {"source_document_sha256": "not-a-sha"},
        )
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    prepare_official_bulletin(replace(jet(), **change))

    @staticmethod
    def observation(bulletin):
        prepared = prepare_official_bulletin(bulletin)
        return SimpleNamespace(
            observation_id="obs:reviewed-bulletin-test",
            observation_type=prepared["observation_type"],
            source_url=prepared["source_url"],
            provenance=prepared["provenance"],
            received_at=datetime(2026, 10, 30, 12, tzinfo=UTC),
            lat=prepared["lat"], lon=prepared["lon"],
            uncertainty_m=prepared["uncertainty_m"],
        )

    def test_anchorage_coordinates_cannot_become_attack_location(self):
        bulletin = replace(
            synthetic_identified_jet(), lat=43.25, lon=28.81,
            location_uncertainty_km=12, location_role="anchorage",
        )
        obs = self.observation(bulletin)
        claim = claim_from_source_observation(obs, {
            "kind": "attack", "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
            "imo": "9348625", "mmsi": "636019532",
            "lat": 43.25, "lon": 28.81,
            "uncertainty_km": 0, "time_uncertainty_minutes": 0,
        })
        assert claim is not None
        assert claim.lat is None and claim.lon is None
        assert claim.source_group == ""

    def test_incident_site_cannot_be_moved_or_made_more_precise(self):
        bulletin = replace(
            synthetic_identified_jet(), lat=43.25, lon=28.81,
            location_uncertainty_km=12, location_role="incident_site",
        )
        obs = self.observation(bulletin)
        extracted = {
            "kind": "attack", "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
            "imo": "9348625", "mmsi": "636019532",
            "lat": 43.25, "lon": 28.81,
            "uncertainty_km": 0, "time_uncertainty_minutes": 0,
        }
        claim = claim_from_source_observation(obs, extracted)
        assert (claim.lat, claim.lon, claim.uncertainty_km) == (43.25, 28.81, 12.0)
        with self.assertRaisesRegex(ValueError, "site differs"):
            claim_from_source_observation(obs, {**extracted, "lat": 43.0})

    def test_date_only_cannot_become_minute_precision(self):
        bulletin = replace(
            synthetic_identified_jet(), occurred_at=None, event_date=date(2026, 10, 28),
        )
        claim = claim_from_source_observation(self.observation(bulletin), {
            "kind": "attack", "occurred_at": datetime(2026, 10, 28, tzinfo=UTC),
            "imo": "9348625", "time_uncertainty_minutes": 0,
        })
        assert claim is not None
        assert claim.time_uncertainty_minutes >= 1440
        with self.assertRaisesRegex(ValueError, "event date differs"):
            claim_from_source_observation(self.observation(bulletin), {
                "kind": "attack", "occurred_at": datetime(2026, 10, 29, tzinfo=UTC),
                "imo": "9348625", "time_uncertainty_minutes": 0,
            })

    def test_approximate_official_clock_is_not_minute_exact(self):
        # MSCIO-style "approximately 22:12 UTC" keeps the reported clock,
        # but cannot be counted as a precision-qualified second witness.
        approx = replace(synthetic_identified_jet(), event_time_approximate=True)
        prepared = prepare_official_bulletin(approx)
        assert prepared["provenance"]["event_time_precision"] == "approximate"
        assert prepared["provenance"]["occurred_at_utc"] == "2026-10-28T10:00:00+00:00"
        assert prepared["provenance"]["reported_time_uncertainty_minutes"] is None
        extracted = {
            "kind": "attack", "occurred_at": approx.occurred_at,
            "imo": "9348625", "vessel_name": "CONTSHIP JET",
            "time_uncertainty_minutes": 0,
        }
        claim = claim_from_source_observation(self.observation(approx), extracted)
        assert claim is not None
        assert claim.time_uncertainty_minutes == 1440.0
        bounded = replace(approx, reported_time_uncertainty_minutes=45)
        bounded_claim = claim_from_source_observation(
            self.observation(bounded), extracted
        )
        assert bounded_claim.time_uncertainty_minutes == 45.0
        for invalid in (0, -1, float("nan"), 1441, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    prepare_official_bulletin(replace(
                        approx, reported_time_uncertainty_minutes=invalid
                    ))
        with self.assertRaises(ValueError):
            prepare_official_bulletin(replace(
                jet(), reported_time_uncertainty_minutes=30
            ))
        with self.assertRaises(ValueError):
            prepare_official_bulletin(replace(
                jet(), occurred_at=None, event_time_approximate=True
            ))

    def test_publication_only_and_reclassified_bulletin_cannot_be_attack(self):
        publication_only = replace(synthetic_identified_jet(), occurred_at=None)
        assert claim_from_source_observation(self.observation(publication_only), {
            "kind": "attack", "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
            "imo": "9348625", "time_uncertainty_minutes": 0,
        }) is None
        suspicious = replace(synthetic_identified_jet(), kind="suspicious_activity")
        assert claim_from_source_observation(self.observation(suspicious), {
            "kind": "attack", "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
            "imo": "9348625", "time_uncertainty_minutes": 0,
        }) is None

    def test_exact_bulletin_time_and_unclassified_position_fail_closed(self):
        obs = self.observation(synthetic_identified_jet())
        with self.assertRaisesRegex(ValueError, "event timestamp differs"):
            claim_from_source_observation(obs, {
                "kind": "attack", "occurred_at": datetime(2026, 10, 28, 11, tzinfo=UTC),
                "imo": "9348625", "time_uncertainty_minutes": 0,
            })
        with self.assertRaisesRegex(ValueError, "documented location role"):
            prepare_official_bulletin(replace(jet(), lat=43.25, lon=28.81))
        with self.assertRaisesRegex(ValueError, "Location role without coordinates"):
            prepare_official_bulletin(replace(jet(), location_role="anchorage"))

    def test_extraction_cannot_swap_official_imo_or_mmsi(self):
        obs = self.observation(synthetic_identified_jet())
        original = {
            "kind": "attack", "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
            "imo": "9348625", "mmsi": "636019532",
            "vessel_name": "CONTSHIP JET",
        }
        assert claim_from_source_observation(obs, original).vessel.imo == "9348625"
        for changed in (
            {"imo": "9249075"},  # RITI's different, valid IMO
            {"mmsi": "352002473"},
            {"vessel_name": "RITI"},
        ):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(ValueError, "vessel identity differs"):
                    claim_from_source_observation(obs, {**original, **changed})

    def test_real_bulgarian_report_cannot_be_silently_enriched_with_imo_mmsi(self):
        obs = self.observation(jet())
        claim = claim_from_source_observation(obs, {
            "kind": "attack",
            "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
            "vessel_name": "CONTSHIP JET",
        })
        assert claim is not None
        assert claim.vessel.imo == "" and claim.vessel.mmsi == ""
        for injected in ({"imo": "9348625"}, {"mmsi": "636019532"}):
            with self.subTest(injected=injected):
                with self.assertRaisesRegex(ValueError, "vessel identity differs"):
                    claim_from_source_observation(obs, {
                        "kind": "attack",
                        "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
                        "vessel_name": "CONTSHIP JET",
                        **injected,
                    })

    def test_extraction_cannot_invent_ids_missing_from_official_bulletin(self):
        anonymous = replace(jet(), imo="", mmsi="", vessel_name="UNKNOWN TANKER")
        obs = self.observation(anonymous)
        original = {
            "kind": "attack", "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
            "vessel_name": "UNKNOWN TANKER",
        }
        assert claim_from_source_observation(obs, original) is not None
        for injected in ({"imo": "9348625"}, {"mmsi": "636019532"}):
            with self.subTest(injected=injected):
                with self.assertRaisesRegex(ValueError, "vessel identity differs"):
                    claim_from_source_observation(obs, {**original, **injected})

    def test_older_official_bulletin_without_identity_provenance_fails_closed(self):
        obs = self.observation(synthetic_identified_jet())
        obs.provenance.pop("vessel_imo")
        obs.provenance.pop("vessel_mmsi")
        obs.provenance.pop("vessel_name")
        with self.assertRaisesRegex(ValueError, "vessel identity differs"):
            claim_from_source_observation(obs, {
                "kind": "attack",
                "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
                "imo": "9348625",
            })

    def test_missing_all_dates_rejected_before_database_call(self):
        warning = replace(jet(), occurred_at=None, publication_date=None)
        # The guard must fire before any persistence import or DB access.
        with self.assertRaisesRegex(ValueError, "No reliable"):
            ingest_official_bulletin(object(), warning)


    def test_explicit_ingest_calls_existing_canonical_write_path_once(self):
        fake_db = object()
        # CI's pure-Python job intentionally has no SQLAlchemy installed.
        # Stub the canonical writer module without importing DB dependencies.
        writer = ModuleType("core.intel.source_observation")
        writer.record_observation = MagicMock(return_value="observation")
        with patch.dict("sys.modules", {"core.intel.source_observation": writer}):
            assert ingest_official_bulletin(fake_db, jet()) == "observation"
        writer.record_observation.assert_called_once()
        args, kwargs = writer.record_observation.call_args
        assert args == (fake_db,)
        assert kwargs["source_policy"] == "official_metadata_unverified"
        assert len(kwargs["source_policy"]) <= 32
        assert "raw_payload_ref" not in kwargs
        assert kwargs["provenance"]["origin_authority_verified"] is False
