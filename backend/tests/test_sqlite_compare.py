import subprocess
from datetime import datetime, timedelta
import sys

import pytest
from fastapi.testclient import TestClient

from app import main

from app.facility_catalog import DB_PATH, read_catalog
from app.models import KST, Conditions
from app.sqlite_compare import compare_sqlite, load_query_api


@pytest.fixture(scope="module")
def sqlite_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("sqlite-fee") / "facilities.sqlite3"
    subprocess.run([sys.executable, str(DB_PATH.with_name("build_db.py")), "--db", str(path)], check=True)
    return path


@pytest.fixture
def gudeok(sqlite_db):
    facilities, _ = read_catalog(sqlite_db)
    return next(facility for facility in facilities if facility["facility_id"] == "busan_gudeok_stadium_tennis")


def test_gudeok_quote_includes_mandatory_lighting_and_source(sqlite_db, gudeok):
    result = compare_sqlite(sqlite_db, gudeok, Conditions(
        sport="tennis", date="2026-11-09", start_time="19:00", end_time="21:00", source="direct",
    ))

    assert result.fee.status == "calculated"
    assert [(item.type, item.amount) for item in result.fee.items] == [("base", 8000), ("lighting", 20000)]
    assert result.fee.payment_due == 28000
    assert result.sources[0].source_id == result.fee.items[0].source_id


def test_sqlite_quote_leaves_unresolved_discount_out_of_total(sqlite_db, gudeok):
    result = compare_sqlite(sqlite_db, gudeok, Conditions(
        sport="tennis", date="2026-11-09", start_time="19:00", end_time="21:00",
        discount_types=["multi_child"], source="direct",
    ))

    assert result.fee.status == "needs_review"
    assert result.fee.payment_due is None
    assert result.fee.review_items[0].target == "discount"


def test_expired_rule_source_is_not_displayed(sqlite_db, gudeok):
    result = compare_sqlite(sqlite_db, gudeok, Conditions(
        sport="tennis", date="2099-01-01", start_time="19:00", end_time="21:00", source="direct",
    ))
    assert result.sources == []
    assert result.fee.review_items[0].source_id is None
    assert result.terms.booking_open is None
    assert result.fee.review_items[0].code == "rule_not_in_effect"


@pytest.mark.parametrize(("overrides", "code"), [
    ({"sport": "futsal"}, "invalid_option"),
    ({"discount_types": ["unknown"]}, "invalid_option"),
    ({}, "rule_conflict"),
])
def test_sqlite_compare_handles_invalid_options_and_conflicts(sqlite_db, gudeok, monkeypatch, overrides, code):
    monkeypatch.setattr(main, "DB_PATH", sqlite_db)
    query = load_query_api()
    def conflicting_quote(*args):
        raise ValueError("중복된 요금 규정")
    monkeypatch.setattr(query, "quote", conflicting_quote)
    with TestClient(main.app) as client:
        day = (datetime.now(KST).date() + timedelta(days=1)).isoformat()
        conditions = {
            "sport": "tennis", "date": day, "source": "direct", "start_time": "19:00", "end_time": "21:00",
        }
        response = client.post("/api/compare", json={
            "facility_ids": [gudeok["facility_id"]], "conditions": conditions | overrides,
        })
    if overrides:
        assert response.status_code == 400
        assert response.json()["error"]["fields"][0]["code"] == code
    else:
        assert response.status_code == 200
        fee = response.json()["results"][0]["fee"]
        assert fee["payment_due"] is None
        assert fee["review_items"][0]["code"] == code


@pytest.mark.parametrize(("day", "amount"), [("2026-11-10", 6000), ("2026-12-25", 9000)])
def test_samrak_uses_calendar_for_weekday_and_holiday(sqlite_db, day, amount):
    catalog, _ = read_catalog(sqlite_db)
    samrak = next(facility for facility in catalog if facility["facility_id"] == "busan_samrak_ecopark_tennis")
    result = compare_sqlite(sqlite_db, samrak, Conditions(
        sport="tennis", date=day, start_time="08:00", end_time="10:00", source="direct",
    ))
    assert result.fee.status == "calculated"
    assert result.fee.payment_due == amount


def test_gudeok_rejects_duration_over_limit(sqlite_db, gudeok):
    result = compare_sqlite(sqlite_db, gudeok, Conditions(
        sport="tennis", date="2026-11-10", start_time="10:00", end_time="14:00", source="direct",
    ))
    assert result.fee.status == "not_eligible"
    assert result.fee.review_items[0].code == "duration_not_allowed"


def test_sqlite_compare_uses_one_read_connection(sqlite_db, gudeok):
    from unittest.mock import patch
    query = load_query_api()
    with patch.object(query.sqlite3, "connect", wraps=query.sqlite3.connect) as connect:
        result = compare_sqlite(sqlite_db, gudeok, Conditions(
            sport="tennis", date="2026-11-30", start_time="10:00", end_time="12:00", source="direct",
        ))
    assert result.fee.status == "calculated"
    assert connect.call_count == 1
