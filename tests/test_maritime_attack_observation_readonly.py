# SPDX-License-Identifier: AGPL-3.0-or-later
"""No-database staging tests for bounded reviewed observation correlation."""
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from core.intel.maritime_attack_correlation import VesselRef
from core.intel.maritime_attack_observation_readonly import correlate_reviewed_observations

JET = VesselRef("9348625", "636019532", "CONTSHIP JET")
OCCURRED = "2026-10-28T10:00:00+00:00"


def observation(identifier, authority, *, service="intel", verified=True):
    return SimpleNamespace(
        observation_id=identifier, service=service,
        source_url="https://example.org/" + identifier,
        received_at=datetime(2026, 10, 28, 11, tzinfo=timezone.utc),
        provenance={
            "origin_authority_verified": verified,
            "originating_authority_id": authority,
            "original_report_id": authority + ":" + identifier,
            "published_at": "2026-10-28T10:30:00+00:00",
        },
    )


def extraction(*, reviewed=True, reviewed_by="analyst", kind="attack", imo="9348625"):
    return {
        "reviewed": reviewed, "reviewed_by": reviewed_by,
        "kind": kind, "occurred_at": OCCURRED, "imo": imo,
        "mmsi": "636019532", "vessel_name": "CONTSHIP JET",
    }


def evaluate(ids, rows, extracts, lineage=(), calls=None):
    def fetch_observations(requested):
        if calls is not None:
            calls.append(("observations", requested))
        return rows

    def fetch_lineage(frontier):
        if calls is not None:
            calls.append(("lineage", frontier))
        return [edge for edge in lineage if edge.from_observation_id in frontier]

    return correlate_reviewed_observations(
        JET, ids, extracts, fetch_observations, fetch_lineage,
    )


class ReviewedObservationReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.rows = [observation("mod", "mod"), observation("mrcc", "mrcc")]
        self.extractions = {"mod": extraction(), "mrcc": extraction()}

    def test_two_reviewed_origins_can_corroborate_but_never_publish(self):
        result = evaluate(["mod", "mrcc"], self.rows, self.extractions)
        self.assertEqual(result.correlation.status, "corroborated")
        self.assertFalse(result.correlation.publication_allowed)
        self.assertTrue(result.correlation.requires_operator_review)
        self.assertEqual(result.loaded_count, 2)

    def test_missing_observation_blocks_without_partial_promotion(self):
        result = evaluate(["mod", "mrcc"], self.rows[:1], self.extractions)
        self.assertIsNone(result.correlation)
        self.assertEqual(result.blocked_reasons, ("missing_observations",))

    def test_duplicate_or_unrequested_rows_block(self):
        duplicate = evaluate(["mod", "mrcc"], [self.rows[0], self.rows[0]], self.extractions)
        self.assertEqual(duplicate.blocked_reasons, ("unexpected_or_duplicate_row",))
        foreign = evaluate(["mod"], [self.rows[0], observation("alien", "alien")],
                           {"mod": extraction()})
        self.assertEqual(foreign.blocked_reasons, ("unexpected_or_duplicate_row",))

    def test_unreviewed_extraction_never_queries(self):
        calls = []
        extracts = dict(self.extractions)
        extracts["mrcc"] = extraction(reviewed=False)
        result = evaluate(["mod", "mrcc"], self.rows, extracts, calls=calls)
        self.assertEqual(result.blocked_reasons, ("unreviewed_extraction",))
        self.assertEqual(calls, [])

    def test_unattributed_source_cannot_be_independent(self):
        rows = [self.rows[0], observation("mrcc", "mrcc", verified=False)]
        result = evaluate(["mod", "mrcc"], rows, self.extractions)
        self.assertEqual(result.correlation.status, "candidate")

    def test_humanitarian_drift_is_excluded(self):
        rows = [self.rows[0], observation("mrcc", "mrcc", service="humanitarian")]
        result = evaluate(["mod", "mrcc"], rows, self.extractions)
        self.assertIsNone(result.correlation)
        self.assertEqual(result.blocked_reasons, ("humanitarian_domain_excluded",))

    def test_padded_humanitarian_service_blocks_reviewed_attack(self):
        rows = [self.rows[0], observation("mrcc", "mrcc", service=" HUMANITARIAN  ")]
        result = evaluate(["mod", "mrcc"], rows, self.extractions)
        self.assertIsNone(result.correlation)
        self.assertEqual(result.blocked_reasons, ("humanitarian_domain_excluded",))

    def test_malformed_imo_blocks_entire_batch(self):
        extracts = dict(self.extractions)
        extracts["mrcc"] = extraction(imo="1234560")
        result = evaluate(["mod", "mrcc"], self.rows, extracts)
        self.assertIsNone(result.correlation)
        self.assertEqual(result.blocked_reasons, ("invalid_extraction:mrcc",))

    def test_lineage_merges_syndicated_sources(self):
        edge = SimpleNamespace(
            from_observation_id="mrcc", to_observation_id="mod",
            relation="derived_from", confidence=0.99,
            method_version="operator_verified",
        )
        result = evaluate(["mod", "mrcc"], self.rows, self.extractions, lineage=[edge])
        self.assertEqual(result.correlation.status, "candidate")
        self.assertEqual(len(result.correlation.independent_groups), 1)

    def test_bounded_or_duplicate_input_never_queries(self):
        calls = []
        result = evaluate(["mod"] * 33, self.rows, self.extractions, calls=calls)
        self.assertEqual(result.blocked_reasons, ("invalid_batch_size",))
        result = evaluate(["mod", "mod"], self.rows, self.extractions, calls=calls)
        self.assertEqual(result.blocked_reasons, ("invalid_observation_ids",))
        self.assertEqual(calls, [])

    def test_unknown_kind_is_not_relabelled_attack(self):
        extracts = dict(self.extractions)
        extracts["mrcc"] = extraction(kind="distress")
        result = evaluate(["mod", "mrcc"], self.rows, extracts)
        self.assertIsNone(result.correlation)
        self.assertEqual(result.blocked_reasons, ("not_an_incident_claim:mrcc",))


if __name__ == "__main__":
    unittest.main()
