import logging
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import main
from app.models import KST, Option

client = TestClient(main.app)


def next_saturday() -> str:
    today = datetime.now(KST).date()
    return (today + timedelta(days=(5 - today.weekday()) % 7 or 7)).isoformat()


def payload(**overrides) -> dict:
    conditions = {
        "sport": "futsal",
        "districts": ["해운대구"],
        "date": next_saturday(),
        "start_time": "18:00",
        "end_time": "20:00",
        "discount_types": ["multi_child"],
        "source": "direct",
    }
    return {"facility_ids": ["F001"], "conditions": conditions | overrides}


SOURCES = [
    {"source_id": "S-01", "url": "https://example.com/fee-rules", "checked_at": "2026-11-05", "license": "가상 데이터"},
    {"source_id": "S-02", "url": "https://example.com/discount-rules", "checked_at": "2026-11-05", "license": "가상 데이터"},
    {"source_id": "S-03", "url": "https://example.com/booking-rules", "checked_at": "2026-11-05", "license": "가상 데이터"},
]
TERMS = {
    "booking_open": "이용일 30일 전 09:00부터",
    "cancel_deadline": "이용일 3일 전까지",
    "refund": "기한 내 취소 시 전액 환불",
    "source_id": "S-03",
}


def test_calculated_response_matches_api_draft():
    response = client.post("/api/compare", json=payload())

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {
                "facility_id": "F001",
                "facility_name": "예시 체육관",
                "fee": {
                    "status": "calculated",
                    "items": [
                        {"type": "base", "amount": 40000, "rule_id": "R-F001-01", "source_id": "S-01"},
                        {"type": "lighting", "amount": 10000, "rule_id": "R-F001-02", "source_id": "S-01"},
                        {
                            "type": "discount",
                            "amount": -20000,
                            "rule_id": "R-F001-05",
                            "source_id": "S-02",
                            "method": "prepay_refund",
                        },
                    ],
                    "total": 30000,
                    "payment_due": 50000,
                    "expected_refund": 20000,
                    "net_cost_after_refund": 30000,
                    "review_items": [],
                },
                "terms": TERMS,
                "checklist": ["다자녀 가정 확인 서류"],
                "checklist_review_items": [],
                "sources": SOURCES,
            }
        ]
    }


def test_needs_review_response_has_null_totals():
    response = client.post("/api/compare", json=payload(discount_types=["multi_child", "disabled"]))

    assert response.status_code == 200
    result = response.json()["results"][0]
    fee = result["fee"]
    assert fee["status"] == "needs_review"
    assert [fee[key] for key in ("total", "payment_due", "expected_refund", "net_cost_after_refund")] == [None] * 4
    assert [item["type"] for item in fee["items"]] == ["base", "lighting"]
    assert fee["review_items"][0]["code"] == "rule_missing"
    assert fee["review_items"][0]["target"] == "discount"
    assert fee["review_items"][0]["source_id"] == "S-02"
    assert result["checklist"] == ["다자녀 가정 확인 서류", "장애인 증명 서류"]


def test_booking_can_end_at_midnight():
    response = client.post("/api/compare", json=payload(start_time="22:00", end_time="24:00", discount_types=[]))

    assert response.status_code == 200
    assert response.json()["results"][0]["fee"]["total"] == 40000


def test_headcount_is_optional_and_accepted():
    assert client.post("/api/compare", json=payload(headcount=10)).status_code == 200


def test_value_outside_options_is_rejected():
    response = client.post("/api/compare", json=payload(sport="nope", discount_types=["multi_child", "nope"]))

    assert fields_of(response) == {
        "conditions.sport": "invalid_option",
        "conditions.discount_types": "invalid_option",
    }
    assert "nope" not in response.text


