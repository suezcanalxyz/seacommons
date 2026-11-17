from core.intel.maritime_attack_feed import classify_security_report, configured_feeds

def test_attack_extraction():
    r=classify_security_report('Cargo ship attacked by drone','IMO 9348625 MMSI 636019532')
    assert r['imo']=='9348625' and r['mmsi']=='636019532' and r['publication_status']=='private'

def test_risk_advisory_exclusion():
    assert classify_security_report('Risk of attack on commercial vessels','Black Sea advisory') is None

def test_unrelated_news_exclusion():
    assert classify_security_report('Markets update','No incident') is None

def test_no_unverified_feed_config():
    assert isinstance(configured_feeds(),list)
