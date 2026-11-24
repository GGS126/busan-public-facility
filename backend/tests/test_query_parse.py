import json
from collections import deque
from datetime import date, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.gemini_extractor import GeminiExtractor, GeminiHTTPError, GeminiResponseError
from app.query_parser import parse_query

TODAY = date(2026, 11, 9)


@pytest.fixture(autouse=True)
def reset_gemini_state(monkeypatch):
    monkeypatch.setattr(main, "gemini_calls", deque())
    main.gemini_provider.cache_clear()
    yield
    main.gemini_provider.cache_clear()


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
    ("date", None), ("date", "2026-11-08"), ("date", "2099-11-10"), ("headcount", 0),
    ("end_time", "19:00"), ("end_time", "18:00"), ("discount_types", None), ("districts", "해운대구"),
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


@pytest.mark.parametrize(("model", "level"), [
    ("gemini-3.5-flash-lite", "minimal"),
    ("gemini-3.1-pro-preview", "low"),
])
def test_gemini_leaves_code_validation_to_parser(monkeypatch, model, level):
    connection = Mock()
    connection.getresponse.return_value.status = 200
    connection.getresponse.return_value.read.return_value = json.dumps({"candidates": [{
        "finishReason": "STOP",
        "content": {"parts": [{"text": json.dumps(CONDITIONS | {"sport": "unknown"})}]},
    }]}).encode()
    monkeypatch.setattr("app.gemini_extractor.http.client.HTTPSConnection", Mock(return_value=connection))
    extractor = GeminiExtractor("test-key", sport_codes={"futsal": "풋살"},
                               discount_codes={}, districts=["해운대구"], model=model)
    assert extractor("풋살", TODAY)["sport"] == "unknown"
    payload = json.loads(connection.request.call_args.args[2])
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": level}
    assert payload["generationConfig"]["maxOutputTokens"] == (4096 if level == "low" else 1024)


def test_unconfigured_gemini_3_model_is_rejected():
    with pytest.raises(ValueError, match="invalid_model_configuration"):
        GeminiExtractor("test-key", sport_codes={}, discount_codes={}, districts=[], model="gemini-3.99-flash")


