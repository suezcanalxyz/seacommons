# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline regression: a manager's relay is not an independent Master witness."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase

from core.intel.maritime_attack_correlation import (
    AISFix, IncidentClaim, VesselRef, claim_from_source_observation, correlate,
)
from core.intel.maritime_attack_operator_statement import (
    OperatorIncidentStatement, prepare_operator_statement,
)

UTC = timezone.utc
JET = VesselRef("9348625", "636019532", "CONTSHIP JET")
OPERATOR_URL = (
    "https://contships-management.com/2026/10/29/"
    "contships-management-inc-company-update/"
)


def manager_statement(**changes):
    # Document: published 29 Oct, datelined 28 Oct, no exact clock or MMSI.
    return replace(OperatorIncidentStatement(
        report_id="company-update-2026-10-29",
        source_url=OPERATOR_URL,
        vessel_name="CONTSHIP JET",
        imo="9348625",
        event_date=date(2026, 10, 28),
        publication_date=date(2026, 10, 29),
        reported_witness_role="master",
    ), **changes)


def operator_observation(envelope, **changes):
    return SimpleNamespace(
        observation_type=envelope["observation_type"],
        observation_id=envelope["source_id"],
        source_url=envelope["source_url"],
        provenance=envelope["provenance"],
        received_at=datetime(2026, 11, 1, 16, 30, tzinfo=UTC),
        lat=None, lon=None, uncertainty_m=None,
        **changes,
    )


class OperatorWitnessRelayTests(TestCase):
    def test_real_document_dates_and_identity_are_source_faithful(self):
        envelope = prepare_operator_statement(manager_statement())
        self.assertEqual(envelope["observed_at"], "2026-10-29")
        self.assertEqual(envelope["provenance"]["event_date"], "2026-10-28")
        self.assertIsNone(envelope["provenance"]["occurred_at_utc"])
        self.assertIsNone(envelope["provenance"]["published_at_utc"])
        self.assertIsNone(envelope["provenance"]["received_at_utc"])
        self.assertEqual(envelope["subject_refs"], ["imo:9348625"])
        self.assertEqual(envelope["provenance"]["vessel_mmsi"], "")
        self.assertFalse(envelope["provenance"]["origin_authority_verified"])
        self.assertFalse(envelope["provenance"]["original_witness_artifact_verified"])
        self.assertFalse(envelope["provenance"]["reported_witness_is_independent"])
        self.assertFalse(envelope["provenance"]["attack_corroboration_allowed"])
        self.assertFalse(envelope["provenance"]["reuse_rights_verified"])
        self.assertEqual(envelope["source_id"], prepare_operator_statement(manager_statement())["source_id"])

    def test_operator_origin_is_restricted(self):
        for url in (
            "http://contships-management.com/2026/10/29/x",
            "https://example.org/2026/10/29/x",
            "https://contships-management.com.evil.org/2026/10/29/x",
            "https://user:pass@contships-management.com/2026/10/29/x",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                prepare_operator_statement(manager_statement(source_url=url))

    def test_invalid_identity_and_reverse_chronology_fail_closed(self):
        for change in (
            {"imo": "9348624"}, {"mmsi": "123"},
            {"vessel_name": ""}, {"publication_date": date(2026, 10, 27)},
            {"received_at": datetime(2026, 10, 29, 12)},
            {"received_at": datetime(2026, 10, 28, 12, tzinfo=UTC)},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepare_operator_statement(manager_statement(**change))

    def test_received_at_is_preserved_only_if_actually_supplied(self):
        receipt = datetime(2026, 11, 1, 17, 30, tzinfo=timezone(timedelta(hours=1)))
        envelope = prepare_operator_statement(manager_statement(received_at=receipt))
        self.assertEqual(envelope["provenance"]["received_at_utc"], "2026-11-01T16:30:00+00:00")
        self.assertEqual(envelope["observed_at"], "2026-10-29")

    def test_extraction_cannot_forge_exact_time_or_mmsi(self):
        envelope = prepare_operator_statement(manager_statement())
        observation = operator_observation(envelope)
        extraction = {
            "kind": "attack", "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
            "vessel_name": "CONTSHIP JET", "imo": "9348625",
            "time_uncertainty_minutes": 0,
            "lat": 43.26, "lon": 28.81, "uncertainty_km": 0,
        }
        claim = claim_from_source_observation(observation, extraction)
        self.assertIsNotNone(claim)
        self.assertEqual(claim.time_uncertainty_minutes, 1440)
        self.assertIsNone(claim.lat)
        self.assertIsNone(claim.lon)
        self.assertEqual(claim.source_group, "")
        self.assertIsNone(claim.origin_report_id)
        self.assertIsNone(claim.published_at)
        for update in (
            {"occurred_at": datetime(2026, 10, 29, 10, tzinfo=UTC)},
            {"mmsi": "636019532"},
            {"imo": "9249075"},
            {"vessel_name": "RITI"},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                claim_from_source_observation(observation, {**extraction, **update})

    def test_operator_relay_cannot_become_independent_via_provenance_flag(self):
        envelope = prepare_operator_statement(manager_statement())
        envelope["provenance"]["origin_authority_verified"] = True
        observation = operator_observation(envelope)
        claim = claim_from_source_observation(observation, {
            "kind": "attack",
            "occurred_at": datetime(2026, 10, 28, 10, tzinfo=UTC),
            "vessel_name": "CONTSHIP JET", "imo": "9348625",
        })
        self.assertEqual(claim.source_group, "")
        self.assertIsNone(claim.origin_report_id)
        military = IncidentClaim(
            "bg_mod_news9664", "attack",
            datetime(2026, 10, 28, 10, tzinfo=UTC),
            "bg_mod", "https://www.mod.bg/news9664",
            VesselRef(name="CONTSHIP JET"),
            published_at=datetime(2026, 10, 28, 13, tzinfo=UTC),
            received_at=datetime(2026, 10, 28, 14, tzinfo=UTC),
            origin_report_id="BG_MOD:news9664",
        )
        result = correlate(JET, [military, claim], [
            AISFix(JET.mmsi, datetime(2026, 10, 28, 9, 59, tzinfo=UTC), 43.26, 28.81),
        ])
        self.assertEqual(result.status, "candidate")
        self.assertEqual(result.independent_groups, ("bg_mod",))
        self.assertFalse(result.publication_allowed)
