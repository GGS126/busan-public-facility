"""DB 후속 검토: 원본 공통 안내 분리, 미확인 서류 보존, 환불 필드 의미 검증."""
import datetime as dt
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from build_db import DEFAULT_FILES
from load import load_many
import query_api as q


def test_guidance_fields_are_separated_and_unambiguous():
    count = 0
    for file in DEFAULT_FILES:
        src = json.loads(Path(file).read_text(encoding='utf-8'))
        common = src['discount_common']
        if 'checklist_guidance' not in common:
            continue
        count += 1
        assert '다자녀인 동일 가족' not in common['checklist_guidance']
        assert common['multi_child_guidance'] == '다자녀인 동일 가족은 증빙자료 1부 제출 가능.'
    assert count == 7


def test_discount_guidance_is_category_specific_and_unknown_docs_preserved():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / 'facilities.sqlite3'
        load_many(DEFAULT_FILES, db)
        rules = q.discounts(db, 'busan_samrak_ecopark_tennis', '2026-12-05')
        by_id = {r['category_id']: r for r in rules}
        assert '다자녀인 동일 가족' in by_id['multi_child']['documents']
        assert '다자녀인 동일 가족' not in by_id['disabled']['documents']
        assert '감면 대상 이용자 이름' not in by_id['disabled']['documents']
        assert '감면 대상 이용자 이름' in by_id['disabled']['deadline']
        assert 'application_note' not in by_id['disabled']
        unknown = q.discounts(db, 'busan_samrak_ecopark_soccer', '2026-12-05')
        children = next(x for x in unknown if x['category_id'] == 'children_group')
        assert children['documents'] is None  # 모르는 서류를 확정 자료처럼 채우지 않는다
        assert '감면 대상 이용자 이름을 모두 기재' in children['deadline']
        assert '신청 절차:' in children['deadline']
        assert '경기장 이용시간 전' in children['deadline']


def test_cancellation_error_and_nonambiguous_refund_fields():
    today = dt.date.today()
    past = (today - dt.timedelta(days=1)).isoformat()
    future_use = (today + dt.timedelta(days=2)).isoformat()
    with pytest.raises(ValueError, match='취소일은 오늘보다 이전'):
        q.user_cancellation_refund(None, 'dummy', future_use, past, {})
    with pytest.raises(ValueError, match='취소일 날짜 형식'):
        q.user_cancellation_refund(None, 'dummy', future_use, 'abc', {})
    with pytest.raises(ValueError, match='취소일은 이용일 이후'):
        q.user_cancellation_refund(None, 'dummy', future_use, (today + dt.timedelta(days=3)).isoformat(), {})
    assert 'user_cancel_refund_won' in q.user_cancellation_refund(None, 'dummy', future_use, today.isoformat(), {})
