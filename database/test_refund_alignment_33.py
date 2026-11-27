"""PR #33 취소 환불 계약에 맞춘 DB 독립 계산 회귀 테스트.

실제 /api/compare 환불액의 기준은 backend/app/refund.py이며, 이 파일은
DB 계층 규정과 입력 검증의 호환성만 검사한다.
"""
import datetime as dt
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from build_db import DEFAULT_FILES
from load import load_many
import query_api as q


@pytest.fixture(scope='module')
def refund_database():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / 'refund.sqlite3'
        load_many(DEFAULT_FILES, path)
        yield path


def test_backend33_separates_cancel_refund_from_discount_refund(refund_database):
    result = q.quote(refund_database, 'busan_samrak_ecopark_soccer',
                     '2026-12-10', '08:00', '11:00', False,
                     cancellation_date='2026-12-08')
    assert result['user_cancel_refund_status'] == 'estimated'
    assert result['user_cancel_refund_rate_percent'] == 90
    assert result['user_cancel_refund_won'] == 18000
    assert result['user_cancel_net_cost_won'] == 2000
    assert 'expected_refund' not in result
    assert 'net_cost_after_refund' not in result


def test_backend33_rejects_past_and_after_use_date():
    today = dt.date.today()
    use_date = today + dt.timedelta(days=2)
    with pytest.raises(ValueError, match='취소일은 오늘보다 이전일 수 없습니다'):
        q.user_cancellation_refund(None, 'unused', use_date.isoformat(),
                                   (today - dt.timedelta(days=1)).isoformat(), {})
    with pytest.raises(ValueError, match='취소일은 이용일 이후일 수 없습니다'):
        q.user_cancellation_refund(None, 'unused', use_date.isoformat(),
                                   (use_date + dt.timedelta(days=1)).isoformat(), {})
    with pytest.raises(ValueError, match='취소일 날짜 형식 오류'):
        q.user_cancellation_refund(None, 'unused', use_date.isoformat(), 'bad-date', {})


def test_backend33_rain_and_force_majeure_rule_only(refund_database):
    # 우천과 불가항력은 시설 확인 전 확정 환불액을 산출하지 않는다.
    for facility in ('busan_samrak_ecopark_soccer', 'busan_gudeok_stadium_tennis'):
        rules = q.refund_rules(refund_database, facility, '2026-12-10')
        for rule in rules:
            if rule['reason'] in ('rain_same_day', 'rain_unused', 'force_majeure_or_city_event'):
                assert rule['rate_percent'] is None or 0 <= rule['rate_percent'] <= 100
    assert q.quote(refund_database, 'busan_samrak_ecopark_soccer',
                   '2026-12-10', '08:00', '11:00', False)['user_cancel_refund_status'] == 'not_requested'


def test_backend33_does_not_fix_amount_for_not_allowed_or_unverified(refund_database):
    disallowed = q.quote(refund_database, 'busan_samrak_ecopark_soccer',
                         '2026-12-10', '08:00', '11:00', False,
                         cancellation_date='2026-12-10')
    assert disallowed['user_cancel_refund_status'] == 'needs_review'
    assert disallowed['user_cancel_refund_won'] is None
    unverified = q.quote(refund_database, 'busan_gudeok_stadium_tennis',
                         '2026-12-10', '18:00', '20:00', False,
                         cancellation_date='2026-12-09')
    assert unverified['user_cancel_refund_status'] == 'needs_review'
    assert unverified['user_cancel_refund_won'] is None


def test_invalid_cancellation_rejected_even_when_time_rule_not_found(refund_database):
    # 백엔드 #33과 마찬가지로 예약 불가/미정 시간도 취소일 자체의 오류를 숨기지 않는다.
    today = dt.date.today()
    with pytest.raises(ValueError, match='취소일은 오늘보다 이전일 수 없습니다'):
        q.quote(refund_database, 'busan_samrak_ecopark_soccer',
                '2026-12-10', '00:00', '00:30', False,
                cancellation_date=(today - dt.timedelta(days=1)).isoformat())
