# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed tests for canonical attack provenance, no database access."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from core.intel.maritime_attack_independence_readonly import (
    audit_attack_episode_independence,
)


def episode(**changes):
    values = dict(
        episode_family="maritime_attack_episode",
        verification_status="multi_source_corroborated",
        independence_groups=["navy", "rescue"],
        observation_ids=["mod", "mrcc"],
    )
    values.update(changes)
    return SimpleNamespace(**values)


def observation(identifier, authority, document, url=None, *, verified=True, service="intel"):
    return SimpleNamespace(
        observation_id=identifier, service=service,
        source_url=url or "https://example.org/" + identifier,
        provenance={
            "origin_authority_verified": verified,
            "originating_authority_id": authority,
            "original_report_id": document,
        },
    )


def edge(child, parent, method="operator_verified", relation="derived_from"):
    return SimpleNamespace(
        from_observation_id=child, to_observation_id=parent,
        relation=relation, method_version=method, confidence=0.99,
    )


def audit(rows, edges=(), ep=None):
    return audit_attack_episode_independence(
        ep or episode(),
        lambda ids: [row for row in rows if row.observation_id in ids],
        lambda ids: [row for row in edges if row.from_observation_id in ids],
    )


class IndependenceAuditTests(unittest.TestCase):
    def test_two_independent_verified_origins(self):
        result = audit([
            observation("mod", "bulgarian_navy", "mod-2026-28"),
            observation("mrcc", "independent_rescue", "rescue-2026-28"),
        ])
        self.assertTrue(result.verified)
        self.assertEqual(len(result.groups), 2)

    def test_authority_separator_aliases_are_not_independent(self):
        result = audit([
            observation("mod", "Bulgarian_Navy", "report-a"),
            observation("mrcc", " bulgarian navy ", "report-b"),
        ])
        self.assertFalse(result.verified)
        self.assertEqual(result.reason, "shared_original_source")

    def test_hyphenated_authority_aliases_are_not_independent(self):
        result = audit([
            observation("mod", "BULGARIAN-NAVY", "report-a"),
            observation("mrcc", "bulgarian_navy", "report-b"),
        ])
        self.assertFalse(result.verified)
        self.assertEqual(result.reason, "shared_original_source")

    def test_canonical_group_separator_aliases_block_before_database_reads(self):
        calls = []
        result = audit_attack_episode_independence(
            episode(independence_groups=["Bulgarian_Navy", "bulgarian navy"]),
            lambda ids: calls.append(ids) or [],
            lambda ids: [],
        )
        self.assertEqual(result.reason, "canonical_verification_incomplete")
        self.assertEqual(calls, [])

    def test_two_labels_do_not_prove_independence(self):
        result = audit([
            observation("mod", "bulgarian_navy", "mod-2026-28"),
            observation("mrcc", "bulgarian_navy", "other-document"),
        ])
        self.assertFalse(result.verified)
        self.assertEqual(result.reason, "shared_original_source")

    def test_syndicated_articles_share_one_root(self):
        ep = episode(observation_ids=["news_a", "news_b"])
        rows = [
            observation("news_a", "publisher_a", "a"),
            observation("news_b", "publisher_b", "b"),
        ]
        edges = [edge("news_a", "wire_a"), edge("wire_a", "original"),
                 edge("news_b", "wire_b"), edge("wire_b", "original")]
        self.assertEqual(audit(rows, edges, ep).reason, "shared_original_source")

    def test_unverified_origin_fails_closed(self):
        rows = [
            observation("mod", "mod", "1", verified=False),
            observation("mrcc", "mrcc", "2"),
        ]
        self.assertEqual(audit(rows).reason, "origin_not_verified")

    def test_missing_observation_fails_closed(self):
        self.assertEqual(audit([observation("mod", "mod", "1")]).reason,
                         "missing_or_duplicate_observations")

    def test_humanitarian_is_not_relabelled_attack(self):
        rows = [observation("mod", "mod", "1", service="humanitarian"),
                observation("mrcc", "mrcc", "2")]
        self.assertEqual(audit(rows).reason, "humanitarian_domain_excluded")

    def test_cycle_blocks_even_distinct_authorities(self):
        rows = [observation("mod", "mod", "1"), observation("mrcc", "mrcc", "2")]
        self.assertEqual(audit(rows, [edge("mod", "x"), edge("x", "mod")]).reason,
                         "lineage_cycle_detected")

    def test_unverified_quotation_blocks(self):
        rows = [observation("mod", "mod", "1"), observation("mrcc", "mrcc", "2")]
        self.assertEqual(audit(rows, [edge("mrcc", "mod", relation="quotes")]).reason,
                         "unverified_lineage_edge")

    def test_tracking_aliases_not_two_sources(self):
        rows = [observation("mod", "mod", "1", "https://a.test/report?id=42&utm_source=a"),
                observation("mrcc", "mrcc", "2", "https://a.test/report?id=42&utm_source=b#section")]
        self.assertEqual(audit(rows).reason, "shared_original_source")

    def test_distinct_query_identified_reports_not_falsely_merged(self):
        rows = [observation("mod", "mod", "1", "https://a.test/report?id=41"),
                observation("mrcc", "mrcc", "2", "https://a.test/report?id=42")]
        result = audit(rows)
        self.assertTrue(result.verified)
        self.assertEqual(len(result.groups), 2)

    def test_same_original_report_id_still_collapses_distinct_urls(self):
        rows = [observation("mod", "mod", "original-42", "https://a.test/report?id=41"),
                observation("mrcc", "mrcc", "original-42", "https://b.test/report?id=42")]
        self.assertEqual(audit(rows).reason, "shared_original_source")

    def test_malformed_url_never_counts_as_verified_origin(self):
        rows = [observation("mod", "mod", "1", "http://a.test/report?id=41"),
                observation("mrcc", "mrcc", "2", "https://b.test/report?id=42")]
        self.assertEqual(audit(rows).reason, "missing_original_provenance")

    def test_observation_future_of_receipt_is_not_corroboration(self):
        a = observation("mod", "navy", "one")
        b = observation("mrcc", "rescue", "two")
        a.observed_at = "2026-10-28T11:00:00Z"
        a.received_at = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)
        self.assertEqual(audit([a, b]).reason, "observation_after_receipt")

    def test_publication_future_of_receipt_is_not_corroboration(self):
        a = observation("mod", "navy", "one")
        b = observation("mrcc", "rescue", "two")
        a.observed_at = "2026-10-28T10:00:00Z"
        a.received_at = datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc)
        a.provenance["published_at_utc"] = "2026-10-28T12:00:00Z"
        self.assertEqual(audit([a, b]).reason, "publication_after_receipt")

    def test_minor_clock_skew_does_not_invalidate_independent_reports(self):
        a = observation("mod", "navy", "one")
        b = observation("mrcc", "rescue", "two")
        a.observed_at = "2026-10-28T11:04:00Z"
        a.received_at = datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc)
        a.provenance["published_at"] = "2026-10-28T11:03:00Z"
        self.assertTrue(audit([a, b]).verified)

    def test_malformed_publication_time_blocks(self):
        a = observation("mod", "navy", "one")
        b = observation("mrcc", "rescue", "two")
        a.observed_at = "2026-10-28T10:00:00Z"
        a.received_at = datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc)
        a.provenance["published_at"] = "not-a-timestamp"
        self.assertEqual(audit([a, b]).reason, "invalid_publication_timestamp")

    def test_strict_canonical_audit_rejects_both_missing_timestamps(self):
        rows = [
            observation("mod", "navy", "one"),
            observation("mrcc", "rescue", "two"),
        ]
        result = audit_attack_episode_independence(
            episode(),
            lambda ids: rows,
            lambda ids: [],
            require_chronology=True,
        )
        self.assertFalse(result.verified)
        self.assertEqual(result.reason, "missing_observation_chronology")

    def test_strict_canonical_audit_accepts_valid_timestamps(self):
        rows = [
            observation("mod", "navy", "one"),
            observation("mrcc", "rescue", "two"),
        ]
        for row in rows:
            row.observed_at = "2026-10-28T10:00:00Z"
            row.received_at = datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc)
        result = audit_attack_episode_independence(
            episode(),
            lambda ids: rows,
            lambda ids: [],
            require_chronology=True,
        )
        self.assertTrue(result.verified)

    def test_missing_half_of_observation_timeline_blocks(self):
        a = observation("mod", "navy", "one")
        b = observation("mrcc", "rescue", "two")
        a.observed_at = "2026-10-28T10:00:00Z"
        self.assertEqual(audit([a, b]).reason, "invalid_observation_chronology")

    def test_naive_postgres_receipt_assumed_utc(self):
        a = observation("mod", "navy", "one")
        b = observation("mrcc", "rescue", "two")
        a.observed_at = "2026-10-28T10:00:00+00:00"
        a.received_at = datetime(2026, 10, 28, 11, 0)
        self.assertTrue(audit([a, b]).verified)

    def test_offset_publication_later_than_utc_receipt_blocks(self):
        a = observation("mod", "navy", "one")
        b = observation("mrcc", "rescue", "two")
        a.observed_at = "2026-10-28T10:00:00Z"
        a.received_at = datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc)
        # 14:30 +03:00 is 11:30 UTC, later than the 11:00 UTC receipt.
        a.provenance["published_at"] = "2026-10-28T14:30:00+03:00"
        self.assertEqual(audit([a, b]).reason, "publication_after_receipt")

    def test_string_verified_flag_cannot_establish_independence(self):
        a = observation("mod", "navy", "one", verified="true")
        b = observation("mrcc", "rescue", "two")
        self.assertEqual(audit([a, b]).reason, "origin_not_verified")

    def test_malformed_episode_labels_block_without_fetch(self):
        calls = []
        result = audit_attack_episode_independence(
            episode(independence_groups=["mod", " mod "]),
            lambda ids: calls.append(ids) or [],
            lambda ids: [],
        )
        self.assertFalse(result.verified)
        self.assertEqual(calls, [])

    def test_non_attack_episode_never_passes(self):
        self.assertEqual(audit([], ep=episode(episode_family="gap_episode")).reason,
                         "not_attack_episode")

    def test_duplicated_observation_ids_block_without_fetch(self):
        result = audit([], ep=episode(observation_ids=["mod", "mod"]))
        self.assertEqual(result.reason, "duplicate_observation_ids")


    def test_conflicting_publication_aliases_cannot_corrobate(self):
        a = observation("mod", "navy", "one")
        b = observation("mrcc", "rescue", "two")
        a.observed_at = "2026-10-28T10:00:00Z"
        a.received_at = "2026-10-28T13:00:00Z"
        a.provenance["published_at_utc"] = "2026-10-28T11:00:00Z"
        a.provenance["published_at"] = "2026-10-28T12:00:00Z"
        self.assertEqual(audit([a, b]).reason, "conflicting_publication_timestamps")

    def test_equivalent_publication_aliases_with_offsets_pass(self):
        a = observation("mod", "navy", "one")
        b = observation("mrcc", "rescue", "two")
        a.observed_at = "2026-10-28T10:00:00Z"
        a.received_at = "2026-10-28T13:00:00Z"
        a.provenance["published_at_utc"] = "2026-10-28T11:00:00Z"
        a.provenance["published_at"] = "2026-10-28T14:00:00+03:00"
        self.assertTrue(audit([a, b]).verified)

    def test_date_only_observed_at_is_not_precise_evidence(self):
        a = observation("mod", "navy", "one")
        b = observation("mrcc", "rescue", "two")
        a.observed_at = "2026-10-28"
        a.received_at = "2026-10-28T13:00:00Z"
        self.assertEqual(audit([a, b]).reason, "invalid_observation_chronology")

    def test_date_only_secondary_publication_alias_is_not_ignored(self):
        a = observation("mod", "navy", "one")
        b = observation("mrcc", "rescue", "two")
        a.observed_at = "2026-10-28T10:00:00Z"
        a.received_at = "2026-10-28T13:00:00Z"
        a.provenance["published_at_utc"] = "2026-10-28T11:00:00Z"
        a.provenance["published_at"] = "2026-10-28"
        self.assertEqual(audit([a, b]).reason, "invalid_publication_timestamp")


if __name__ == "__main__":
    unittest.main()
