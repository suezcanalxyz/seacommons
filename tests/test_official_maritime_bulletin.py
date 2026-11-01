# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline staging contracts for original maritime-bulletin ingestion."""
from dataclasses import replace
from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch
from types import ModuleType

from core.intel.official_maritime_bulletin import (
    OfficialMaritimeBulletin, ingest_official_bulletin, prepare_official_bulletin,
)

UTC = timezone.utc


def jet():
    return OfficialMaritimeBulletin(
        issuer="BG_MOD", bulletin_id="news9664",
        source_url="https://www.mod.bg/news9664", kind="attack",
        vessel_name="CONTSHIP JET", imo="9348625", mmsi="636019532",
        occurred_at=datetime(2026, 10, 28, 10, tzinfo=UTC),
        publication_date=date(2026, 10, 28),
    )


class OfficialBulletinTests(TestCase):
    def test_contship_jet_primary_document_is_canonical_but_not_auto_verified(self):
        result = prepare_official_bulletin(jet())
        assert result["source_name"] == "Bulgarian Ministry of Defence"
        assert result["subject_refs"] == ["imo:9348625", "mmsi:636019532"]
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


    def test_mscio_relay_cannot_manufacture_an_independent_authority(self):
        warning = OfficialMaritimeBulletin(
            issuer="MSCIO", bulletin_id="159/26",
            source_url="https://mscio.eu/alerts/195", kind="attack",
            event_date=date(2026, 10, 29),
            publication_date=date(2026, 10, 29),
        )
        result = prepare_official_bulletin(warning)
        assert result["observed_at"] == "2026-10-29"
        assert result["provenance"]["event_time_precision"] == "day"
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
        )
        result = prepare_official_bulletin(warning)
        assert result["observed_at"] == "2026-10-30"
        assert result["provenance"]["observed_at_semantics"] == "publication"
        assert result["uncertainty_m"] == 10000
        assert result["provenance"]["event_time_precision"] == "unknown"


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
        assert kwargs["source_policy"] == "official_bulletin_metadata_only_reuse_unverified"
        assert "raw_payload_ref" not in kwargs
        assert kwargs["provenance"]["origin_authority_verified"] is False
