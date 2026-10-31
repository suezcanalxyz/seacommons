# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging regression: do not attach a sinking to a fabricated/irrelevant episode."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from core.intel.maritime_attack_correlation import Correlation, IncidentClaim, VesselRef
from core.intel.maritime_attack_outcomes import ReviewedOutcomeLink
from core.intel.maritime_attack_episode_readonly import (
    reconcile_against_existing_episode, reconcile_against_db_episode,
)
from core.intel.maritime_attack_independence_readonly import IndependenceAudit

JET = VesselRef("9348625", "636019532", "CONTSHIP JET")


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


ATTACK = IncidentClaim(
    "bg_mod_20261028", "attack", at(28, 10),
    "military_observation", "https://example.org/attack", JET,
    43.25, 28.8, 25.0, at(28, 11), at(28, 12), "mod_report",
)
SINKING = IncidentClaim(
    "bg_navwarn_768_20261028", "sinking", at(28, 20, 30),
    "maritime_administration", "https://example.org/sinking", JET,
    43.13, 28.756, 0.5, at(28, 21), at(28, 22), "navwarn_768_26",
)
LINK = ReviewedOutcomeLink(
    "episode:jet:20261028", ATTACK.claim_id, SINKING.claim_id,
    SINKING.claim_id, SINKING.source_url, "reviewer_42", verified=True,
)


def corr(claim):
    return Correlation(
        "corroborated", claim.kind, "maritime_incident_candidate_orange",
        (claim.claim_id,), ("independent_1", "independent_2"),
        ("documentary_evidence",), (),
    )


