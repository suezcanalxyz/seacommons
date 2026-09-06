from __future__ import annotations
from datetime import datetime, timezone

def test_review_metric_normalizes_unbounded_labels():
    from prometheus_client import generate_latest
    from core import observability
    secret='mmsi-247123456-private@example.com'
    observability.record_review_event(target_type=secret,decision=secret,outcome=secret)
    metrics=generate_latest().decode()
    assert secret not in metrics
    assert 'seacommons_review_events_total' in metrics and 'target_type="other"' in metrics

def test_review_metric_accepts_bounded_values():
    from prometheus_client import generate_latest
    from core import observability
    observability.record_review_event(target_type='humanitarian_resolution',decision='approve',outcome='applied')
    m=generate_latest().decode(); assert 'decision="approve"' in m and 'outcome="applied"' in m

def test_operator_summary_omits_rationale_snapshot_and_sensitive_fields():
    from core.db.models import ReviewRecordDB
    from core.db.session import engine, session_scope
    from core.review.summary import recent_review_summary
    ReviewRecordDB.__table__.create(bind=engine(),checkfirst=True)
    with session_scope() as db:
        db.query(ReviewRecordDB).delete()
        db.add(ReviewRecordDB(review_id='review:1',target_type='humanitarian_resolution',target_id='resolution:r1',target_version='v1',evidence_snapshot_id='xev:opaque',decision='approve',rationale='MMSI 247123456 MAYDAY',actor='operator:alice',reviewed_at=datetime(2026,9,6,21,0),requested_transition='resolved'))
    out=recent_review_summary(limit=10); assert out['total']==1
    item=out['items'][0]; serialized=str(item).lower()
    for bad in ('rationale','evidence_snapshot','247123456','mayday','mmsi','imo','callsign','transcript'): assert bad not in serialized
    assert item['decision']=='approve' and item['target_type']=='humanitarian_resolution'
