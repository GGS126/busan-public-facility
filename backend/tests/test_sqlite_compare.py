import subprocess
import sys

import pytest

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
