# SPDX-License-Identifier: AGPL-3.0-or-later
from unittest import TestCase

from core.intel.maritime_attack_staging_routing import route_staging_incident


def candidate(**patch):
    return {
        "staging_only": True, "publication_allowed": False,
        "proposed_incident_type": "maritime_attack",
        "review_blockers": [], "canonical_observation_id": "obs:jet",
        "occurred_at_utc": "2026-10-28T10:00:00Z",
        "reported_location": {"role": "incident_site", "lat": 43.0, "lon": 28.0},
        **patch,
    }


class RoutingTests(TestCase):
    def route(self, p, **kw):
        return route_staging_incident(p, now_utc="2026-11-03T12:00:00Z", **kw)

    def test_contship_jet_historical_to_play(self):
        result = self.route(candidate(), reviewed=True, corroborated=True)
        self.assertEqual(result["destination"], "PLAY")
        self.assertFalse(result["publication_allowed"])

    def test_recent_attack_to_live(self):
        result = self.route(candidate(occurred_at_utc="2026-11-03T11:00:00Z"), reviewed=True, corroborated=True)
        self.assertEqual(result["destination"], "LIVE")

    def test_old_incident_active_update_to_live(self):
        result = self.route(candidate(), reviewed=True, corroborated=True, active_update_at_utc="2026-11-03T11:00:00Z")
        self.assertEqual(result["destination"], "LIVE")

    def test_unverified_candidate_never_published(self):
        self.assertEqual(self.route(candidate())["destination"], "review_queue")
        self.assertEqual(self.route(candidate(), reviewed=True)["destination"], "review_queue")

    def test_blockers_keep_contship_jet_out_of_play(self):
        self.assertEqual(self.route(candidate(review_blockers=["incident_location_unverified"]), reviewed=True, corroborated=True)["destination"], "review_queue")

    def test_unknown_position_is_not_a_map_pin(self):
        self.assertEqual(self.route(candidate(reported_location=None), reviewed=True, corroborated=True)["destination"], "review_queue")

    def test_humanitarian_case_is_not_an_attack(self):
        self.assertEqual(self.route(candidate(proposed_incident_type=None), reviewed=True, corroborated=True)["destination"], "review_queue")

    def test_future_attack_rejected(self):
        with self.assertRaisesRegex(ValueError, "future_event"):
            self.route(candidate(occurred_at_utc="2026-11-04T00:00:00Z"), reviewed=True, corroborated=True)

    def test_invalid_active_update_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid_active_update"):
            self.route(candidate(), reviewed=True, corroborated=True, active_update_at_utc="2026-10-27T00:00:00Z")

    def test_untrusted_published_preview_rejected(self):
        with self.assertRaisesRegex(ValueError, "untrusted_preview"):
            self.route(candidate(publication_allowed=True), reviewed=True, corroborated=True)
