from __future__ import annotations
from datetime import datetime, timezone


def _record(**kw):
    from core.review.contracts import ReviewRecord
    v=dict(target_type='humanitarian_resolution',target_id='resolution:r1',target_version='humanitarian-resolution-v1',evidence_snapshot_id='xev:abc',decision='approve',rationale='reviewed',actor='operator:alice',reviewed_at=datetime(2026,9,6,20,45,tzinfo=timezone.utc),requested_transition='resolved')
    v.update(kw); return ReviewRecord(**v)

def test_ledger_replay_is_idempotent_and_append_only():
    from core.review.ledger import persist_review
    from core.db.models import ReviewRecordDB
    from core.db.session import engine, session_scope
    ReviewRecordDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db: db.query(ReviewRecordDB).delete()
    r=_record(); a=persist_review(r); b=persist_review(r)
    assert a.review_id==b.review_id and a.replayed is False and b.replayed is True
    with session_scope() as db: assert db.query(ReviewRecordDB).count()==1

def test_distinct_decision_or_target_version_appends_new_record():
    from core.review.ledger import persist_review
    from core.db.models import ReviewRecordDB
    from core.db.session import engine, session_scope
    ReviewRecordDB.__table__.create(bind=engine(), checkfirst=True)
    with session_scope() as db: db.query(ReviewRecordDB).delete()
    persist_review(_record())
    persist_review(_record(decision='reject',requested_transition=None))
    persist_review(_record(target_version='humanitarian-resolution-v2'))
    with session_scope() as db: assert db.query(ReviewRecordDB).count()==3

def test_ledger_schema_contains_only_review_metadata_and_references():
    from core.db.models import ReviewRecordDB
    cols=set(ReviewRecordDB.__table__.columns.keys())
    assert {'review_id','target_type','target_id','target_version','evidence_snapshot_id','decision','rationale','actor','reviewed_at','requested_transition','created_at'} <= cols
    for bad in ('raw_payload','raw_evidence','mmsi','imo','callsign','transcript','lifecycle','publication_status'):
        assert bad not in cols

def test_persist_review_does_not_mutate_target_objects():
    from core.review.ledger import persist_review
    from core.db.models import AssessmentDB, InvestigationHypothesisDB, ReviewRecordDB
    from core.db.session import engine, session_scope
    for t in (AssessmentDB.__table__, InvestigationHypothesisDB.__table__, ReviewRecordDB.__table__): t.create(bind=engine(), checkfirst=True)
    with session_scope() as db:
        db.query(ReviewRecordDB).delete(); db.query(AssessmentDB).delete(); db.query(InvestigationHypothesisDB).delete()
        db.add(AssessmentDB(assessment_id='resolution:r1',incident_id='inc:1',field_type='resolution',value={'outcome':'rescue_confirmed'},supporting_claim_ids=[],contradicting_claim_ids=[],method_version='humanitarian-resolution-v1',confidence=.9,review_state='needs_review'))
    persist_review(_record())
    with session_scope() as db:
        row=db.get(AssessmentDB,'resolution:r1'); assert row.review_state=='needs_review' and row.value['outcome']=='rescue_confirmed'
