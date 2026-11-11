from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.models import KST, RuleData
from app.options import build_options

client = TestClient(main.app)

SOURCE = {"source_id": "S", "url": "https://example.com", "checked_at": "2026-11-05", "license": "가상"}


def facility(facility_id="F1", district="해운대구", sports=("futsal",), discounts=()) -> dict:
    return {
        "facility_id": facility_id,
        "name": "가상 시설",
        "district": district,
        "source_id": "S",
        "fee_rules": [
            {"rule_id": f"{facility_id}-{sport}", "sport": sport, "type": "base", "effective_from": "2026-01-01", "source_id": "S"}
            for sport in sports
        ],
        "discount_rules": [
            {"rule_id": f"{facility_id}-{code}", "discount_type": code, "effective_from": "2026-01-01", "source_id": "S"}
            for code in discounts
        ],
        "sources": [SOURCE],
    }


LABELS = {
    "sports": {"futsal": "풋살", "tennis": "테니스"},
    "discount_types": {"disabled": "장애인", "multi_child": "다자녀 가정"},
}


def test_options_endpoint_returns_sample_values():
    response = client.get("/api/options")

    assert response.status_code == 200
    assert response.json() == {
        "sports": [{"code": "futsal", "label": "풋살"}],
        "districts": ["해운대구"],
        "discount_types": [
            {"code": "disabled", "label": "장애인"},
            {"code": "multi_child", "label": "다자녀 가정"},
        ],
    }


def test_sqlite_options_match_facility_search(monkeypatch, tmp_path):
    build_script = Path(__file__).resolve().parents[2] / "database" / "build_db.py"
    db = tmp_path / "facilities.sqlite3"
    subprocess.run([sys.executable, str(build_script), "--db", str(db)], check=True)
    monkeypatch.setattr(main, "DB_PATH", db)
    day = (datetime.now(KST).date() + timedelta(days=1)).isoformat()
    conditions = {"sport": "tennis", "date": day, "source": "direct"}
    options = client.get("/api/facilities/options").json()
    assert options["sports"] == [{"code": "tennis", "label": "테니스"}]
    assert options["districts"] == ["사상구", "서구", "해운대구"]

    response = client.post("/api/facilities/search", json={"conditions": conditions | {"districts": ["서구"]}})
    assert response.status_code == 200
    assert [facility["facility_id"] for facility in response.json()["results"]] == ["busan_gudeok_stadium_tennis"]

    response = client.post("/api/facilities/search", json={"conditions": conditions})
    assert response.status_code == 200
    assert len(response.json()["results"]) == 3
    response = client.post("/api/facilities/search", json={"conditions": conditions | {"start_time": "09:00"}})
    assert response.status_code == 400


def test_values_are_merged_without_duplicates_in_stable_order():
    data = RuleData(
        labels=LABELS,
        facilities=[
            facility("F1", "해운대구", ["tennis", "futsal"], ["multi_child"]),
            facility("F2", "동래구", ["futsal"], ["disabled", "multi_child"]),
        ],
    )
    options = build_options(data)

    assert [sport.code for sport in options.sports] == ["futsal", "tennis"]
    assert options.districts == ["동래구", "해운대구"]
    assert [item.code for item in options.discount_types] == ["disabled", "multi_child"]


def test_labels_for_unused_codes_are_not_offered():
    options = build_options(RuleData(labels=LABELS, facilities=[facility()]))

    assert [sport.code for sport in options.sports] == ["futsal"]
    assert options.discount_types == []


def test_facility_without_district_is_skipped():
    options = build_options(RuleData(labels=LABELS, facilities=[facility(district=None)]))

    assert options.districts == []


def test_no_facilities_gives_empty_options():
    options = build_options(RuleData(labels=LABELS, facilities=[]))

    assert (options.sports, options.districts, options.discount_types) == ([], [], [])


@pytest.mark.parametrize(
    "kwargs",
    [{"sports": ["unknown"]}, {"discounts": ["unknown"]}],
)
def test_code_without_label_is_rejected_on_load(kwargs):
    with pytest.raises(ValidationError, match="unknown"):
        RuleData(labels=LABELS, facilities=[facility(**kwargs)])


def test_sport_with_only_lighting_rule_is_not_offered():
    data = facility(sports=())
    data["fee_rules"] = [
        {"rule_id": "L", "sport": "tennis", "type": "lighting", "effective_from": "2026-01-01", "source_id": "S"}
    ]
    options = build_options(RuleData(labels=LABELS, facilities=[data]))

    assert options.sports == []


def test_every_offered_option_can_be_used_in_compare():
    options = client.get("/api/options").json()
    day = (datetime.now(KST).date() + timedelta(days=1)).isoformat()

    for sport in options["sports"]:
        for discount in options["discount_types"]:
            response = client.post(
                "/api/compare",
                json={
                    "facility_ids": ["F001"],
                    "conditions": {
                        "sport": sport["code"],
                        "districts": options["districts"],
                        "date": day,
                        "start_time": "10:00",
                        "end_time": "12:00",
                        "discount_types": [discount["code"]],
                        "source": "direct",
                    },
                },
            )
            assert response.status_code == 200
            assert response.json()["results"][0]["fee"]["status"] == "calculated"
