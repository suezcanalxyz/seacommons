# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline, source-faithful CONTSHIP JET identity linkage regressions."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase

from core.intel.maritime_attack_correlation import claim_from_source_observation
from core.intel.maritime_attack_identity_evidence import (
    ExternalVesselIdentity, link_external_vessel_identity,
)
from core.intel.official_maritime_bulletin import (
    OfficialMaritimeBulletin, prepare_official_bulletin,
)

UTC = timezone.utc


def primary_bulgarian_report():
    # Actual published ministry text names CONTSHIP JET but does NOT print
    # IMO 9348625 or MMSI 636019532. Never fabricate those source fields.
    return OfficialMaritimeBulletin(
        issuer="BG_MOD", bulletin_id="news9664",
        source_url="https://www.mod.bg/news9664", kind="attack",
        vessel_name="CONTSHIP JET", imo="", mmsi="",
        occurred_at=datetime(2026, 10, 28, 10, tzinfo=UTC),
        publication_date=date(2026, 10, 28),
    )


def synthetic_external_registry(**changes):
    # Synthetic fixture only: this URL is NOT asserted to be a real registry.
    record = ExternalVesselIdentity(
        source_record_id="synthetic-registry:jet-20261028",
        source_url="https://example.org/registry/9348625",
        vessel_name="CONTSHIP JET", imo="9348625", mmsi="636019532",
        published_at=datetime(2026, 10, 28, 9, tzinfo=UTC),
        received_at=datetime(2026, 10, 28, 11, tzinfo=UTC),
        reviewed_by="staging-regression-reviewer",
    )
    return replace(record, **changes)


class ExternalIdentityLinkTests(TestCase):
    def test_original_bulgarian_document_contains_name_not_imo_mmsi(self):
        primary = primary_bulgarian_report()
        prepared = prepare_official_bulletin(primary)
        self.assertEqual(prepared["subject_refs"], [])
        self.assertEqual(prepared["provenance"]["vessel_imo"], "")
        self.assertEqual(prepared["provenance"]["vessel_mmsi"], "")
        self.assertEqual(prepared["provenance"]["vessel_name"], "CONTSHIP JET")
        self.assertFalse(prepared["provenance"]["attack_corroboration_allowed"])

        obs = SimpleNamespace(
            observation_type="official_maritime_bulletin",
            observation_id="synthetic:jet-primary",
            source_url=primary.source_url,
            provenance=prepared["provenance"],
            received_at=datetime(2026, 10, 28, 11, tzinfo=UTC),
            lat=None, lon=None, uncertainty_m=None,
        )
        with self.assertRaisesRegex(ValueError, "vessel identity differs"):
            claim_from_source_observation(obs, {
                "kind": "attack", "occurred_at": primary.occurred_at,
                "vessel_name": "CONTSHIP JET", "imo": "9348625",
                "mmsi": "636019532",
            })
        original_claim = claim_from_source_observation(obs, {
            "kind": "attack", "occurred_at": primary.occurred_at,
            "vessel_name": "CONTSHIP JET",
        })
        self.assertEqual(original_claim.vessel.imo, "")
        self.assertEqual(original_claim.vessel.mmsi, "")
        self.assertEqual(original_claim.source_group, "")

    def test_external_identity_link_is_separate_and_never_attack_proof(self):
        primary = primary_bulgarian_report()
        before = prepare_official_bulletin(primary)
        link = link_external_vessel_identity(primary, [synthetic_external_registry()])
        after = prepare_official_bulletin(primary)
        self.assertEqual(before, after)
        self.assertEqual(link.status, "linked_for_review")
        self.assertEqual(link.original_report_id, "BG_MOD:news9664")
        self.assertEqual(link.vessel.imo, "9348625")
        self.assertEqual(link.vessel.mmsi, "636019532")
        self.assertEqual(link.evidence_record_ids, ("synthetic-registry:jet-20261028",))
        self.assertFalse(link.attack_corroboration_allowed)
        self.assertFalse(link.publication_allowed)

    def test_unreviewed_or_same_document_cannot_enrich_identity(self):
        primary = primary_bulgarian_report()
        for record in (
            synthetic_external_registry(reviewed_by=""),
            synthetic_external_registry(source_url=primary.source_url),
            synthetic_external_registry(received_at=None),
            synthetic_external_registry(source_url="https://127.0.0.1/ships"),
        ):
            with self.subTest(record=record):
                self.assertEqual(
                    link_external_vessel_identity(primary, [record]).status,
                    "blocked",
                )

    def test_mismatched_name_or_invalid_ids_are_blocked(self):
        primary = primary_bulgarian_report()
        for record in (
            synthetic_external_registry(vessel_name="RITI"),
            synthetic_external_registry(imo="9348624"),
            synthetic_external_registry(mmsi="123"),
            synthetic_external_registry(imo="", mmsi=""),
        ):
            with self.subTest(record=record):
                self.assertEqual(
                    link_external_vessel_identity(primary, [record]).status,
                    "blocked",
                )

    def test_conflicting_sources_and_duplicate_ids_fail_closed(self):
        primary = primary_bulgarian_report()
        first = synthetic_external_registry()
        conflicting = synthetic_external_registry(
            source_record_id="synthetic-registry:other",
            source_url="https://example.net/registry/other",
            imo="9249075",
        )
        self.assertEqual(
            link_external_vessel_identity(primary, [first, conflicting]).reason,
            "conflicting_external_identifiers",
        )
        self.assertEqual(
            link_external_vessel_identity(primary, [first, first]).reason,
            "invalid_or_duplicate_identity_provenance",
        )

    def test_distinct_record_ids_cannot_reuse_the_same_canonical_registry_url(self):
        primary = primary_bulgarian_report()
        first = synthetic_external_registry()
        alias = synthetic_external_registry(
            source_record_id="synthetic-registry:alias-jet",
            source_url="https://example.org/registry/9348625/?utm_source=mirror#copy",
        )
        result = link_external_vessel_identity(primary, [first, alias])
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "invalid_or_duplicate_identity_provenance")
        self.assertEqual(result.evidence_record_ids, ())
        self.assertFalse(result.attack_corroboration_allowed)
        self.assertFalse(result.publication_allowed)

    def test_distinct_registry_urls_remain_linkable_but_not_attack_proof(self):
        primary = primary_bulgarian_report()
        first = synthetic_external_registry()
        second = synthetic_external_registry(
            source_record_id="synthetic-registry:second-review",
            source_url="https://example.net/ships/9348625",
        )
        result = link_external_vessel_identity(primary, [first, second])
        self.assertEqual(result.status, "linked_for_review")
        self.assertEqual(len(result.evidence_urls), 2)
        self.assertFalse(result.attack_corroboration_allowed)
        self.assertFalse(result.publication_allowed)

    def test_impossible_publication_clock_and_missing_ship_name_fail(self):
        primary = primary_bulgarian_report()
        late = synthetic_external_registry(
            published_at=datetime(2026, 10, 29, 12, tzinfo=UTC),
        )
        self.assertEqual(
            link_external_vessel_identity(primary, [late]).reason,
            "identity_publication_after_receipt",
        )
        self.assertEqual(
            link_external_vessel_identity(
                replace(primary, vessel_name=""), [synthetic_external_registry()]
            ).reason,
            "bulletin_has_no_vessel_name",
        )
