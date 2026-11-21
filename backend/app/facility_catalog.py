"""SQLite 시설 카탈로그와 시간 정책을 DB 파일 버전별로 캐시한다."""

import sys
from functools import cache, lru_cache
from importlib import import_module
from pathlib import Path

from app.models import Option, OptionsResponse

DB_PATH = Path(__file__).resolve().parents[2] / "database" / "facilities.sqlite3"
SPORT_LABELS = {"tennis": "테니스", "soccer": "축구", "futsal": "풋살"}


@cache
def load_query_api():
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    return import_module("database.query_api")


def _file_version(path: Path):
    stat = path.stat()
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


def read_catalog(path: Path):
    return _read_catalog(path, _file_version(path))


@lru_cache(maxsize=4)
def _read_catalog(path, _version):
    query = load_query_api()
    facilities = [
        {"facility_id": row["id"], "name": row["name"], "sport": row["facility_type"],
         "district": row["district"], "address": row["address"], "booking_url": row["booking_url"]}
        for row in query.facilities(path)
    ]
    discounts = query.fetch(path, "SELECT id, name FROM discount_categories ORDER BY id")
    return facilities, OptionsResponse(
        sports=[Option(code=code, label=SPORT_LABELS.get(code, code))
                for code in sorted({facility["sport"] for facility in facilities})],
        districts=sorted({facility["district"] for facility in facilities}),
        discount_types=[Option(code=row["id"], label=row["name"]) for row in discounts],
    )


@lru_cache(maxsize=32)
def _time_data(path, use_date, _version):
    return load_query_api().search_time_data(path, use_date)


def read_fixed_slots(path: Path, use_date: str):
    return _time_data(path, use_date, _file_version(path))[1]


def read_search_time_policies(path: Path, use_date: str):
    return _time_data(path, use_date, _file_version(path))[0]
