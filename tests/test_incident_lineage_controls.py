"""Synthetic, fail-closed incident lineage controls for #440.

This is an isolated benchmark prototype, NOT a production incident classifier.
Run: python -m unittest discover -s tests -p 'test_incident_lineage_controls.py'
No network, DB, private locations, or external fixtures.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import unittest


@dataclass(frozen=True)
class Report:
    source: str
    origin: str | None
    event_id: str | None = None
    domain: str = "maritime_security"
    vessel: str | None = None
    event_time: datetime | None = None
    published_at: datetime | None = None
    ingested_at: datetime | None = None
    kind: str = "reported_event"
    has_sensitive_geometry: bool = False


def evaluate(reports: list[Report]) -> dict:
    """Conservative synthetic origin assessment; missing lineage never counts."""
    allowed = [r for r in reports if r.domain == "maritime_security"
               and not r.has_sensitive_geometry]
    event_ids = {r.event_id for r in allowed if r.kind == "reported_event"}
    same_event = (len(event_ids) == 1 and all(
        r.event_id is not None for r in allowed if r.kind == "reported_event"
    ))
    origins = {r.origin for r in allowed
               if r.origin and r.kind == "reported_event"}
    vessels = {r.vessel for r in allowed if r.vessel}
    conflicting = len(vessels) > 1
    def valid_time(value):
        return value is None or (isinstance(value, datetime)
                                 and value.tzinfo is not None
                                 and value.utcoffset() is not None)

    timestamps_valid = all(
        all(valid_time(t) for t in (r.event_time, r.published_at, r.ingested_at))
        and (r.event_time is None or r.published_at is None
             or r.event_time <= r.published_at)
        and (r.published_at is None or r.ingested_at is None
             or r.published_at <= r.ingested_at)
        and (r.event_time is None or r.ingested_at is None
             or r.event_time <= r.ingested_at)
        for r in allowed
    )
    return {
        "independent_origins": len(origins),
        "identity_conflict": conflicting,
        "same_event": same_event,
        "chronology_valid": timestamps_valid,
        "eligible_for_human_review": same_event and len(origins) >= 2 and not conflicting
            and timestamps_valid,
        "automatic_attack_attribution": False,
        "excluded_sensitive": len(reports) - len(allowed),
    }


class IncidentLineageControls(unittest.TestCase):
    def test_syndication_counts_one_origin(self):
        reports = [Report("primary", "wire-A"), Report("news", "wire-A"),
                   Report("aggregator", "wire-A")]
        self.assertEqual(evaluate(reports)["independent_origins"], 1)
        self.assertFalse(evaluate(reports)["eligible_for_human_review"])

    def test_independent_origins_only_eligible_for_review(self):
        result = evaluate([Report("primary-A", "A", event_id="case-1"), Report("primary-D", "D", event_id="case-1")])
        self.assertEqual(result["independent_origins"], 2)
        self.assertTrue(result["eligible_for_human_review"])
        self.assertFalse(result["automatic_attack_attribution"])

    def test_conflicting_vessel_identity_abstains(self):
        result = evaluate([Report("A", "A", event_id="case-1", vessel="vessel-1"),
                           Report("D", "D", event_id="case-1", vessel="vessel-2")])
        self.assertTrue(result["identity_conflict"])
        self.assertFalse(result["eligible_for_human_review"])

    def test_ais_gap_and_unverified_post_are_not_attacks(self):
        result = evaluate([Report("AIS", None, kind="ais_gap"),
                           Report("social", None, kind="unverified_post")])
        self.assertEqual(result["independent_origins"], 0)
        self.assertFalse(result["automatic_attack_attribution"])

    def test_event_publication_ingest_times_are_distinct(self):
        t = lambda day: datetime(2026, 11, day, tzinfo=timezone.utc)
        report = Report("A", "A", event_time=t(1), published_at=t(3),
                        ingested_at=t(5))
        self.assertTrue(evaluate([report])["chronology_valid"])
        self.assertEqual(report.ingested_at, t(5))
        self.assertNotEqual(report.event_time, report.published_at)

    def test_naive_and_aware_chronology_abstains_without_exception(self):
        aware = datetime(2026, 11, 14, tzinfo=timezone.utc)
        naive = datetime(2026, 11, 13)
        result = evaluate([Report("A", "A", event_id="case-1", event_time=naive,
                                  published_at=aware),
                           Report("B", "B", event_id="case-1", event_time=aware,
                                  published_at=aware)])
        self.assertFalse(result["chronology_valid"])
        self.assertFalse(result["eligible_for_human_review"])

    def test_naive_ingest_timestamp_abstains(self):
        result = evaluate([Report("A", "A", event_id="case-1",
                                  ingested_at=datetime(2026, 11, 14)),
                           Report("B", "B", event_id="case-1")])
        self.assertFalse(result["chronology_valid"])
        self.assertFalse(result["eligible_for_human_review"])

    def test_ingest_before_publication_abstains(self):
        t = lambda day: datetime(2026, 11, day, tzinfo=timezone.utc)
        result = evaluate([
            Report("A", "A", event_id="case-1", event_time=t(10),
                   published_at=t(12), ingested_at=t(11)),
            Report("B", "B", event_id="case-1", event_time=t(10),
                   published_at=t(12), ingested_at=t(13)),
        ])
        self.assertFalse(result["chronology_valid"])
        self.assertFalse(result["eligible_for_human_review"])

    def test_ingest_before_event_without_publication_abstains(self):
        t = lambda day: datetime(2026, 11, day, tzinfo=timezone.utc)
        result = evaluate([
            Report("A", "A", event_id="case-1", event_time=t(12),
                   ingested_at=t(11)),
            Report("B", "B", event_id="case-1", event_time=t(12),
                   ingested_at=t(13)),
        ])
        self.assertFalse(result["chronology_valid"])
        self.assertFalse(result["eligible_for_human_review"])

    def test_equal_event_publication_ingest_timestamps_allowed(self):
        t = datetime(2026, 11, 14, tzinfo=timezone.utc)
        result = evaluate([
            Report("A", "A", event_id="case-1", event_time=t,
                   published_at=t, ingested_at=t),
            Report("B", "B", event_id="case-1", event_time=t,
                   published_at=t, ingested_at=t),
        ])
        self.assertTrue(result["chronology_valid"])
        self.assertTrue(result["eligible_for_human_review"])
        self.assertFalse(result["automatic_attack_attribution"])

    def test_non_datetime_ingestion_metadata_abstains(self):
        """Malformed persisted metadata must not become a trusted timestamp."""
        t = datetime(2026, 11, 14, tzinfo=timezone.utc)
        result = evaluate([
            Report("A", "A", event_id="case-1", event_time=t,
                   published_at=t, ingested_at="2026-11-14T00:00:00Z"),
            Report("B", "B", event_id="case-1", event_time=t,
                   published_at=t, ingested_at=t),
        ])
        self.assertFalse(result["chronology_valid"])
        self.assertFalse(result["eligible_for_human_review"])
        self.assertFalse(result["automatic_attack_attribution"])

    def test_timezone_offsets_compare_as_instants(self):
        """Different UTC offsets must not produce a false chronology failure."""
        from datetime import timedelta
        utc = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
        plus_two = timezone(timedelta(hours=2))
        result = evaluate([
            Report("A", "A", event_id="case-1", event_time=utc,
                   published_at=utc.astimezone(plus_two),
                   ingested_at=utc),
            Report("B", "B", event_id="case-1", event_time=utc,
                   published_at=utc, ingested_at=utc),
        ])
        self.assertTrue(result["chronology_valid"])
        self.assertTrue(result["eligible_for_human_review"])
        self.assertFalse(result["automatic_attack_attribution"])

    def test_humanitarian_sensitive_record_excluded(self):
        result = evaluate([Report("A", "A"), Report("rescue", "B",
                                  domain="humanitarian",
                                  has_sensitive_geometry=True)])
        self.assertEqual(result["independent_origins"], 1)
        self.assertEqual(result["excluded_sensitive"], 1)
        self.assertFalse(result["eligible_for_human_review"])

    def test_distinct_events_never_cross_corrobate(self):
        result = evaluate([Report("A", "A", event_id="case-1"),
                           Report("B", "B", event_id="case-2")])
        self.assertFalse(result["same_event"])
        self.assertFalse(result["eligible_for_human_review"])

    def test_missing_event_identity_abstains(self):
        result = evaluate([Report("A", "A"), Report("B", "B")])
        self.assertFalse(result["same_event"])
        self.assertFalse(result["eligible_for_human_review"])

    def test_partial_missing_event_identity_abstains(self):
        result = evaluate([Report("A", "A", event_id="case-1"),
                           Report("B", "B", event_id=None)])
        self.assertFalse(result["same_event"])
        self.assertFalse(result["eligible_for_human_review"])

    def test_unknown_origin_fails_closed(self):
        self.assertEqual(evaluate([Report("A", None),
                                   Report("B", None)])["independent_origins"], 0)


if __name__ == "__main__":
    unittest.main()
