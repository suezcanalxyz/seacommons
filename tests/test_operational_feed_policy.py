from datetime import datetime, timezone, timedelta
from core.intel.operational_feed_policy import humanitarian_live_eligible as eligible

def test_old_missing_report_excluded():
    assert not eligible(text='We lost contact with 20 people on October 16',timestamp='2026-10-16T12:00:00+00:00',is_distress=True,now=datetime(2026,10,30,tzinfo=timezone.utc))
def test_fresh_retrospective_excluded():
    now=datetime(2026,10,30,tzinfo=timezone.utc)
    assert not eligible(text='Traces were lost yesterday',timestamp=now.isoformat(),is_distress=True,now=now)
def test_fresh_emergency_allowed():
    now=datetime(2026,10,30,tzinfo=timezone.utc)
    assert eligible(text='Mayday immediate assistance needed',timestamp=now.isoformat(),is_distress=True,now=now)
def test_non_distress_excluded():
    now=datetime(2026,10,30,tzinfo=timezone.utc)
    assert not eligible(text='NGO annual report',timestamp=now.isoformat(),is_distress=False,now=now)


def test_real_alarm_phone_oct16_missing_report_is_not_live():
    now=datetime(2026,10,16,20,5,tzinfo=timezone.utc)
    text='We were alerted to 28 people who left Algeria heading towards Spain on 14 October. Since then, there are no news from them and their relatives are very worried.'
    assert not eligible(text=text,timestamp='2026-10-16T20:04:03+00:00',is_distress=True,now=now)

def test_real_alarm_phone_oct17_missing_report_is_not_live():
    now=datetime(2026,10,17,20,16,tzinfo=timezone.utc)
    text='16 people in distress on their way from Algiers. They left on 14 October, since then there are no news from them.'
    assert not eligible(text=text,timestamp='2026-10-17T20:15:59+00:00',is_distress=True,now=now)


def test_fresh_unreachable_group_report_is_retrospective_not_live():
    now = datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc)
    text = (
        "14 people in distress in the WesternMed. Relatives alerted us to the group "
        "that left Mostaganem on 27 October. Neither we nor their relatives are able "
        "to reach them. The authorities are alerted."
    )
    assert not eligible(
        text=text,
        timestamp="2026-11-02T19:31:30+00:00",
        is_distress=True,
        now=now,
    )
