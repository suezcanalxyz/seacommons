from core.api.routes.play import _evidence_audit


def test_evidence_audit_separates_satellite_coverage_from_corrob():
    timeline = [
        {'id':'report:1', 'at':'2026-10-13T08:00:00Z', 'type':'report', 'geometry':{'type':'Point','coordinates':[14,35]}, 'properties':{'url':'https://example.org/original'}},
        {'id':'sat:1', 'at':'2026-10-13T08:05:00Z','type':'satellite','geometry':{'type':'Polygon','coordinates':[[[14,35],[15,35],[14,36],[14,35]]]},'properties':{'evidence_role':'context'}},
        {'id':'drift:1','at':'2026-10-13T08:10:00Z','type':'drift','properties':{}},
    ]
    data=_evidence_audit(timeline,independent_lineages=['source-a'],counter_indicators=['coverage_gap'])
    assert data['counts']['direct_observation']==1
    assert data['counts']['context_only']==1
    assert data['counts']['modelled']==1
    assert data['counts']['linked_source']==1
    assert data['lineage_count']==1
    assert 'coverage_gap' in data['counter_indicators']
    assert data['interpretation'].find('not a probability') >= 0


def test_no_evidence_is_explicitly_incomplete():
    data=_evidence_audit([])
    assert data['timeline_items']==0
    assert 'No dated timeline evidence available' in data['next_checks']
