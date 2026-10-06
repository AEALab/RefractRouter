"""实际日历、时区及预算上界须采用不同语义。"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from refractrouter.deepseek_official_pricing import pricing


CN = ZoneInfo('Asia/Shanghai')


@pytest.mark.parametrize('month,day', [(1, 1), (2, 16), (2, 17), (4, 5), (5, 1),
                                     (6, 19), (9, 25), (10, 1), (10, 2)])
def test_holiday_weekdays_are_offpeak(month, day):
    instant = datetime(2026, month, day, 10, tzinfo=CN)
    actual = pricing('deepseek-flash', at=instant)
    assert actual['tier'] == 'offpeak'
    assert actual['inputPer1k'] == .001
    assert actual['calendarVerified']
    assert pricing('deepseek-flash', at=instant, conservative=True)['inputPer1k'] == .002


def test_working_weekend_is_still_offpeak_and_utc_is_converted():
    assert pricing('deepseek-flash', at=datetime(2026, 10, 10, 10, tzinfo=CN))['tier'] == 'offpeak'
    assert pricing('deepseek-flash', at=datetime(2026, 10, 8, 2, tzinfo=timezone.utc))['tier'] == 'peak'


@pytest.mark.parametrize('hour,minute,tier', [(8, 59, 'offpeak'), (9, 0, 'peak'),
    (12, 0, 'offpeak'), (14, 0, 'peak'), (18, 0, 'offpeak')])
def test_half_open_peak_boundaries(hour, minute, tier):
    assert pricing('deepseek-flash', at=datetime(2026, 10, 8, hour, minute, tzinfo=CN))['tier'] == tier


def test_unknown_calendar_is_marked_as_upper_bound():
    result = pricing('deepseek-flash', at=datetime(2027, 1, 1, 10, tzinfo=CN))
    assert result['tier'] == 'calendar-unverified-upper-bound'
    assert result['calendarVerified'] is False


def test_adjusted_weekday_break_does_not_assume_unconfirmed_discount():
    result = pricing('deepseek-flash', at=datetime(2026, 10, 6, 10, tzinfo=CN))
    assert result['tier'] == 'holiday-adjustment-unverified-upper-bound'
    assert result['inputPer1k'] == .002
