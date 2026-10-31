# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging regression: an attack's later sinking is an outcome, not a new attack."""
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from core.intel.maritime_attack_correlation import Correlation, IncidentClaim, VesselRef
from core.intel.maritime_attack_outcomes import (
    ReviewedOutcomeLink, reconcile_reported_sinking,
)

JET = VesselRef("9348625", "636019532", "CONTSHIP JET")


def at(day, hour, month=10):
    return datetime(2026, month, day, hour, tzinfo=timezone.utc)


# Synthetic unit-test timestamps and source-independence labels: the fixture
# does not assert that real-world sinking corroboration has been established.
ATTACK = IncidentClaim(
    "bg_mod_20261028", "attack", at(28, 10),
    "bg_mod_military_observation", "https://www.mod.bg/news9664",
    JET, 43.25, 28.8, 25.0, at(28, 11), at(28, 12),
    "bg_mod_news9664",
)
SINKING = IncidentClaim(
    "bg_mtc_20261029_sinking", "sinking", at(29, 10),
    "bg_mtc_maritime_administration", "https://example.org/ship-sank",
    JET, 43.25, 28.8, 25.0, at(29, 11), at(29, 12),
    "bg_mtc_sinking_report",
)


def corr(claim, status="corroborated"):
    return Correlation(
        status, claim.kind, "maritime_incident_candidate_orange",
        (claim.claim_id,), ("source_a", "source_b") if status == "corroborated" else ("source_a",),
        ("incident_claim",), (),
    )


REVIEW = ReviewedOutcomeLink(
    "episode:contship-jet:20261028",
    ATTACK.claim_id, SINKING.claim_id, SINKING.claim_id,
    SINKING.source_url, "operator_42", verified=True,
)


def evaluate(attack=ATTACK, sinking=SINKING, link=REVIEW,
             attack_corr=None, sinking_corr=None):
    return reconcile_reported_sinking(
        JET, attack, sinking,
        attack_corr if attack_corr is not None else corr(attack),
        sinking_corr if sinking_corr is not None else corr(sinking),
        link,
    )


