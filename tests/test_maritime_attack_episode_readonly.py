# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staging regression: do not attach a sinking to a fabricated/irrelevant episode."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from core.intel.maritime_attack_correlation import Correlation, IncidentClaim, VesselRef
from core.intel.maritime_attack_outcomes import ReviewedOutcomeLink
from core.intel.maritime_attack_episode_readonly import reconcile_against_existing_episode

JET = VesselRef("9348625", "636019532", "CONTSHIP JET")


def at(day, hour):
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


ATTACK = IncidentClaim(
    "bg_mod_20261028", "attack", at(28, 10),
    "military_observation", "https://example.org/attack", JET,
    43.25, 28.8, 25.0, at(28, 11), at(28, 12), "mod_report",
)
SINKING = IncidentClaim(
    "bg_sinking_20261029", "sinking", at(29, 10),
    "maritime_administration", "https://example.org/sinking", JET,
    43.25, 28.8, 25.0, at(29, 11), at(29, 12), "sinking_report",
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
        evidence_fingerprint="a" * 64,
        observation_ids=[ATTACK.claim_id],
        subject_ids=["imo:9348625", "mmsi:636019532"],
        start_at=datetime(2026, 10, 28, 9, 50),
        end_at=datetime(2026, 10, 28, 10, 10),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def evaluate(row=None, *, link=LINK, use_default=True):
    return reconcile_against_existing_episode(
        JET, ATTACK, SINKING, corr(ATTACK), corr(SINKING),
        link, episode() if use_default else row,
    )


class CanonicalEpisodeGuardTests(unittest.TestCase):
    def test_contship_jet_documented_sinking_stays_same_episode(self):
        result = evaluate()
        self.assertEqual(result.status, "corroborated_update")
        self.assertEqual(result.attack_episode_id, LINK.attack_episode_id)
        self.assertEqual(result.outcome_key, LINK.attack_episode_id + ":outcome:sinking")
        self.assertFalse(result.publication_allowed)

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
