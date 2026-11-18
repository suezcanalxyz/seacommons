"""A newer MMSI position is not a validated AIS gap closure."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from core.db.models import IntelEventDB, MaritimeEpisodeDB, VesselTrackDB
from core.mda.watch import MdaWatch


NOW = datetime.now(timezone.utc).replace(microsecond=0)
MMSI = '123456789'


@pytest.mark.parametrize('attestation_kind', ['missing', 'wrong_track', 'wrong_source', 'verified'])
def test_mda_gap_reappearance_requires_bound_attestation(monkeypatch, attestation_kind):
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    for model in (IntelEventDB, MaritimeEpisodeDB, VesselTrackDB):
        model.__table__.create(bind=engine)

    @contextmanager
    def isolated():
        with Session(engine) as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    monkeypatch.setattr('core.db.session.session_scope', isolated)
    events = []
    monkeypatch.setattr('core.mda.watch.intel_store.update_metadata', lambda *args, **kwargs: events.append((args, kwargs)))
    monkeypatch.setattr(MdaWatch, 'scan_hypotheses', lambda *args, **kwargs: None)
    event_at = NOW - timedelta(hours=2)
    last_fix_at = NOW - timedelta(minutes=15)
    with isolated() as db:
        track = VesselTrackDB(
            mmsi=MMSI, ts=last_fix_at.replace(tzinfo=None),
            received_at=last_fix_at.replace(tzinfo=None), lat=35, lon=12,
            source='aisstream',
        )
        db.add(track)
        db.flush()
        attestation = dict(
            identity_validated=True, source_validated=True,
            track_id=str(track.id), mmsi=MMSI, source='aisstream',
            observed_at=last_fix_at.isoformat(),
        )
        if attestation_kind == 'wrong_track':
            attestation['track_id'] = '999999'
        elif attestation_kind == 'wrong_source':
            attestation['source'] = 'unrelated'
        metadata = {'anomaly_type': 'gap', 'silent_seconds': 3600}
        if attestation_kind != 'missing':
            metadata['reappearance_validation'] = attestation
        db.add(IntelEventDB(
            id='gap-1', timestamp_utc=event_at.isoformat(), type='ais_anomaly',
            severity='medium', title='AIS gap', source='aisstream',
            linked_mmsi=MMSI, meta=metadata,
        ))
    count = MdaWatch()._resolve_reappeared_gaps()
    expected = int(attestation_kind == 'verified')
    assert count == expected
    assert len(events) == expected
    with isolated() as db:
        row = db.execute(select(IntelEventDB)).scalar_one()
        assert (row.meta.get('incident_lifecycle') == 'resolved') is bool(expected)
        if expected:
            assert row.meta['gap_reappeared_at'] == last_fix_at.isoformat()
            assert row.meta['identity_validated'] is True
            assert row.meta['source_validated'] is True