class MaritimeAttackOutcomeTests(unittest.TestCase):
    def test_contship_jet_sinking_is_same_episode_outcome_not_second_attack(self):
        result = evaluate()
        self.assertEqual(result.status, "corroborated_update")
        self.assertEqual(result.attack_episode_id, REVIEW.attack_episode_id)
        self.assertEqual(result.outcome_key, REVIEW.attack_episode_id + ":outcome:sinking")
        self.assertEqual(result.outcome_type, "sinking")
        self.assertEqual(result.color_token, "maritime_sinking_bordeaux")
        self.assertIn("no_second_attack_created", result.reason_codes)
        self.assertFalse(result.publication_allowed)
        self.assertTrue(result.requires_operator_review)

    def test_contship_navwarn_768_26_real_sinking_clock_is_same_episode(self):
        # Primary Bulgarian VTMIS NAVWARN 768/26: 28 Oct 2026, 20:30 UTC,
        # wreck 43-07.80N 028-45.36E. This is a documented OUTCOME, not
        # another attack. Operator review and corroboration are simulated;
        # no production record or real approval is implied by this fixture.
        navwarn = replace(
            SINKING,
            occurred_at=datetime(2026, 10, 28, 20, 30, tzinfo=timezone.utc),
            lat=43 + 7.80 / 60, lon=28 + 45.36 / 60,
            source_group="bulgaria_vtmis_navwarn",
            source_url="https://www.vtmis.bg/wx/wx_eng.htm",
            origin_report_id="NAVWARN-768/26",
            published_at=None, received_at=None,
        )
        reviewed = replace(
            REVIEW, outcome_claim_id=navwarn.claim_id,
            evidence_claim_id=navwarn.claim_id,
            evidence_url=navwarn.source_url,
        )
        result = evaluate(
            sinking=navwarn, link=reviewed,
            sinking_corr=corr(navwarn, "candidate"),
        )
        self.assertEqual(result.status, "candidate_update")
        self.assertEqual(result.attack_episode_id, REVIEW.attack_episode_id)
        self.assertEqual(result.outcome_key, REVIEW.attack_episode_id + ":outcome:sinking")
        self.assertEqual(result.source_evidence[1]["occurred_at"],
                         "2026-10-28T20:30:00+00:00")
        self.assertEqual(result.source_evidence[1]["origin_report_id"], "NAVWARN-768/26")
        self.assertIsNone(result.source_evidence[1]["published_at"])
        self.assertIsNone(result.source_evidence[1]["received_at"])
        self.assertFalse(result.publication_allowed)

    def test_evidence_keeps_both_original_documents_and_three_timestamps(self):
        result = evaluate()
        self.assertEqual(len(result.source_evidence), 2)
        self.assertEqual(result.source_evidence[0]["source_url"], ATTACK.source_url)
        self.assertEqual(result.source_evidence[1]["origin_report_id"], SINKING.origin_report_id)
        self.assertEqual(result.source_evidence[1]["occurred_at"], at(29, 10).isoformat())
        self.assertEqual(result.source_evidence[1]["published_at"], at(29, 11).isoformat())
        self.assertEqual(result.source_evidence[1]["received_at"], at(29, 12).isoformat())

    def test_one_source_sinking_is_candidate_update_not_confirmed(self):
        result = evaluate(sinking_corr=corr(SINKING, "candidate"))
        self.assertEqual(result.status, "candidate_update")
        self.assertEqual(result.color_token, "maritime_incident_candidate_orange")
        self.assertIn("independent_corroboration_incomplete", result.reason_codes)

    def test_one_source_attack_is_not_laundered_by_confirmed_sinking(self):
        result = evaluate(attack_corr=corr(ATTACK, "candidate"))
        self.assertEqual(result.status, "candidate_update")

    def test_no_review_is_rejected(self):
        self.assertEqual(evaluate(link=replace(REVIEW, verified=False)).status, "rejected")
        self.assertEqual(evaluate(link=replace(REVIEW, reviewed_by="")).status, "rejected")

    def test_wrong_review_document_is_rejected(self):
        self.assertEqual(evaluate(link=replace(REVIEW, evidence_claim_id="other")).status, "rejected")
        self.assertEqual(evaluate(link=replace(REVIEW, evidence_url="https://other.org/claim")).status, "rejected")

    def test_wrong_claim_link_is_rejected(self):
        self.assertEqual(evaluate(link=replace(REVIEW, attack_claim_id="unrelated")).status, "rejected")
        self.assertEqual(evaluate(link=replace(REVIEW, outcome_claim_id="unrelated")).status, "rejected")

    def test_strong_identity_required_on_both_documents(self):
        wrong = replace(SINKING, vessel=VesselRef("1234567", "", "CONTSHIP JET"))
        self.assertEqual(evaluate(sinking=wrong, sinking_corr=corr(wrong)).status, "rejected")
        weak = replace(SINKING, vessel=VesselRef(name="CONTSHIP JET"))
        self.assertEqual(evaluate(sinking=weak, sinking_corr=corr(weak)).status, "rejected")

    def test_earlier_sinking_cannot_be_an_outcome(self):
        early = replace(SINKING, occurred_at=at(27, 10),
                        published_at=at(27, 11), received_at=at(27, 12))
        self.assertEqual(evaluate(sinking=early, sinking_corr=corr(early)).status, "rejected")

    def test_late_sinking_needs_separate_episode_review(self):
        late = replace(SINKING, occurred_at=at(15, 10, 11),
                       published_at=at(15, 11, 11), received_at=at(15, 12, 11))
        self.assertEqual(evaluate(sinking=late, sinking_corr=corr(late)).status, "rejected")

    def test_implausible_displacement_rejected_even_with_operator_link(self):
        distant = replace(SINKING, lat=35.0, lon=70.0)
        result = evaluate(sinking=distant, sinking_corr=corr(distant))
        self.assertEqual(result.reason_codes, ("implausible_vessel_displacement",))

    def test_attack_is_not_an_outcome(self):
        other_attack = replace(SINKING, kind="attack")
        result = evaluate(sinking=other_attack, sinking_corr=corr(other_attack))
        self.assertEqual(result.reason_codes, ("not_attack_to_sinking",))

    def test_invalid_timestamp_fails_closed(self):
        naive = replace(SINKING, occurred_at=datetime(2026, 10, 29, 10))
        result = evaluate(sinking=naive, sinking_corr=corr(naive))
        self.assertEqual(result.reason_codes, ("invalid_event_time_or_position",))

    def test_missing_original_provenance_fails_closed(self):
        no_origin = replace(SINKING, origin_report_id=None)
        result = evaluate(sinking=no_origin, sinking_corr=corr(no_origin))
        self.assertEqual(result.reason_codes, ("missing_original_document_provenance",))

    def test_correlation_must_actually_contain_both_claims(self):
        wrong_corr = replace(corr(SINKING), claim_ids=("another_sinking",))
        result = evaluate(sinking_corr=wrong_corr)
        self.assertEqual(result.reason_codes, ("correlation_does_not_include_claim",))

    def test_repeat_review_is_idempotent(self):
        first, second = evaluate(), evaluate()
        self.assertEqual(first.outcome_key, second.outcome_key)
        self.assertEqual(first.source_evidence, second.source_evidence)

    def test_review_does_not_infer_perpetrator_or_use_ais(self):
        result = evaluate()
        self.assertIn("ais_not_causal_evidence", result.reason_codes)
        self.assertNotIn("aggressor", result.__dict__)
        self.assertFalse(result.publication_allowed)


    def test_no_match_correlation_cannot_be_relabelled_candidate_update(self):
        result = evaluate(sinking_corr=corr(SINKING, "no_match"))
        self.assertEqual(result.reason_codes, ("unusable_correlation_status",))

    def test_conflicting_mmsi_between_reports_is_veto_even_if_imo_matches(self):
        imo_only = VesselRef(imo=JET.imo, name=JET.name)
        conflicting = replace(
            SINKING, vessel=VesselRef(imo=JET.imo, mmsi="123456789", name=JET.name)
        )
        result = reconcile_reported_sinking(
            imo_only, ATTACK, conflicting, corr(ATTACK), corr(conflicting), REVIEW,
        )
        self.assertEqual(result.reason_codes, ("strong_vessel_identity_required",))


if __name__ == "__main__":
    unittest.main()
