"""PR #32: 실SQLite에서 실제 POST /api/compare 체크리스트 회귀 테스트.

실행: python -m pytest -q database/test_compare_api.py
"""
from pathlib import Path
from datetime import datetime
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys

import pytest
from fastapi.testclient import TestClient

DB = Path(__file__).resolve().parent
ROOT = DB.parent
sys.path.insert(0, str(DB))
sys.path.insert(0, str(ROOT / "backend"))

from build_db import DEFAULT_FILES
from load import load_many
from app import main
from app import models
from app.options import build_options
from app.repository import load_sqlite_rule_data


@pytest.fixture(scope="module")
def client():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "facilities.sqlite3"
        load_many(DEFAULT_FILES, db)
        data = load_sqlite_rule_data(db)
        facilities = {facility.facility_id: facility for facility in data.facilities}
        # 고정 규정(2026년 하반기)을 재현할 수 있도록 테스트 기준일만 고정한다.
        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 26, tzinfo=tz)

        with patch.object(main, "facilities", facilities), patch.object(
            main, "available_options", build_options(data)
        ), patch.object(models, "datetime", FixedDateTime):
            with TestClient(main.app) as test_client:
                yield test_client


@pytest.mark.parametrize(
    "facility_id,category,documents_keyword,guide_keyword,start,end",
    [
        (
            "busan_haeundae_arboretum_tennis", "multi_child", "가족사랑카드",
            "반환신청서", "07:00", "09:00",
        ),
        (
            "busan_samrak_ecopark_tennis", "disabled", "장애인등록증",
            "반환신청 게시판", "08:00", "10:00",
        ),
        (
            "busan_gudeok_stadium_tennis", "disabled", "장애인등록증",
            "감경대상자 확인서", "08:00", "10:00",
        ),
    ],
)
def test_discount_guidance_in_compare_response(
    client, facility_id, category, documents_keyword, guide_keyword, start, end
):
    response = client.post(
        "/api/compare",
        json={
            "facility_ids": [facility_id],
            "conditions": {
                "sport": "tennis",
                "date": "2026-12-05",
                "start_time": start,
                "end_time": end,
                "discount_types": [category],
                "headcount": 2,
                "source": "direct",
            },
        },
    )
    assert response.status_code == 200, response.text
    [result] = response.json()["results"]
    checklist = " ".join(result["checklist"])
    assert documents_keyword in checklist, checklist
    assert guide_keyword in checklist, checklist
    if facility_id != "busan_gudeok_stadium_tennis":
        assert "이름을 모두 기재" in checklist, checklist
    if category != "multi_child":
        assert "가족사랑카드" not in checklist, checklist
        assert "다자녀인 동일 가족" not in checklist, checklist
