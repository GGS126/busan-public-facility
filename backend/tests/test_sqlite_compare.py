import sqlite3
import subprocess
from datetime import datetime, timedelta
import sys
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app import main, models

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
    query = load_query_api(DB_PATH.with_name("query_api.py"))
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


@pytest.mark.parametrize(("day", "closure_status", "time_status", "has_slots", "expected_fee"), [
    ("2027-02-07", "closed", "not_eligible", False, None),
    ("2027-02-06", "no_scheduled_closure", "eligible", True, 9000),
    ("2099-04-05", "needs_calendar_resolution", "unknown", True, None),
])
def test_search_and_compare_agree_on_holiday_closure(
    sqlite_db, tmp_path, monkeypatch, day, closure_status, time_status, has_slots, expected_fee,
):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 15, tzinfo=tz)

    monkeypatch.setattr(models, "datetime", FixedDateTime)
    db = tmp_path / "closure.sqlite3"
    db.write_bytes(sqlite_db.read_bytes())
    facility_id = "busan_samrak_ecopark_tennis"
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("UPDATE rule_sets SET effective_to = ? WHERE facility_id = ?", ("2099-04-05", facility_id))
    monkeypatch.setattr(main, "DB_PATH", db)
    conditions = {
        "sport": "tennis", "districts": ["사상구"], "date": day,
        "start_time": "08:00", "end_time": "10:00", "source": "direct",
    }
    client = TestClient(main.app)
    search = client.post("/api/facilities/search", json={"conditions": conditions})
    assert search.status_code == 200
    facility, = search.json()["results"]
    assert facility["closure"]["status"] == closure_status
    assert facility["time_check"]["status"] == time_status
    assert bool(facility["time_options"]) is has_slots

    comparison = client.post("/api/compare", json={"facility_ids": [facility_id], "conditions": conditions})
    assert comparison.status_code == 200
    fee = comparison.json()["results"][0]["fee"]
    assert fee["payment_due"] == expected_fee
    assert fee["status"] == ("not_eligible" if closure_status == "closed" else "needs_review" if expected_fee is None else "calculated")


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


def test_three_overlapping_rules_stay_conflicted(sqlite_db, tmp_path):
    from app.facility_catalog import read_search_time_policies
    path = tmp_path / "overlap.sqlite3"
    path.write_bytes(sqlite_db.read_bytes())
    with closing(sqlite3.connect(path)) as con, con:
        row = con.execute("SELECT id, facility_id, source_id, effective_from, effective_to, status FROM rule_sets WHERE facility_id='busan_gudeok_stadium_tennis'").fetchone()
        for suffix, starts in (("second", "2026-10-02"), ("third", "2026-10-03")):
            con.execute("INSERT INTO rule_sets VALUES(?,?,?,?,?,?)", (suffix, row[1], row[2], starts, row[4], row[5]))
            con.execute("INSERT INTO time_selection_policies SELECT ?, selection_type, available_start_time, available_end_time, min_minutes, max_minutes, step_minutes, daily_limit_minutes, status, note FROM time_selection_policies WHERE rule_set_id=?", (suffix,row[0]))
    assert read_search_time_policies(path,"2026-11-30")["busan_gudeok_stadium_tennis"] is None