def test_sport_offered_elsewhere_returns_review_for_this_facility(monkeypatch):
    options = main.available_options.model_copy(
        update={"sports": [*main.available_options.sports, Option(code="tennis", label="테니스")]}
    )
    monkeypatch.setattr(main, "available_options", options)
    response = client.post("/api/compare", json=payload(sport="tennis", discount_types=[]))

    fee = response.json()["results"][0]["fee"]
    assert response.status_code == 200
    assert fee["status"] == "needs_review"
    assert fee["items"] == []
    assert fee["review_items"][0]["source_id"] == "S-01"


def test_unknown_facility_returns_404():
    body = payload()
    body["facility_ids"] = ["F001", "NOPE"]
    response = client.post("/api/compare", json=body)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "facility_not_found"


def fields_of(response) -> dict[str, str]:
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    return {field["field"]: field["code"] for field in error["fields"]}


def test_invalid_time_range_reports_field():
    response = client.post("/api/compare", json=payload(start_time="20:00", end_time="18:00"))

    assert fields_of(response) == {"conditions.end_time": "invalid_time_range"}


def test_equal_times_rejected():
    response = client.post("/api/compare", json=payload(start_time="18:00", end_time="18:00"))

    assert fields_of(response) == {"conditions.end_time": "invalid_time_range"}


def test_past_date_reports_field():
    response = client.post("/api/compare", json=payload(date="2020-01-01"))

    assert fields_of(response) == {"conditions.date": "past_date"}


def test_today_is_allowed():
    today = datetime.now(KST).date().isoformat()

    assert client.post("/api/compare", json=payload(date=today)).status_code == 200


def test_missing_required_fields_reported_together():
    response = client.post("/api/compare", json={"conditions": {"source": "direct"}})

    assert fields_of(response) == {
        "facility_ids": "required",
        "conditions.sport": "required",
        "conditions.date": "required",
        "conditions.start_time": "required",
        "conditions.end_time": "required",
    }


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"date": "2026-13-40"}, "conditions.date"),
        ({"start_time": "25:00"}, "conditions.start_time"),
        ({"end_time": "24:01"}, "conditions.end_time"),
        ({"start_time": "24:00"}, "conditions.start_time"),
        ({"start_time": "18:00:00"}, "conditions.start_time"),
        ({"headcount": 0}, "conditions.headcount"),
        ({"source": "unknown"}, "conditions.source"),
    ],
)
def test_invalid_values_report_field(overrides, field):
    assert fields_of(client.post("/api/compare", json=payload(**overrides))) == {field: "invalid_value"}


def test_empty_facility_list_rejected():
    body = payload()
    body["facility_ids"] = []

    assert fields_of(client.post("/api/compare", json=body)) == {"facility_ids": "invalid_value"}


def test_unknown_path_uses_common_error_format():
    response = client.get("/api/unknown")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "요청한 경로를 찾을 수 없습니다."}
    }


def test_unsupported_method_uses_common_error_format_and_keeps_allow_header():
    response = client.get("/api/compare")

    assert response.status_code == 405
    assert response.json() == {
        "error": {"code": "method_not_allowed", "message": "지원하지 않는 요청 방식입니다."}
    }
    assert response.headers["allow"] == "POST"


def test_broken_json_reports_body():
    response = client.post("/api/compare", content="{broken", headers={"content-type": "application/json"})

    assert fields_of(response) == {"body": "invalid_value"}


def test_missing_body_reports_body():
    assert fields_of(client.post("/api/compare")) == {"body": "required"}


def test_validation_error_does_not_echo_input():
    response = client.post("/api/compare", json=payload(start_time="주민번호 900101-1234567"))

    assert "900101" not in response.text


def test_server_error_hides_details_and_input(monkeypatch, caplog):
    def fail(*_):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(main, "compare_facility", fail)
    safe_client = TestClient(main.app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = safe_client.post("/api/compare", json=payload())

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret detail" not in response.text
    assert "multi_child" not in caplog.text
    assert "secret detail" not in caplog.text
