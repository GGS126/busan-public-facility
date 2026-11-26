"""실제 팀 DB(SQLite)를 읽은 서비스의 비교·선택지·상세 API."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from test_sqlite_rules import build_database

from app import main
from app.models import KST
from app.options import build_options

LUNAR_NEW_YEAR = "2027-02-07"  # holidays_kr.json의 '설날'


def next_weekday() -> str:
    today = datetime.now(KST).date()
    return (today + timedelta(days=7 - today.weekday())).isoformat()  # 다음 주 월요일

@pytest.fixture(scope="module")
def sqlite_path(tmp_path_factory):
    return build_database(tmp_path_factory.mktemp("db"))


@pytest.fixture
def client(sqlite_path, monkeypatch):
    data = main.load_service_data("sqlite", sqlite_path)
    monkeypatch.setattr(main, "DB_PATH", sqlite_path)
    monkeypatch.setattr(main, "facilities", {facility.facility_id: facility for facility in data.facilities})
    monkeypatch.setattr(main, "available_options", build_options(data))
    return TestClient(main.app)


def compare(client, facility_id, sport, day, start, end):
    body = {
        "facility_ids": [facility_id],
        "conditions": {"sport": sport, "date": day, "start_time": start, "end_time": end, "source": "direct"},
    }
    response = client.post("/api/compare", json=body)
    assert response.status_code == 200, response.json()
    return response.json()["results"][0]


def test_missing_database_stops_with_build_instructions(tmp_path):
    with pytest.raises(RuntimeError, match="build_db.py"):
        main.load_service_data("sqlite", tmp_path / "none.sqlite3")


def test_unknown_data_source_is_rejected():
    with pytest.raises(RuntimeError, match="RULE_DATA_SOURCE"):
        main.load_service_data("json")


def test_options_come_from_database(client):
    body = client.get("/api/options").json()
    assert {sport["code"] for sport in body["sports"]} == {"tennis", "soccer"}
    # 가상 데이터의 시설은 섞이지 않는다.
    assert client.get("/api/facilities/F001").status_code == 404


def test_facility_detail_reads_database(client):
    response = client.get("/api/facilities/busan_gudeok_stadium_tennis", params={"date": next_weekday()})

    assert response.status_code == 200
    assert response.json()["facility_id"] == "busan_gudeok_stadium_tennis"


def test_compare_calculates_database_facility(client):
    result = compare(client, "busan_gudeok_stadium_tennis", "tennis", next_weekday(), "10:00", "12:00")

    assert result["fee"]["status"] == "calculated", result["fee"]["review_items"]
    assert result["fee"]["total"] == 8000
    assert result["sources"]


def test_compare_blocks_regular_closure_before_fee(client):
    result = compare(client, "busan_hwamyeong_ecopark_tennis", "tennis", LUNAR_NEW_YEAR, "10:00", "12:00")
    fee = result["fee"]
    assert fee["status"] == "not_eligible"
    assert fee["items"] == [] and fee["total"] is None
    assert [(item["code"], item["target"]) for item in fee["review_items"]] == [("facility_closed", "time")]
    assert any(source["source_id"] == fee["review_items"][0]["source_id"] for source in result["sources"])


def test_day_after_lunar_new_year_is_not_closed(client):
    day = (date.fromisoformat(LUNAR_NEW_YEAR) + timedelta(days=1)).isoformat()
    result = compare(client, "busan_hwamyeong_ecopark_tennis", "tennis", day, "10:00", "12:00")

    assert all(item["code"] != "facility_closed" for item in result["fee"]["review_items"])


def test_search_options_compare_and_detail_share_loaded_sqlite(client):
    assert client.get("/api/facilities/options").json() == client.get("/api/options").json()
    conditions = {"sport": "tennis", "date": "2026-12-01", "start_time": "10:00", "end_time": "12:00", "source": "direct"}
    search = client.post("/api/facilities/search", json={"conditions": conditions})
    assert search.status_code == 200
    chosen = next(item for item in search.json()["results"] if item["facility_id"] == "busan_gudeok_stadium_tennis")
    response = client.post("/api/compare", json={"facility_ids": [chosen["facility_id"]], "conditions": conditions})
    assert response.status_code == 200
    assert response.json()["results"][0]["fee"]["total"] == 8000
    assert client.get("/api/facilities/" + chosen["facility_id"], params={"date": conditions["date"]}).status_code == 200


def test_terms_list_every_refund_reason(client):
    result = compare(client, "busan_samrak_ecopark_tennis", "tennis", next_weekday(), "08:00", "10:00")
    terms = result["terms"]
    assert terms["refund"].startswith("3일 전까지 취소 100%")
    notes = terms["refund_notes"]
    # 사용자 취소 4단계 다음에 우천·불가항력 환불이 온다.
    assert notes[1].startswith("2일 전 취소 90%: ") and "반환신청서" in notes[1]
    assert any(note.startswith("우천으로 이용하지 못한 경우 100%") for note in notes)
    assert any(note.startswith("천재지변·부산시 행사 등으로 이용할 수 없는 경우 100%") for note in notes)


def test_discount_checklist_includes_application_deadline(client):
    body = {
        "facility_ids": ["busan_samrak_ecopark_tennis"],
        "conditions": {
            "sport": "tennis", "date": next_weekday(), "start_time": "08:00", "end_time": "10:00",
            "headcount": 4, "discounts": [{"type": "disabled", "count": 1}], "source": "direct",
        },
    }
    checklist = client.post("/api/compare", json=body).json()["results"][0]["checklist"]
    deadline = [
        item for item in checklist
        if item.startswith("감면 신청 기한: 경기장 이용시간 전 반환신청 게시판 접수")
    ]
    assert len(deadline) == 1


def test_unknown_refund_reason_is_rejected_on_load():
    from app.repository import _refund_label

    with pytest.raises(ValueError, match="환불 사유"):
        _refund_label({"reason": "rain_during_use", "rate_percent": 100, "days_before_min": None, "days_before_max": None})
