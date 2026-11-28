"""Extracted conditions must survive real SQLite search/compare; no model calls."""
from collections import deque
from datetime import datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from test_sqlite_rules import build_database

from app import main, models
from app.models import KST
from app.options import build_options

TODAY = datetime(2026, 11, 9, tzinfo=KST)
USE_DATE = "2026-11-16"  # Non-holiday Monday within the seeded winter rules.


@pytest.fixture
def client(tmp_path, monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return TODAY.astimezone(tz) if tz else TODAY.replace(tzinfo=None)

    monkeypatch.setattr(main, "datetime", FixedDateTime)
    monkeypatch.setattr(models, "datetime", FixedDateTime)
    path = build_database(tmp_path)
    data = main.load_service_data("sqlite", path)
    monkeypatch.setattr(main, "DB_PATH", path)
    monkeypatch.setattr(main, "facilities", {item.facility_id: item for item in data.facilities})
    monkeypatch.setattr(main, "available_options", build_options(data))
    monkeypatch.setattr(main, "gemini_calls", deque())
    main.gemini_provider.cache_clear()
    yield TestClient(main.app)
    main.gemini_provider.cache_clear()


def conditions(**changes):
    return {"sport": "tennis", "districts": ["사상구"], "date": USE_DATE,
            "start_time": "08:00", "end_time": "10:00", "headcount": 4, "discount_types": [], **changes}


def extract(client, monkeypatch, raw):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main, "gemini_provider", Mock(return_value=Mock(return_value=raw)))
    response = client.post("/api/query/parse", json={"query": "다음 주 월요일 사상구 테니스 오전 8시부터 10시 4명"})
    assert response.status_code == 200
    return response.json()


def test_extracted_times_and_fee_match_direct_input(client, monkeypatch):
    parsed = extract(client, monkeypatch, conditions())
    assert parsed["status"] == "ok"
    confirmed = parsed["conditions"]
    search = client.post("/api/facilities/search", json={"conditions": confirmed})
    assert search.status_code == 200
    chosen = next(item for item in search.json()["results"]
                  if item["facility_id"] == "busan_samrak_ecopark_tennis")
    assert chosen["time_check"]["status"] == "eligible"
    assert {"start_time": confirmed["start_time"], "end_time": confirmed["end_time"]} in chosen["time_options"]["slots"]
    body = {"facility_ids": [chosen["facility_id"]], "conditions": confirmed}
    ai = client.post("/api/compare", json=body)
    body["conditions"] = {**confirmed, "source": "direct"}
    direct = client.post("/api/compare", json=body)
    assert ai.status_code == direct.status_code == 200
    assert ai.json() == direct.json()
    fee = ai.json()["results"][0]["fee"]
    assert fee["status"] == "calculated" and fee["total"] == 6000


def test_unregistered_district_stays_selected_and_returns_alternatives(client, monkeypatch):
    parsed = extract(client, monkeypatch, conditions(districts=["동래구"]))
    assert parsed["conditions"]["districts"] == ["동래구"]
    response = client.post("/api/facilities/search", json={"conditions": parsed["conditions"]})
    assert response.status_code == 200
    assert response.json()["results"] == []
    assert "사상구" in response.json()["alternatives"]["districts"]


def test_missing_time_can_be_confirmed_manually(client, monkeypatch):
    parsed = extract(client, monkeypatch, conditions(end_time=None))
    assert parsed["status"] == "need_more" and "end_time" in parsed["missing_fields"]
    assert "end_time" not in parsed["conditions"]
    confirmed = {**parsed["conditions"], "end_time": "10:00", "source": "direct"}
    response = client.post("/api/facilities/search", json={"conditions": confirmed})
    assert response.status_code == 200 and response.json()["results"]


def test_model_failure_does_not_block_direct_search(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = client.post("/api/query/parse", json={"query": "사상구 테니스"})
    assert response.json()["status"] == "llm_failed"
    direct = {**conditions(), "source": "direct"}
    search = client.post("/api/facilities/search", json={"conditions": direct})
    assert search.status_code == 200 and search.json()["results"]
