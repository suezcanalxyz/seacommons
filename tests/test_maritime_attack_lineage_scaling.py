# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deep source-lineage regressions: pure, staging-only, no network or DB.

All authorities and documents in these fixtures are synthetic. AIS gaps and
publication counts are never used as independent proof of an attack.
"""
from datetime import datetime, timezone
from unittest import TestCase

from core.intel.maritime_attack_correlation import (
    IncidentClaim, VesselRef, _lineage_components, correlate,
)

UTC = timezone.utc
SHIP = VesselRef("9348625", "636019532", "CONTSHIP JET")


def synthetic_claim(claim_id: str, group: str) -> IncidentClaim:
    return IncidentClaim(
        claim_id=claim_id,
        kind="attack",
        occurred_at=datetime(2026, 10, 28, 10, tzinfo=UTC),
        source_group=group,
        source_url="https://example.org/synthetic/" + claim_id,
        vessel=SHIP,
        published_at=datetime(2026, 10, 28, 11, tzinfo=UTC),
        received_at=datetime(2026, 10, 28, 12, tzinfo=UTC),
        origin_report_id="synthetic:" + claim_id,
    )


class DeepDocumentLineageTests(TestCase):
    @staticmethod
    def deep_chain(length: int = 1601) -> list[tuple[str, str]]:
        # Descending edges deliberately build a long parent chain when
        # union picks the lexicographically smallest canonical root.
        return [
            (f"{index:04d}", f"{index - 1:04d}")
            for index in range(length, 0, -1)
        ]

    def test_deep_chain_iterative_collapse(self):
        roots = _lineage_components(self.deep_chain())
        self.assertEqual(roots["1601"], roots["0000"])
        self.assertEqual(len(roots), 1602)

    def test_deep_chain_cannot_manufacture_two_attack_witnesses(self):
        claims = [
            synthetic_claim("1601", "synthetic_owner"),
            synthetic_claim("0000", "synthetic_republisher"),
        ]
        result = correlate(SHIP, claims, lineage_edges=self.deep_chain())
        self.assertEqual(result.status, "candidate")
        self.assertEqual(len(result.independent_groups), 1)
        self.assertFalse(result.publication_allowed)

    def test_third_unconnected_original_remains_independent(self):
        claims = [
            synthetic_claim("1601", "synthetic_owner"),
            synthetic_claim("0000", "synthetic_republisher"),
            synthetic_claim("third", "synthetic_third"),
        ]
        result = correlate(SHIP, claims, lineage_edges=self.deep_chain())
        self.assertEqual(result.status, "corroborated")
        self.assertEqual(len(result.independent_groups), 2)
        self.assertFalse(result.publication_allowed)
