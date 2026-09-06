from __future__ import annotations
from datetime import datetime, timezone
import pytest

def _review(**kw):
    from core.review.contracts import ReviewRecord
    v=dict(target_type='humanitarian_resolution',target_id='resolution:r1',target_version='humanitarian-resolution-v1',evidence_snapshot_id='xev:snap1',decision='approve',rationale='reviewed evidence',actor='operator:alice',reviewed_at=datetime(2026,9,6,20,50,tzinfo=timezone.utc),requested_transition='resolved')
    v.update(kw); return ReviewRecord(**v)

def _seed():
    from core.db.models import AssessmentDB, HumanitarianIncidentDB, IncidentTransitionDB, ReviewRecordDB
    from core.db.session import engine, session_scope
    for t in (AssessmentDB.__table__, HumanitarianIncidentDB.__table__, IncidentTransitionDB.__table__, ReviewRecordDB.__table__): t.create(bind=engine(),checkfirst=True)
    with session_scope() as db:
        for m in (IncidentTransitionDB,ReviewRecordDB,AssessmentDB,HumanitarianIncidentDB): db.query(m).delete()
        db.add(HumanitarianIncidentDB(incident_id='inc:1',lifecycle='needs_review',incident_status='needs_review',reported_at='2026-09-06T20:00:00+00:00',last_update_at='2026-09-06T20:00:00+00:00',review_status='pending',revision=1,source_observation_ids=[]))
        db.add(AssessmentDB(assessment_id='resolution:r1',incident_id='inc:1',field_type='resolution',value={'outcome':'rescue_confirmed'},supporting_claim_ids=['claim:1'],contradicting_claim_ids=[],method_version='humanitarian-resolution-v1',confidence=.9,review_state='needs_review'))

def test_approved_resolution_applies_audited_transition_without_publication():
    _seed(); from core.review.humanitarian import apply_humanitarian_review
    result=apply_humanitarian_review(_review())
    assert result.applied and result.lifecycle=='resolved'
    from core.db.models import AssessmentDB,HumanitarianIncidentDB,IncidentTransitionDB
    from core.db.session import session_scope
    with session_scope() as db:
        a=db.get(AssessmentDB,'resolution:r1'); i=db.get(HumanitarianIncidentDB,'inc:1')
        assert a.review_state=='approved' and i.lifecycle=='resolved' and i.incident_status=='resolved'
        tr=db.query(IncidentTransitionDB).filter_by(review_decision_id=_review().review_id).one()
        assert tr.to_state=='resolved' and tr.reason_code=='explicit_review_approval'
    assert 'publish' not in result.__dict__

def test_reject_marks_assessment_review_only_and_does_not_change_lifecycle():
    _seed(); from core.review.humanitarian import apply_humanitarian_review
    r=_review(decision='reject',requested_transition=None)
    result=apply_humanitarian_review(r); assert result.applied is False
    from core.db.models import AssessmentDB,HumanitarianIncidentDB,IncidentTransitionDB
    from core.db.session import session_scope
    with session_scope() as db:
        assert db.get(AssessmentDB,'resolution:r1').review_state=='rejected'
        assert db.get(HumanitarianIncidentDB,'inc:1').lifecycle=='needs_review'
        assert db.query(IncidentTransitionDB).count()==0

def test_needs_more_evidence_remains_needs_review_without_transition():
    _seed(); from core.review.humanitarian import apply_humanitarian_review
    apply_humanitarian_review(_review(decision='needs_more_evidence',requested_transition=None))
    from core.db.models import AssessmentDB,HumanitarianIncidentDB
    from core.db.session import session_scope
    with session_scope() as db:
        assert db.get(AssessmentDB,'resolution:r1').review_state=='needs_review'
        assert db.get(HumanitarianIncidentDB,'inc:1').lifecycle=='needs_review'

def test_target_version_mismatch_fails_closed():
    _seed(); from core.review.humanitarian import apply_humanitarian_review
    with pytest.raises(ValueError,match='target_version'): apply_humanitarian_review(_review(target_version='stale-version'))

def test_replay_does_not_duplicate_transition():
    _seed(); from core.review.humanitarian import apply_humanitarian_review
    r=_review(); apply_humanitarian_review(r); second=apply_humanitarian_review(r); assert second.replayed
    from core.db.models import IncidentTransitionDB
    from core.db.session import session_scope
    with session_scope() as db: assert db.query(IncidentTransitionDB).filter_by(review_decision_id=r.review_id).count()==1

def test_stale_humanitarian_review_is_not_persisted_to_ledger():
    _seed(); from core.review.humanitarian import apply_humanitarian_review
    from core.db.models import ReviewRecordDB
    from core.db.session import session_scope
    r=_review(target_version='stale-version')
    with pytest.raises(ValueError,match='target_version'): apply_humanitarian_review(r)
    with session_scope() as db: assert db.get(ReviewRecordDB,r.review_id) is None
