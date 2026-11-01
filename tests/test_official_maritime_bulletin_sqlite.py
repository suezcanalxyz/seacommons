# SPDX-License-Identifier: AGPL-3.0-or-later
"""Real canonical writer contract against an isolated, ephemeral SQLite DB.

This is a staging CI integration test, NOT an Oracle/production write. The
engine has no network credentials or filesystem persistence. In particular,
SQLite does not enforce VARCHAR(n), so check the PostgreSQL ORM widths too.
"""
from dataclasses import replace
from datetime import date, datetime, timezone
from unittest import TestCase

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from core.db.models import (
    Base, EntityDB, EntityRelationshipDB, LineageEdgeDB, SourceObservationDB,
    IntelEventDB, MaritimeEpisodeDB,
)
from core.intel.official_maritime_bulletin import (
    OfficialMaritimeBulletin, ingest_official_bulletin, prepare_official_bulletin,
)

UTC = timezone.utc
TABLES = (
    SourceObservationDB.__table__,
    LineageEdgeDB.__table__,
    EntityDB.__table__,
    EntityRelationshipDB.__table__,
)


def jet():
    return OfficialMaritimeBulletin(
        issuer="BG_MOD",
        bulletin_id="news9664",
        source_url="https://www.mod.bg/news9664",
        kind="attack",
        vessel_name="CONTSHIP JET",
        imo="9348625",
        mmsi="636019532",
        occurred_at=datetime(2026, 10, 28, 10, tzinfo=UTC),
        publication_date=date(2026, 10, 28),
    )


class IsolatedCanonicalBulletinWriterTests(TestCase):
    def setUp(self):
        # No connection to Oracle, no external server and no persistent file.
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=list(TABLES))

    def tearDown(self):
        self.engine.dispose()

    def test_postgres_column_widths_and_required_fields(self):
        prepared = prepare_official_bulletin(jet())
        for key in (
            "service", "lane", "observation_type", "source_name",
            "source_policy", "source_id", "source_url", "observed_at",
        ):
            column = SourceObservationDB.__table__.c[key]
            self.assertLessEqual(
                len(prepared[key]), column.type.length,
                f"{key} exceeds PostgreSQL VARCHAR({column.type.length})",
            )
        self.assertEqual(prepared["source_policy"], "official_metadata_unverified")
        self.assertEqual(prepared["provenance"]["attack_corroboration_allowed"], False)

    def test_writer_replay_revision_lineage_and_rollback(self):
        with Session(self.engine) as db:
            first = ingest_official_bulletin(db, jet())
            replay = ingest_official_bulletin(db, jet())
            revised = ingest_official_bulletin(
                db, replace(jet(), vessel_name="CONTSHIP JET (corrected)"),
            )
            self.assertFalse(first.replayed)
            self.assertTrue(replay.replayed)
            self.assertEqual(first.observation_id, replay.observation_id)
            self.assertNotEqual(first.observation_id, revised.observation_id)
            self.assertEqual(revised.provenance["vessel_imo"], "9348625")
            self.assertEqual(first.provenance["origin_authority_verified"], False)
            self.assertEqual(first.provenance["attack_corroboration_allowed"], False)
            self.assertEqual(first.provenance["published_at_utc"], None)
            self.assertEqual(first.observed_at, "2026-10-28T10:00:00+00:00")
            self.assertEqual(
                db.scalar(select(func.count()).select_from(SourceObservationDB)), 2,
            )
            # Canonical reported_by graph is written in the same transaction.
            self.assertEqual(
                db.scalar(select(func.count()).select_from(EntityRelationshipDB)), 2,
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(EntityDB)), 3,
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(LineageEdgeDB)), 0,
            )
            # The adapter must not write public IntelEvent/PLAY episodes.
            # Those tables are deliberately not even created in this DB.
            self.assertNotIn("intel_events", self.engine.dialect.get_table_names(db.connection()))
            self.assertNotIn("maritime_episodes", self.engine.dialect.get_table_names(db.connection()))
            db.rollback()
        with Session(self.engine) as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(SourceObservationDB)), 0,
            )
            self.assertEqual(
                db.scalar(select(func.count()).select_from(EntityRelationshipDB)), 0,
            )

    def test_unknown_time_and_anchorage_remain_explicit(self):
        bulletin = OfficialMaritimeBulletin(
            issuer="NAVAREA_IX", bulletin_id="420/26",
            source_url="https://hydrography.paknavy.gov.pk/navarea-ix-warnings/",
            kind="navigational_hazard", vessel_name="RITI",
            imo="9249075", mmsi="352002473",
            publication_date=date(2026, 10, 30),
            lat=26.401167, lon=56.412, location_uncertainty_km=10.0,
            location_role="anchorage",
        )
        with Session(self.engine) as db:
            obs = ingest_official_bulletin(db, bulletin)
            self.assertEqual(obs.observed_at, "2026-10-30")
            self.assertEqual(obs.provenance["observed_at_semantics"], "publication")
            self.assertEqual(obs.provenance["event_time_precision"], "unknown")
            self.assertEqual(obs.provenance["location_role"], "anchorage")
            self.assertEqual(obs.uncertainty_m, 10000.0)
            self.assertEqual(obs.provenance["attack_corroboration_allowed"], False)
            db.rollback()
