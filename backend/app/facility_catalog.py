"""SQLite 시설 카탈로그와 시간 정책을 DB 파일 버전별로 캐시한다."""

import sys
from datetime import date
from functools import cache, lru_cache
from importlib import import_module
from pathlib import Path

from app.models import HolidayCalendar, Option, OptionsResponse
from app.repository import HOLIDAYS_PATH

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


@cache
def holiday_calendar() -> HolidayCalendar:
    return HolidayCalendar.model_validate_json(HOLIDAYS_PATH.read_text(encoding="utf-8"))


def facility_closures(path: Path, day: date) -> dict[str, dict]:
    return _facility_closures(path, day, _file_version(path))


@lru_cache(maxsize=32)
def _facility_closures(path: Path, day: date, _version) -> dict[str, dict]:
    return load_query_api().closure_statuses(path, day.isoformat(), closure_holiday_codes(day))


def closure_holiday_codes(day: date):
    calendar = holiday_calendar()
    codes = None
    if calendar.covers(day):
        holiday_codes = {"설날": "lunar_new_year_day", "추석": "chuseok_day"}
        codes = [holiday_codes[item.name] for item in calendar.holidays
                 if item.date == day and item.name in holiday_codes]
    return codes
