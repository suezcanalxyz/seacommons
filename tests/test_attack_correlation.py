from datetime import datetime, timezone
from core.intel.attack_correlation import AttackReport, AISGap, correlate_attack

def t(h,m,s=0): return datetime(2026,10,28,h,m,s,tzinfo=timezone.utc)

def test_contship_jet_regression():
    gap=AISGap('636019532',t(9,59,22),t(10,34,46),43.2659,28.8149)
    report=AttackReport('636019532','9348625',t(10,0),43.26,28.81,('Bulgarian MOD','Bulgarian Transport Ministry'))
    out=correlate_attack(report,gap,known_imo='9348625')
    assert out['classification']=='corroborated_attack_candidate'
    assert out['publication_allowed'] is False

def test_gap_alone_cannot_confirm_attack():
    gap=AISGap('636019532',t(9,59),t(10,34),43.26,28.81)
    report=AttackReport('636019532',None,t(10,0),43.26,28.81,())
    assert correlate_attack(report,gap)['classification']=='possible_attack_candidate'

def test_wrong_ship_is_unlinked():
    gap=AISGap('636019532',t(9,59),t(10,34),43.26,28.81)
    report=AttackReport('123456789',None,t(10,0),43.26,28.81,('a','b'))
    assert correlate_attack(report,gap)['classification']=='unlinked'

def test_distant_event_is_unlinked():
    gap=AISGap('636019532',t(9,59),t(10,34),43.26,28.81)
    report=AttackReport('636019532',None,t(10,0),40,24,('a','b'))
    assert correlate_attack(report,gap)['classification']=='unlinked'

def test_same_source_twice_not_corroborated():
    gap=AISGap('636019532',t(9,59),t(10,34),43.26,28.81)
    report=AttackReport('636019532',None,t(10,0),43.26,28.81,('MOD','mod'))
    assert correlate_attack(report,gap)['classification']=='possible_attack_candidate'


def test_missing_coverage_not_called_radio_jamming():
    gap=AISGap('636019532',t(9,59),t(10,34),43.26,28.81)
    report=AttackReport('636019532',None,t(10,0),43.26,28.81,('a','b'))
    result=correlate_attack(report,gap)
    assert result['ais_coverage_verified'] is False
    assert result['ais_gap_evidence_only'] is True
    assert result['publication_allowed'] is False

def test_provenance_preserved():
    gap=AISGap('636019532',t(9,59),t(10,34),43.26,28.81)
    report=AttackReport('636019532',None,t(10,0),43.26,28.81,('a','b'),
                        source_urls=('https://example.org/report',),received_at=t(11,0))
    result=correlate_attack(report,gap)
    assert result['source_urls']==('https://example.org/report',)
    assert result['received_at']==t(11,0).isoformat()


def test_news_first_without_gap():
    from core.intel.attack_correlation import AISFix, correlate_report_to_track
    report = AttackReport('636019532','9348625',t(10,0),43.2659,28.8149,('official','independent_media'))
    fix = AISFix('636019532',t(9,59),43.265926,28.8149)
    out = correlate_report_to_track(report,(fix,),known_imo='9348625')
    assert out['classification']=='corroborated_attack_candidate'
    assert out['ais_gap_required'] is False
    assert out['publication_allowed'] is False


def test_news_first_spatial_only_does_not_identify_ship():
    from core.intel.attack_correlation import AISFix, correlate_report_to_track
    report = AttackReport(None,None,t(10,0),43.2659,28.8149,('official',))
    fix = AISFix('636019532',t(9,59),43.265926,28.8149)
    out = correlate_report_to_track(report,(fix,))
    assert out['classification']=='spatial_candidate_identity_unresolved'


def test_news_first_rejects_wrong_time():
    from core.intel.attack_correlation import AISFix, correlate_report_to_track
    report = AttackReport('636019532',None,t(10,0),43.2659,28.8149,('official',))
    fix = AISFix('636019532',t(14,0),43.265926,28.8149)
    assert correlate_report_to_track(report,(fix,))['classification']=='unlinked'


def test_named_ship_without_report_coordinates_is_not_geospatially_confirmed():
    from core.intel.attack_correlation import AISFix, correlate_report_to_track
    report=AttackReport('636019532','9348625',t(10,0),None,None,('reuters','ap'))
    fix=AISFix('636019532',t(9,59),43.265926,28.8149)
    out=correlate_report_to_track(report,(fix,),known_imo='9348625')
    assert out['classification']=='identity_time_candidate'
    assert out['geospatial_verified'] is False
    assert out['publication_allowed'] is False
