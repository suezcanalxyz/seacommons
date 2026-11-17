"""Exercise the real upsert boundary with a disposable SQLite table only."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from core.db.models import MaritimeEpisodeDB
from core.intel.episode_store import save_episode


START = datetime(2026, 11, 17, 10, tzinfo=timezone.utc)


def test_real_upsert_keeps_single_id_and_cumulative_source_observations(monkeypatch):
    # This is an isolated in-memory database: never open the VM's production DB.
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    MaritimeEpisodeDB.__table__.create(bind=engine)

    @contextmanager
    def isolated_scope():
        with Session(engine) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    monkeypatch.setattr('core.db.session.session_scope', isolated_scope)

    def feature(*, first_hour=0, last_hour=26, ids, status='active'):
        return {
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [12, 35]},
            'properties': {
                'episode_id': 'episode:subj:mmsi:123456789:gap_episode:1',
                'episode_family': 'gap_episode', 'subject_ids': ['subj:mmsi:123456789'],
                'first_observed_at': (START + timedelta(hours=first_hour)).isoformat(),
                'last_observed_at': (START + timedelta(hours=last_hour)).isoformat(),
                'observation_ids': ids, 'episode_status': status,
                'analysis_state': 'evidence_candidate', 'publication_state': 'published',
                'resolution_state': 'open',
            },
        }

    first = save_episode(feature(ids=['ais:origin', 'ais:middle']))
    assert first.start_at.replace(tzinfo=timezone.utc) == START
    save_episode(feature(first_hour=2, last_hour=53, ids=['ais:middle', 'ais:reappearance']))
    save_episode(feature(first_hour=3, last_hour=12, ids=['ais:late-replay'], status='resolved'))
    with isolated_scope() as db:
        rows = db.execute(select(MaritimeEpisodeDB)).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.episode_id == first.episode_id
        assert row.start_at.replace(tzinfo=timezone.utc) == START
        assert row.end_at.replace(tzinfo=timezone.utc) == START + timedelta(hours=53)
        assert row.status == 'active'
        assert row.observation_ids == [
            'ais:origin', 'ais:middle', 'ais:reappearance', 'ais:late-replay',
        ]
