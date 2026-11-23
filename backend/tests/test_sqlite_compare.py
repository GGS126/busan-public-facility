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

    assert result.fee.status == "needs_review"
    assert [(item.type, item.amount) for item in result.fee.items] == [("base", 8000), ("lighting", 20000)]
    assert result.fee.payment_due is None
    assert result.fee.online_prepay == 8000
    assert result.fee.payment_unverified == 20000
    assert result.fee.items[1].rule_id != result.fee.items[0].rule_id
    assert result.sources[0].source_id == result.fee.items[0].source_id


def test_sqlite_quote_leaves_unresolved_discount_out_of_total(sqlite_db, gudeok):
    result = compare_sqlite(sqlite_db, gudeok, Conditions(
        sport="tennis", date="2026-11-09", start_time="19:00", end_time="21:00",
        discount_types=["multi_child"], source="direct",
    ))

    assert result.fee.status == "needs_review"
    assert result.fee.payment_due is None
    assert any(item.target == "discount" for item in result.fee.review_items)


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


def test_three_overlapping_rules_stay_conflicted(sqlite_db, tmp_path, monkeypatch):
    from app.facility_catalog import read_search_time_policies
    path = tmp_path / "overlap.sqlite3"
    path.write_bytes(sqlite_db.read_bytes())
    with closing(sqlite3.connect(path)) as con, con:
        row = con.execute("SELECT id, facility_id, source_id, effective_from, effective_to, status FROM rule_sets WHERE facility_id='busan_gudeok_stadium_tennis'").fetchone()
        for suffix, starts in (("second", "2026-10-02"), ("third", "2026-10-03")):
            con.execute("INSERT INTO rule_sets VALUES(?,?,?,?,?,?)", (suffix, row[1], row[2], starts, row[4], row[5]))
            con.execute("INSERT INTO time_selection_policies SELECT ?, selection_type, available_start_time, available_end_time, min_minutes, max_minutes, step_minutes, daily_limit_minutes, status, note FROM time_selection_policies WHERE rule_set_id=?", (suffix,row[0]))
    assert read_search_time_policies(path,"2026-11-30")["busan_gudeok_stadium_tennis"] is None
    monkeypatch.setattr(main, "DB_PATH", path)
    response = TestClient(main.app).post("/api/facilities/search", json={"conditions": {
        "sport": "tennis", "districts": ["서구"], "date": "2026-11-30", "source": "direct",
        "start_time": "10:00", "end_time": "12:00",
    }})
    assert response.status_code == 200
    result, = response.json()["results"]
    assert result["slot_status"] == "rule_conflict"
    assert result["time_check"] == {"status": "unknown", "code": "rule_conflict"}
    assert result["time_options"] is None



def test_sqlite_compare_uses_one_read_connection(sqlite_db, gudeok):
    from unittest.mock import patch
    query = load_query_api()
    from app.facility_catalog import facility_closures
    from datetime import date
    closures = facility_closures(sqlite_db, date(2026, 11, 30))
    with patch.object(query.sqlite3, "connect", wraps=query.sqlite3.connect) as connect:
        result = compare_sqlite(sqlite_db, gudeok, Conditions(
            sport="tennis", date="2026-11-30", start_time="10:00", end_time="12:00", source="direct",
        ), closures=closures)
    assert result.fee.status == "calculated"
    assert connect.call_count == 1


def test_closed_day_cannot_be_quoted(sqlite_db):
    facilities, _ = read_catalog(sqlite_db)
    facility = next(item for item in facilities if item["facility_id"] == "busan_samrak_ecopark_tennis")
    result = compare_sqlite(sqlite_db, facility, Conditions(
        sport="tennis", date="2027-02-07", start_time="10:00", end_time="12:00", source="direct",
    ))
    assert result.fee.status == "not_eligible"
    assert result.fee.payment_due is None


def test_all_catalog_discount_codes_are_accepted_by_compare(sqlite_db, gudeok, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", sqlite_db)
    options = TestClient(main.app).get("/api/facilities/options").json()
    day = (datetime.now(KST).date() + timedelta(days=1)).isoformat()
    for discount in options["discount_types"]:
        response = TestClient(main.app).post("/api/compare", json={
            "facility_ids": [gudeok["facility_id"]],
            "conditions": {"sport": "tennis", "date": day, "start_time": "10:00", "end_time": "12:00",
                           "source": "direct", "discount_types": [discount["code"]]},
        })
        assert response.status_code == 200, discount["code"]
        assert response.json()["results"][0]["fee"]["status"] == "needs_review"


def test_search_snapshot_uses_one_version_and_connection(sqlite_db, tmp_path, monkeypatch):
    from datetime import date
    from unittest.mock import patch
    from app import facility_catalog
    path = tmp_path / "snapshot.sqlite3"
    path.write_bytes(sqlite_db.read_bytes())
    query = load_query_api()
    with patch.object(facility_catalog, "_file_version", wraps=facility_catalog._file_version) as version:
        with patch.object(query.sqlite3, "connect", wraps=query.sqlite3.connect) as connect:
            snapshot = facility_catalog.read_search_snapshot(path, date(2026, 11, 30))
    assert snapshot[0]
    assert connect.call_count == 1
    assert version.call_count == 1


def test_search_keeps_original_snapshot_during_db_update(sqlite_db, tmp_path, monkeypatch):
    from datetime import date
    from app.facility_catalog import read_search_snapshot
    path = tmp_path / "concurrent.sqlite3"
    path.write_bytes(sqlite_db.read_bytes())
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
    query = load_query_api()
    original = query.facilities
    def read_then_update(connection):
        rows = original(connection)
        with closing(sqlite3.connect(path)) as writer, writer:
            writer.execute("UPDATE time_selection_policies SET max_minutes=1")
        return rows
    monkeypatch.setattr(query, "facilities", read_then_update)
    _, _, policies, _, _, _ = read_search_snapshot(path, date(2026, 11, 30))
    assert policies["busan_gudeok_stadium_tennis"]["max_minutes"] == 120
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT max_minutes FROM time_selection_policies LIMIT 1").fetchone()[0] == 1
