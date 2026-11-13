import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app import main
from app.facility_catalog import DB_PATH
from app.models import Conditions
from app.sqlite_compare import compare_sqlite


@pytest.fixture(scope="module")
def sqlite_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("sqlite-fee") / "facilities.sqlite3"
    subprocess.run([sys.executable, str(DB_PATH.with_name("build_db.py")), "--db", str(path)], check=True)
    return path


def test_gudeok_quote_includes_mandatory_lighting_and_source(sqlite_db):
    result = compare_sqlite(sqlite_db, "busan_gudeok_stadium_tennis", Conditions(
        sport="tennis", date="2026-11-09", start_time="19:00", end_time="21:00", source="direct",
    ))

    assert result.fee.status == "calculated"
    assert [(item.type, item.amount) for item in result.fee.items] == [("base", 8000), ("lighting", 20000)]
    assert result.fee.payment_due == 28000
    assert result.sources[0].source_id == result.fee.items[0].source_id


def test_sqlite_quote_leaves_unresolved_discount_out_of_total(sqlite_db):
    result = compare_sqlite(sqlite_db, "busan_gudeok_stadium_tennis", Conditions(
        sport="tennis", date="2026-11-09", start_time="19:00", end_time="21:00",
        discount_types=["multi_child"], source="direct",
    ))

    assert result.fee.status == "needs_review"
    assert result.fee.payment_due is None
    assert result.fee.review_items[0].target == "discount"


def test_closed_facility_has_no_slots_or_quote(sqlite_db, tmp_path, monkeypatch):
    db = tmp_path / "closed.sqlite3"
    db.write_bytes(sqlite_db.read_bytes())
    day = "2099-01-01"
    facility_id = "busan_haeundae_arboretum_tennis"
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute("UPDATE rule_sets SET effective_to = ? WHERE facility_id = ?", (day, facility_id))
    monkeypatch.setattr(main, "DB_PATH", db)
    client = TestClient(main.app)
    conditions = {
        "sport": "tennis", "districts": ["해운대구"], "date": day,
        "start_time": "07:00", "end_time": "09:00", "source": "direct",
    }

    search = client.post("/api/facilities/search", json={"conditions": conditions})
    assert search.status_code == 200
    facility, = search.json()["results"]
    assert facility["closure"]["status"] == "closed"
    assert facility["time_check"]["status"] == "not_eligible"
    assert facility["time_options"] is None

    comparison = client.post("/api/compare", json={"facility_ids": [facility_id], "conditions": conditions})
    assert comparison.status_code == 200
    fee = comparison.json()["results"][0]["fee"]
    assert fee["payment_due"] is None
    assert "정기 휴장일" in fee["review_items"][0]["reason"]
