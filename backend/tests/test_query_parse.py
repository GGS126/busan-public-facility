import json
from datetime import date, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.gemini_extractor import GeminiExtractor, GeminiHTTPError, GeminiResponseError
from app.query_parser import parse_query

TODAY = date(2026, 11, 9)
CONDITIONS = {
    "sport": "futsal",
    "districts": ["해운대구"],
    "date": "2026-11-10",
    "start_time": "19:00",
    "end_time": "21:00",
    "headcount": None,
    "discount_types": [],
}


def test_valid_conditions():
    result = parse_query("내일 저녁 풋살", today=TODAY, extract=Mock(return_value=CONDITIONS))
    assert result["status"] == "ok"
    assert result["conditions"]["discount_types"] == []
    assert result["conditions"]["source"] == "llm"


@pytest.mark.parametrize(("field", "value"), [
    ("date", None), ("date", "2026-11-08"), ("headcount", 0),
    ("end_time", "19:00"), ("end_time", "18:00"), ("discount_types", None), ("districts", []),
])
def test_invalid_field_preserves_other_conditions(field, value):
    extract = Mock(return_value=CONDITIONS | {field: value})
    result = parse_query("풋살", today=TODAY, extract=extract)
    assert result["status"] == "need_more"
    assert result["missing_fields"] == [field]
    assert result["questions"][field]
    assert field not in result["conditions"]
    assert result["conditions"]["sport"] == "futsal"


def test_personal_information_is_not_sent_to_provider():
    extract = Mock()
    result = parse_query("풋살 문의 010-1234-5678", today=TODAY, extract=extract)
    assert result["status"] == "llm_failed"
    extract.assert_not_called()


def test_provider_exception_returns_failed_without_details():
    extract = Mock(side_effect=RuntimeError("private details"))
    result = parse_query("풋살", today=TODAY, extract=extract)
    assert result["status"] == "llm_failed"
    assert "private details" not in str(result)


def test_gemini_rejects_unknown_sport(monkeypatch):
    connection = Mock()
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.read.return_value = json.dumps({"candidates": [{
        "finishReason": "STOP",
        "content": {"parts": [{"text": json.dumps(CONDITIONS | {"sport": "unknown"})}]},
    }]}).encode()
    monkeypatch.setattr("app.gemini_extractor.http.client.HTTPSConnection", Mock(return_value=connection))
    extractor = GeminiExtractor("test-key", sport_codes={"futsal": "풋살"},
                               discount_codes={}, districts=["해운대구"])
    with pytest.raises(GeminiResponseError, match="^unsupported_sport_code$"):
        extractor("풋살", TODAY)


@pytest.mark.parametrize(("errors", "diagnostic"), [
    ([GeminiHTTPError(429)], "status=429"),
    ([TimeoutError("private details")], "type=TimeoutError"),
    ([GeminiResponseError("invalid_output_json")] * 2, "code=invalid_output_json"),
])
def test_api_logs_safe_diagnostics(monkeypatch, caplog, errors, diagnostic):
    monkeypatch.setenv("GEMINI_API_KEY", "private-key")
    provider = Mock(side_effect=errors)
    monkeypatch.setattr(main, "GeminiExtractor", Mock(return_value=provider))
    response = TestClient(main.app).post("/api/query/parse", json={"query": "private-query"})
    assert response.status_code == 200
    assert response.json()["status"] == "llm_failed"
    assert provider.call_count == len(errors)
    assert diagnostic in caplog.text
    assert all(secret not in caplog.text for secret in ("private details", "private-key", "private-query"))


def test_missing_api_key_is_logged(monkeypatch, caplog):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = TestClient(main.app).post("/api/query/parse", json={"query": "풋살"})
    assert response.json()["status"] == "llm_failed"
    assert "code=missing_api_key" in caplog.text


def test_api_keeps_partial_conditions_in_response(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    tomorrow = (datetime.now(main.KST).date() + timedelta(days=1)).isoformat()
    provider = Mock(return_value=CONDITIONS | {"date": tomorrow, "discount_types": None})
    monkeypatch.setattr(main, "GeminiExtractor", Mock(return_value=provider))

    response = TestClient(main.app).post("/api/query/parse", json={"query": "내일 풋살"})

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "need_more"
    assert result["conditions"]["date"] == tomorrow
    assert "discount_types" not in result["conditions"]
    assert result["missing_fields"] == ["discount_types"]
