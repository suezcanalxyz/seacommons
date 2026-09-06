from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timezone
import pytest

def _review(**kw):
    from core.review.contracts import ReviewRecord
    v=dict(target_type='maritime_hypothesis',target_id='hyp:v1:dark:1',target_version='candidate',evidence_snapshot_id='xev:maritime1',decision='approve',rationale='reviewed hypothesis evidence',actor='operator:bob',reviewed_at=datetime(2026,9,6,21,0,tzinfo=timezone.utc),requested_transition='collecting')
    v.update(kw); return ReviewRecord(**v)

def _seed(*,state='candidate',allegation=False):
    from core.db.models import InvestigationHypothesisDB, ReviewRecordDB
    from core.db.session import engine, session_scope
    for t in (InvestigationHypothesisDB.__table__,ReviewRecordDB.__table__): t.create(bind=engine(),checkfirst=True)
    with session_scope() as db:
        db.query(ReviewRecordDB).delete(); db.query(InvestigationHypothesisDB).delete()
        db.add(InvestigationHypothesisDB(hypothesis_id='hyp:v1:dark:1',episode_id='episode:1',hypothesis_type='dark_transit',subject_ids=['subj:1'],state=state,reason_codes=['gap'],counter_indicators=[],evidence_links=['obs:1','obs:2'],evidence_stage='corroborated',has_unresolved_blocking_identity_conflict=False,allegation_shaped_wording=allegation,explicit_review_done=False,audit_history=[]))

def test_approve_uses_existing_state_machine_and_sets_explicit_review_done():
    _seed(allegation=True); from core.review.maritime import apply_maritime_review
    result=apply_maritime_review(_review())
    assert result.applied and result.state=='collecting'
    from core.intel.hypothesis_store import get_hypothesis
    h=get_hypothesis('hyp:v1:dark:1'); assert h.explicit_review_done is True and h.state=='collecting'
    assert h.audit_history[-1].actor==f'review:{_review().review_id}'

def test_reject_uses_state_machine_and_never_publishes():
    _seed(); from core.review.maritime import apply_maritime_review
    result=apply_maritime_review(_review(decision='reject',requested_transition=None))
    assert result.state=='rejected'
    assert 'publish' not in result.__dict__

def test_needs_more_evidence_does_not_advance_state():
    _seed(); from core.review.maritime import apply_maritime_review
    result=apply_maritime_review(_review(decision='needs_more_evidence',requested_transition=None))
    assert result.applied is False and result.state=='candidate'

def test_target_version_must_match_current_hypothesis_state():
    _seed(); from core.review.maritime import apply_maritime_review
    with pytest.raises(ValueError,match='target_version'): apply_maritime_review(_review(target_version='review_ready'))

def test_invalid_state_machine_shortcut_still_fails():
    _seed(); from core.review.maritime import apply_maritime_review
    with pytest.raises(ValueError,match='invalid transition'): apply_maritime_review(_review(requested_transition='assessed'))

def test_replay_does_not_append_duplicate_audit_entry():
    _seed(); from core.review.maritime import apply_maritime_review
    r=_review(); first=apply_maritime_review(r); second=apply_maritime_review(r)
    assert first.state=='collecting' and second.replayed
    from core.intel.hypothesis_store import get_hypothesis
    h=get_hypothesis(r.target_id); assert len(h.audit_history)==1

def test_same_actor_distinct_review_is_not_mistaken_for_replay():
    _seed(); from core.review.maritime import apply_maritime_review
    first=_review(); apply_maritime_review(first)
    second=_review(target_version='collecting',evidence_snapshot_id='xev:maritime2',reviewed_at=datetime(2026,9,6,21,5,tzinfo=timezone.utc),requested_transition='review_ready')
    result=apply_maritime_review(second)
    assert result.replayed is False and result.state=='review_ready'

def test_stale_maritime_review_is_not_persisted_to_ledger():
    _seed(); from core.review.maritime import apply_maritime_review
    from core.db.models import ReviewRecordDB
    from core.db.session import session_scope
    r=_review(target_version='review_ready')
    with pytest.raises(ValueError,match='target_version'): apply_maritime_review(r)
    with session_scope() as db: assert db.get(ReviewRecordDB,r.review_id) is None
