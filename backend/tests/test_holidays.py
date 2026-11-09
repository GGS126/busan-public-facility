from datetime import date

from app.repository import load_rule_data

calendar = load_rule_data().facilities[0].holiday_calendar


def test_calendar_covers_registered_rule_period():
    # PR #12 테니스장 규정의 적용기간(동절기)과 같다.
    assert calendar.covered_from == date(2026, 10, 1)
    assert calendar.covered_to == date(2027, 3, 31)


def test_substitute_holidays_included():
    assert calendar.is_holiday(date(2026, 10, 5))  # 개천절(토) 대체공휴일
    assert calendar.is_holiday(date(2027, 2, 9))  # 설 연휴 중 일요일 대체공휴일


def test_ordinary_days_are_not_holidays():
    assert not calendar.is_holiday(date(2026, 11, 9))
    assert not calendar.is_holiday(date(2026, 12, 24))


def test_every_facility_shares_the_calendar():
    facilities = load_rule_data().facilities
    assert all(facility.holiday_calendar == calendar for facility in facilities)
