# SPDX-License-Identifier: AGPL-3.0-or-later
"""PostgreSQL-only canonical bulletin writer contract on an ephemeral CI service.

No Oracle credentials, no external database, no production migration and no
scheduler. The test refuses any host other than loopback and any database
other than its dedicated disposable CI database. All inserted rows are rolled
back; GitHub Actions destroys the PostgreSQL service after the job.
"""
import os
from dataclasses import replace
from datetime import date, datetime, timezone
from unittest import TestCase, skipUnless

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from core.db.models import (
    Base, EntityDB, EntityRelationshipDB, LineageEdgeDB, SourceObservationDB, VesselTrackDB,
)
from core.intel.official_maritime_bulletin import (
    OfficialMaritimeBulletin, ingest_official_bulletin,
)

URL_ENV = "SC_ATTACK_TEST_PG_URL"
ALLOWED_DATABASE = "seacommons_attack_test"
TABLES = (
    SourceObservationDB.__table__,
    LineageEdgeDB.__table__,
    EntityDB.__table__,
    EntityRelationshipDB.__table__,
    VesselTrackDB.__table__,
)


def _isolated_url(raw: str) -> str:
    """Reject non-ephemeral and non-local databases before any connection."""
    url = make_url(raw)
    if (url.get_backend_name() != "postgresql"
            or url.host not in {"localhost", "127.0.0.1", "::1"}
            or url.database != ALLOWED_DATABASE
            or url.port != 5432):
        raise ValueError("Refusing non-local/non-test PostgreSQL database")
    return raw


def jet():
    return OfficialMaritimeBulletin(
        issuer="BG_MOD", bulletin_id="news9664",
        source_url="https://www.mod.bg/news9664", kind="attack",
        # Real Ministry report does not publish ship IMO/MMSI.
        vessel_name="CONTSHIP JET",
        occurred_at=datetime(2026, 10, 28, 10, tzinfo=timezone.utc),
        publication_date=date(2026, 10, 28),
    )


class PostgresURLSafetyTests(TestCase):
    def test_refuses_oracle_or_non_test_databases(self):
        for url in (
            "postgresql+psycopg://u:p@oracle.example:5432/seacommons_attack_test",
            "postgresql+psycopg://u:p@127.0.0.1:5432/seacommons",
            "postgresql+psycopg://u:p@127.0.0.1:5433/seacommons_attack_test",
            "sqlite:///:memory:",
        ):
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "Refusing"):
                    _isolated_url(url)