@pytest.mark.parametrize(("errors", "diagnostic"), [
    ([GeminiHTTPError(429)], "status=429"),
    ([TimeoutError("private details")] * 2, "type=TimeoutError"),
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


def test_api_keeps_partial_conditions_in_response(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "missing.sqlite3")
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


@pytest.mark.parametrize("phone", [
    "051-123-4567", "02-1234-5678", "0311234567", "+82-51-123-4567",
    "070-1234-5678", "0505-123-4567", "080-123-4567", "문의/02-1234-5678",
])
def test_landline_is_blocked_before_extraction(phone):
    extract = Mock()
    result = parse_query(f"풋살 문의 {phone}", today=TODAY, extract=extract)
    assert result["status"] == "llm_failed"
    extract.assert_not_called()


def test_input_limit_checks_normalized_characters():
    extract = Mock(return_value=CONDITIONS)
    result = parse_query("㎞" * 500, today=TODAY, extract=extract)
    assert result["status"] == "llm_failed"
    extract.assert_not_called()


def test_long_raw_query_returns_llm_failed():
    response = TestClient(main.app).post("/api/query/parse", json={"query": "가" * 501})
    assert response.status_code == 200
    assert response.json()["status"] == "llm_failed"
    assert "500자" in response.json()["message"]


@pytest.mark.parametrize("query", [
    "내일 1800-2000 풋살", "내일 1600 1800 테니스", "11월 20일 1500-1700 4명",
    "11.02 1800-2000 풋살", "11/02 1900 2100 테니스", "2026.11.02 1800-2000", "2026-11-02 1800-2000 풋살", "11-02 1800-2000", "11월 02 1800-2000",
])
def test_compact_time_range_reaches_extractor(query):
    extract = Mock(return_value=CONDITIONS)
    assert parse_query(query, today=TODAY, extract=extract)["status"] == "ok"
    extract.assert_called_once_with(query, TODAY)


@pytest.mark.parametrize("model", ["", "   "])
def test_empty_model_uses_default(monkeypatch, model):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", model)
    factory = Mock(return_value=Mock(return_value=CONDITIONS))
    monkeypatch.setattr(main, "GeminiExtractor", factory)
    TestClient(main.app).post("/api/query/parse", json={"query": "풋살"})
    assert factory.call_args.kwargs["model"] == "gemini-3.5-flash-lite"


@pytest.mark.parametrize("code", [
    "output_token_limit", "generation_did_not_finish", "candidate_missing_or_unexpected_count",
    "unsupported_sport_code",
])
def test_non_format_errors_are_not_retried(monkeypatch, code):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    provider = Mock(side_effect=GeminiResponseError(code))
    monkeypatch.setattr(main, "GeminiExtractor", Mock(return_value=provider))
    response = TestClient(main.app).post("/api/query/parse", json={"query": "풋살"})
    assert response.json()["status"] == "llm_failed"
    provider.assert_called_once()


@pytest.mark.parametrize("districts", [None, []])
def test_unspecified_district_means_all_busan(districts):
    extract = Mock(return_value=CONDITIONS | {"districts": districts})
    result = parse_query("내일 풋살", today=TODAY, extract=extract)
    assert result["status"] == "ok"
    assert result["conditions"]["districts"] == []


def test_retry_counts_towards_call_limit(monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main, "monotonic", lambda: 100)
    main.gemini_calls.extend([100] * 14)
    provider = Mock(side_effect=GeminiResponseError("invalid_output_json"))
    monkeypatch.setattr(main, "GeminiExtractor", Mock(return_value=provider))
    response = TestClient(main.app).post("/api/query/parse", json={"query": "풋살"})
    assert response.json()["status"] == "llm_failed"
    provider.assert_called_once()
    assert "code=rate_limited limit=per_minute" in caplog.text


def test_concurrent_call_limit_is_logged(monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main, "gemini_slots", Mock(**{"acquire.return_value": False}))
    provider = Mock()
    monkeypatch.setattr(main, "GeminiExtractor", Mock(return_value=provider))
    response = TestClient(main.app).post("/api/query/parse", json={"query": "풋살"})
    assert response.json()["status"] == "llm_failed"
    provider.assert_not_called()
    assert "code=rate_limited limit=concurrency" in caplog.text


def test_dns_block_does_not_block_request_deadline(monkeypatch):
    from threading import Event
    from time import monotonic
    release = Event()
    connection = Mock()
    connection.sock = None
    connection.request.side_effect = lambda *args: release.wait(2)
    monkeypatch.setattr("app.gemini_extractor.http.client.HTTPSConnection", Mock(return_value=connection))
    extractor = GeminiExtractor("test-key", sport_codes={}, discount_codes={}, districts=[])
    started = monotonic()
    try:
        with pytest.raises(TimeoutError, match="request_deadline"):
            extractor("test", TODAY, deadline=started + 0.05)
        assert monotonic() - started < 1
    finally:
        release.set()


@pytest.mark.parametrize(("field", "value"), [
    ("sport", "unknown"), ("districts", ["unknown"]), ("discount_types", ["unknown"]),
    ("sport", []), ("districts", [123]), ("discount_types", "disabled"),
])
def test_parser_validates_catalog_codes_in_one_place(field, value):
    from app.models import Option, OptionsResponse
    catalog = OptionsResponse(sports=[Option(code="futsal", label="Futsal")],
                              districts=["해운대구"], discount_types=[])
    result = parse_query("test", today=TODAY, extract=Mock(return_value=CONDITIONS | {field: value}),
                         catalog=catalog)
    assert result["status"] == "need_more"
    assert result["missing_fields"] == [field]
    assert field not in result["conditions"]
    assert result["conditions"]["date"] == CONDITIONS["date"]


def test_catalog_key_is_cached_per_instance_and_not_serialized():
    from app.models import OptionsResponse
    catalog = OptionsResponse(sports=[], districts=[], discount_types=[])
    assert catalog.extraction_key is catalog.extraction_key
    replacement = OptionsResponse(sports=[], districts=["new"], discount_types=[])
    assert replacement.extraction_key != catalog.extraction_key
    assert "extraction_key" not in catalog.model_dump()


def test_known_busan_district_without_facilities_is_preserved():
    from app.models import Option, OptionsResponse
    catalog = OptionsResponse(sports=[Option(code="futsal", label="Futsal")],
                              districts=["해운대구"], discount_types=[])
    provider = GeminiExtractor("test-key", sport_codes={"futsal": "Futsal"}, discount_codes={},
                               districts=list(catalog.extraction_key[2]))
    assert provider.properties["districts"]["items"]["enum"] == list(catalog.extraction_key[2])
    result = parse_query("test", today=TODAY, extract=Mock(return_value=CONDITIONS | {"districts": ["동구"]}),
                         catalog=catalog)
    assert result["status"] == "ok"
    assert result["conditions"]["districts"] == ["동구"]