def episode(**overrides):
    values = dict(
        episode_id=LINK.attack_episode_id,
        episode_family="maritime_attack_episode",
        status="active",
        verification_status="multi_source_corroborated",
        independence_groups=["bg_military_observation", "independent_maritime_observation"],
        evidence_fingerprint="a" * 64,
        observation_ids=[ATTACK.claim_id],
        subject_ids=["imo:9348625", "mmsi:636019532"],
        start_at=datetime(2026, 10, 28, 9, 50),
        end_at=datetime(2026, 10, 28, 10, 10),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def evaluate(row=None, *, link=LINK, use_default=True, independence_verified=True):
    return reconcile_against_existing_episode(
        JET, ATTACK, SINKING, corr(ATTACK), corr(SINKING),
        link, episode() if use_default else row,
        independence_verified=independence_verified,
    )


class CanonicalEpisodeGuardTests(unittest.TestCase):
    def test_contship_jet_documented_sinking_stays_same_episode(self):
        result = evaluate()
        self.assertEqual(result.status, "corroborated_update")
        self.assertEqual(result.attack_episode_id, LINK.attack_episode_id)
        self.assertEqual(result.outcome_key, LINK.attack_episode_id + ":outcome:sinking")
        self.assertFalse(result.publication_allowed)

    def test_missing_provenance_audit_blocks_outcome_even_with_two_labels(self):
        result = evaluate(independence_verified=False)
        self.assertEqual(result.reason_codes, ("canonical_attack_provenance_unverified",))
        self.assertFalse(result.publication_allowed)

    def test_only_literal_true_is_accepted_as_independence_verification(self):
        for value in ("true", 1, None):
            with self.subTest(value=value):
                result = evaluate(independence_verified=value)
                self.assertEqual(result.reason_codes, ("canonical_attack_provenance_unverified",))

    def test_real_navwarn_sinking_time_and_position(self):
        # NAVWARN 768/26: 28 Oct 2026, 20:30 UTC, 43-07.80N 028-45.36E.
        self.assertEqual(SINKING.occurred_at, at(28, 20, 30))
        self.assertEqual((SINKING.lat, SINKING.lon), (43.13, 28.756))
        self.assertEqual((SINKING.occurred_at - ATTACK.occurred_at).total_seconds(), 37800)
        self.assertEqual(evaluate().status, "corroborated_update")

    def test_db_wrapper_requires_real_audit_before_attaching_outcome(self):
        class Model:
            episode_id = "episode_id"

        class Query:
            def filter(self, predicate):
                return self
            def limit(self, count):
                return self
            def one_or_none(self):
                return episode()

        db = SimpleNamespace(query=lambda model: Query())
        fake_models = SimpleNamespace(MaritimeEpisodeDB=Model)
        audit_path = ("core.intel.maritime_attack_independence_readonly."
                      "audit_attack_episode_independence_db")
        args = (JET, ATTACK, SINKING, corr(ATTACK), corr(SINKING), LINK, db)
        with patch.dict(sys.modules, {"core.db.models": fake_models}):
            with patch(audit_path, return_value=IndependenceAudit(False, reason="shared_original_source")) as check:
                blocked = reconcile_against_db_episode(*args)
                self.assertEqual(blocked.reason_codes, (
                    "canonical_attack_provenance_unverified:shared_original_source",
                ))
                self.assertFalse(blocked.publication_allowed)
                check.assert_called_once()
            with patch(audit_path, return_value=IndependenceAudit(True, ("navy", "mrcc"))) as check:
                accepted = reconcile_against_db_episode(*args)
                self.assertEqual(accepted.status, "corroborated_update")
                self.assertFalse(accepted.publication_allowed)
                check.assert_called_once()

    def test_no_canonical_episode_rejects_even_with_verified_link(self):
        result = evaluate(None, use_default=False)
        self.assertEqual(result.reason_codes, ("existing_attack_episode_not_found",))

    def test_episode_id_cannot_be_supplied_without_matching_record(self):
        result = evaluate(episode(episode_id="other"), use_default=False)
        self.assertEqual(result.reason_codes, ("canonical_episode_id_mismatch",))

    def test_generic_ais_gap_cannot_masquerade_as_attack(self):
        result = evaluate(episode(episode_family="gap_episode"), use_default=False)
        self.assertEqual(result.reason_codes, ("canonical_episode_not_attack",))

    def test_superseded_episode_is_not_reused(self):
        result = evaluate(episode(status="superseded"), use_default=False)
        self.assertEqual(result.reason_codes, ("canonical_episode_inactive",))

    def test_single_source_episode_cannot_anchor_sinking_update(self):
        result = evaluate(
            episode(verification_status="single_source_observed"),
            use_default=False,
        )
        self.assertEqual(result.reason_codes, ("canonical_attack_not_corroborated",))
        self.assertFalse(result.publication_allowed)

    def test_contested_episode_cannot_anchor_sinking_update(self):
        result = evaluate(
            episode(verification_status="contested"),
            use_default=False,
        )
        self.assertEqual(result.reason_codes, ("canonical_attack_not_corroborated",))

    def test_missing_or_repeated_independence_groups_fail_closed(self):
        for groups in ([], None, ["same", "same"], ["UKMTO", " ukmto "], ["same", " "], ["same", 7]):
            with self.subTest(groups=groups):
                result = evaluate(
                    episode(independence_groups=groups), use_default=False,
                )
                self.assertEqual(
                    result.reason_codes,
                    ("canonical_attack_independence_incomplete",),
                )

    def test_two_distinct_independence_groups_preserve_valid_jet_outcome(self):
        result = evaluate(
            episode(independence_groups=["navy_observation", "independent_rescue"]),
            use_default=False,
        )
        self.assertEqual(result.status, "corroborated_update")
        self.assertFalse(result.publication_allowed)

    def test_missing_evidence_fingerprint_fails_closed(self):
        result = evaluate(episode(evidence_fingerprint=""), use_default=False)
        self.assertEqual(result.reason_codes, ("canonical_episode_missing_fingerprint",))

    def test_claim_must_be_present_in_canonical_episode(self):
        result = evaluate(episode(observation_ids=["unrelated_claim"]), use_default=False)
        self.assertEqual(result.reason_codes, ("attack_claim_not_in_canonical_episode",))

    def test_subject_must_match_strong_imo_or_mmsi(self):
        for ids in (["name:CONTSHIP JET"], ["imo:1234567"], ["mmsi:123456789"]):
            with self.subTest(ids=ids):
                result = evaluate(episode(subject_ids=ids), use_default=False)
                self.assertEqual(result.reason_codes, ("canonical_episode_vessel_mismatch",))

    def test_conflicting_identifier_vetoes_matching_identifier(self):
        result = evaluate(
            episode(subject_ids=["imo:9348625", "mmsi:123456789"]), use_default=False,
        )
        self.assertEqual(result.reason_codes, ("canonical_episode_vessel_mismatch",))

    def test_one_strong_mmsi_is_sufficient_when_not_contradicted(self):
        result = evaluate(episode(subject_ids=["mmsi:636019532"]), use_default=False)
        self.assertEqual(result.status, "corroborated_update")

    def test_attack_time_must_match_canonical_episode_window(self):
        result = evaluate(
            episode(start_at=datetime(2026, 10, 25, 10),
                    end_at=datetime(2026, 10, 25, 11)),
            use_default=False,
        )
        self.assertEqual(result.reason_codes, ("attack_outside_canonical_episode_window",))

    def test_reversed_or_missing_canonical_times_rejected(self):
        for fields in (
            {"start_at": datetime(2026, 10, 29, 10)},
            {"start_at": None},
        ):
            with self.subTest(fields=fields):
                result = evaluate(episode(**fields), use_default=False)
                self.assertEqual(result.reason_codes, ("canonical_episode_invalid_window",))

    def test_bad_documentary_review_still_fails(self):
        result = evaluate(link=replace(LINK, verified=False))
        self.assertEqual(result.reason_codes, ("missing_verified_documentary_link",))


if __name__ == "__main__":
    unittest.main()