@skipUnless(os.getenv(URL_ENV), "Only enabled with an ephemeral local CI PostgreSQL URL")
class EphemeralPostgresCanonicalWriterTests(TestCase):
    @classmethod
    def setUpClass(cls):
        # Fail closed BEFORE opening a socket.
        cls.engine = create_engine(_isolated_url(os.environ[URL_ENV]))
        Base.metadata.create_all(cls.engine, tables=list(TABLES))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_real_postgres_replay_revision_lineage_and_transaction_rollback(self):
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
            self.assertEqual(first.provenance["vessel_imo"], "")
            self.assertEqual(first.provenance["vessel_mmsi"], "")
            self.assertEqual(first.subject_refs, [])
            self.assertEqual(first.provenance["origin_authority_verified"], False)
            self.assertEqual(first.provenance["attack_corroboration_allowed"], False)
            self.assertEqual(first.observed_at, "2026-10-28T10:00:00+00:00")
            self.assertTrue(first.received_at)
            self.assertEqual(db.scalar(select(func.count()).select_from(SourceObservationDB)), 2)
            self.assertEqual(db.scalar(select(func.count()).select_from(EntityRelationshipDB)), 2)
            self.assertEqual(db.scalar(select(func.count()).select_from(EntityDB)), 3)
            self.assertEqual(db.scalar(select(func.count()).select_from(LineageEdgeDB)), 0)
            db.rollback()
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(SourceObservationDB)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(EntityRelationshipDB)), 0)

    def test_anchorage_does_not_become_incident_site(self):
        riti = OfficialMaritimeBulletin(
            issuer="NAVAREA_IX", bulletin_id="420/26",
            source_url="https://hydrography.paknavy.gov.pk/navarea-ix-warnings/",
            kind="navigational_hazard", vessel_name="RITI",
            imo="9249075", mmsi="352002473",
            publication_date=date(2026, 10, 30),
            lat=26.401167, lon=56.412,
            location_uncertainty_km=10.0, location_role="anchorage",
        )
        with Session(self.engine) as db:
            obs = ingest_official_bulletin(db, riti)
            self.assertEqual(obs.observed_at, "2026-10-30")
            self.assertEqual(obs.provenance["observed_at_semantics"], "publication")
            self.assertEqual(obs.provenance["event_time_precision"], "unknown")
            self.assertEqual(obs.provenance["location_role"], "anchorage")
            self.assertEqual(obs.uncertainty_m, 10000.0)
            self.assertEqual(obs.provenance["attack_corroboration_allowed"], False)
            db.rollback()

    def test_reviewed_postgres_bulletins_cannot_invent_independent_sources(self):
        """Real PostgreSQL rows -> reviewed read path; publisher != origin.

        Two different official publishers and two complete timestamp sets
        still cannot count as independent witnesses without verified origin
        attribution. This test never commits and never publishes.
        """
        from core.intel.maritime_attack_correlation import VesselRef
        from core.intel.maritime_attack_observation_readonly import (
            correlate_reviewed_db_observations,
        )

        event_time = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
        primary = replace(
            jet(), publication_date=None,
            published_at=datetime(2026, 10, 28, 11, tzinfo=timezone.utc),
        )
        synthetic_relay = OfficialMaritimeBulletin(
            issuer="MSCIO", bulletin_id="synthetic-jet-regression",
            source_url="https://mscio.eu/alerts/synthetic-jet-regression",
            kind="attack", vessel_name="CONTSHIP JET",
            imo="9348625", mmsi="636019532",
            occurred_at=event_time,
            published_at=datetime(2026, 10, 28, 11, 30, tzinfo=timezone.utc),
        )
        with Session(self.engine) as db:
            first = ingest_official_bulletin(db, primary)
            second = ingest_official_bulletin(db, synthetic_relay)
            ids = (first.observation_id, second.observation_id)
            reviewed = {
                first.observation_id: {
                    "reviewed": True, "reviewed_by": "staging-test",
                    "kind": "attack", "occurred_at": event_time,
                    # BG MOD original has the ship name, but NO ship IDs.
                    "vessel_name": "CONTSHIP JET",
                    "time_uncertainty_minutes": 0,
                },
                second.observation_id: {
                    "reviewed": True, "reviewed_by": "staging-test",
                    "kind": "attack", "occurred_at": event_time,
                    # Synthetic MSCIO report is deliberately identified.
                    "imo": "9348625", "mmsi": "636019532",
                    "vessel_name": "CONTSHIP JET",
                    "time_uncertainty_minutes": 0,
                },
            }
            result = correlate_reviewed_db_observations(
                VesselRef("9348625", "636019532", "CONTSHIP JET"),
                ids, reviewed, db,
            )
            self.assertEqual(result.blocked_reasons, ())
            self.assertEqual(result.loaded_count, 2)
            self.assertIsNotNone(result.correlation)
            self.assertEqual(result.correlation.status, "candidate")
            self.assertEqual(result.correlation.independent_groups, ())
            self.assertFalse(result.correlation.publication_allowed)
            self.assertTrue(result.correlation.requires_operator_review)
            db.rollback()
        with Session(self.engine) as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(SourceObservationDB)),
                0,
            )

    def test_source_faithful_jet_identity_link_and_candidate_in_isolated_postgres(self):
        """Real MOD metadata -> canonical row -> separate ID link -> candidate.

        This is an isolated transaction, not a production import. A reviewed
        external crosswalk is identity context, NEVER an independent attack
        witness; the original report remains name-only and unmodified.
        """
        from core.intel.maritime_attack_correlation import VesselRef
        from core.intel.maritime_attack_identity_evidence import (
            ExternalVesselIdentity, link_external_vessel_identity,
        )
        from core.intel.maritime_attack_observation_readonly import (
            correlate_reviewed_db_observations,
        )

        with Session(self.engine) as db:
            primary = ingest_official_bulletin(db, jet())
            self.assertEqual(primary.subject_refs, [])
            self.assertEqual(primary.provenance["vessel_imo"], "")
            self.assertEqual(primary.provenance["vessel_mmsi"], "")
            identity = ExternalVesselIdentity(
                source_record_id="synthetic-jet-registry-crosswalk",
                source_url="https://example.org/ships/9348625",
                vessel_name="CONTSHIP JET",
                imo="9348625", mmsi="636019532",
                published_at=datetime(2026, 10, 28, 10, 30, tzinfo=timezone.utc),
                received_at=datetime(2026, 10, 28, 11, tzinfo=timezone.utc),
                reviewed_by="ci-reviewer",
            )
            link = link_external_vessel_identity(jet(), [identity])
            self.assertEqual(link.status, "linked_for_review")
            self.assertEqual(link.vessel.imo, "9348625")
            self.assertEqual(link.vessel.mmsi, "636019532")
            self.assertFalse(link.attack_corroboration_allowed)
            result = correlate_reviewed_db_observations(
                VesselRef(link.vessel.imo, link.vessel.mmsi, "CONTSHIP JET"),
                (primary.observation_id,),
                {primary.observation_id: {
                    "reviewed": True, "reviewed_by": "ci-reviewer",
                    "kind": "attack",
                    "occurred_at": datetime(2026, 10, 28, 10, tzinfo=timezone.utc),
                    "vessel_name": "CONTSHIP JET",
                    "time_uncertainty_minutes": 0,
                }},
                db,
            )
            self.assertEqual(result.blocked_reasons, ())
            self.assertEqual(result.correlation.status, "candidate")
            self.assertEqual(result.correlation.independent_groups, ())
            self.assertFalse(result.correlation.publication_allowed)
            self.assertTrue(result.correlation.requires_operator_review)
            self.assertEqual(
                db.get(SourceObservationDB, primary.observation_id).subject_refs, []
            )
            db.rollback()
        with Session(self.engine) as db:
            self.assertEqual(
                db.scalar(select(func.count()).select_from(SourceObservationDB)), 0
            )

    def test_postgres_publication_only_cannot_become_incident_time(self):
        """A real persisted NAVAREA anchorage cannot become an attack."""
        from core.intel.maritime_attack_correlation import VesselRef
        from core.intel.maritime_attack_observation_readonly import (
            correlate_reviewed_db_observations,
        )

        warning = OfficialMaritimeBulletin(
            issuer="NAVAREA_IX", bulletin_id="synthetic-anchorage-regression",
            source_url="https://hydrography.paknavy.gov.pk/navarea-ix-warnings/",
            kind="navigational_hazard", vessel_name="RITI",
            imo="9249075", mmsi="352002473",
            publication_date=date(2026, 10, 30),
            lat=26.401167, lon=56.412, location_role="anchorage",
            location_uncertainty_km=10,
        )
        with Session(self.engine) as db:
            obs = ingest_official_bulletin(db, warning)
            result = correlate_reviewed_db_observations(
                VesselRef("9249075", "352002473", "RITI"),
                (obs.observation_id,),
                {obs.observation_id: {
                    "reviewed": True, "reviewed_by": "staging-test",
                    "kind": "attack",
                    "occurred_at": datetime(2026, 10, 30, 3, tzinfo=timezone.utc),
                    "imo": "9249075", "mmsi": "352002473",
                    "vessel_name": "RITI",
                    "lat": 26.401167, "lon": 56.412,
                    "uncertainty_km": 0, "time_uncertainty_minutes": 0,
                }}, db,
            )
            self.assertIsNone(result.correlation)
            self.assertEqual(
                result.blocked_reasons,
                ("not_an_incident_claim:" + obs.observation_id,),
            )
            db.rollback()

    def test_bounded_ais_read_requires_postgres_read_only_transaction(self):
        """Real PostgreSQL SELECT gate; no synthetic fixtures or writes."""
        from core.intel.maritime_attack_ais_context_readonly import (
            load_ais_context_db,
        )
        event = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
        with Session(self.engine) as db:
            # A normal read-write session must not access AIS context through
            # this adapter, even when the query itself would be a SELECT.
            with self.assertRaisesRegex(ValueError, "READ ONLY"):
                load_ais_context_db(db, "636019532", event)
            db.rollback()
        with Session(self.engine) as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            result = load_ais_context_db(db, "636019532", event)
            self.assertTrue(result.complete)
            self.assertEqual(result.fixes, ())
            self.assertEqual(result.track_ids, ())
            self.assertEqual(result.inspected_rows, 0)
            db.rollback()
