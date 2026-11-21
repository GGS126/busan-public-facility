"""Read the SQLite catalog shared by facility search and AI extraction."""

import sqlite3
import sys
from contextlib import closing
from datetime import date
from functools import cache, lru_cache
from importlib import import_module
from pathlib import Path

from app.models import HolidayCalendar, Option, OptionsResponse
from app.repository import HOLIDAYS_PATH

DB_PATH = Path(__file__).resolve().parents[2] / "database" / "facilities.sqlite3"
SPORT_LABELS = {"tennis": "테니스", "soccer": "축구", "futsal": "풋살"}


@cache
def load_query_api(path: Path = DB_PATH.with_name("query_api.py")):
    root = str(DB_PATH.parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    return import_module("database.query_api")


@cache
def holiday_calendar() -> HolidayCalendar:
    return HolidayCalendar.model_validate_json(HOLIDAYS_PATH.read_text(encoding="utf-8"))


def facility_closures(path: Path, day: date) -> dict[str, dict]:
    return _facility_closures(path, day, _file_version(path))


@lru_cache(maxsize=32)
def _facility_closures(path: Path, day: date, _version) -> dict[str, dict]:
    calendar = holiday_calendar()
    codes = None
    if calendar.covers(day):
        holiday_codes = {"설날": "lunar_new_year_day", "추석": "chuseok_day"}
        codes = [holiday_codes[item.name] for item in calendar.holidays
                 if item.date == day and item.name in holiday_codes]
    return load_query_api().closure_statuses(path, day.isoformat(), codes)


def read_catalog(path: Path) -> tuple[list[dict[str, str]], OptionsResponse]:
    return _read_catalog(path, _file_version(path))


def _file_version(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=4)
def _read_catalog(path, _file_version):
    query = load_query_api()
    facilities = [
        {"facility_id": row["id"], "name": row["name"], "sport": row["facility_type"],
         "district": row["district"], "address": row["address"], "booking_url": row["booking_url"]}
        for row in query.facilities(path)
    ]
    discounts = query.fetch(path, "SELECT id, name FROM discount_categories ORDER BY id")
    sports = sorted({facility["sport"] for facility in facilities})
    return facilities, OptionsResponse(
        sports=[Option(code=code, label=SPORT_LABELS.get(code, code)) for code in sports],
        districts=sorted({facility["district"] for facility in facilities}),
        discount_types=[Option(code=code, label=label) for code, label in ((row["id"], row["name"]) for row in discounts)],
    )


def read_fixed_slots(path: Path, use_date: str) -> dict[str, list[dict[str, str]]]:
    return _read_fixed_slots(path, use_date, _file_version(path))


@lru_cache(maxsize=32)
def _read_fixed_slots(path, use_date, _version):
    return load_query_api().fixed_slots_by_facility(path, use_date)


def read_search_time_policies(path: Path, use_date: str) -> dict[str, dict]:
    return _read_search_time_policies(path, use_date, _file_version(path))


@lru_cache(maxsize=32)
def _read_search_time_policies(path, use_date, _version):
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT f.id, f.open_time, f.close_time, t.selection_type, t.available_start_time,
                      t.available_end_time, t.min_minutes, t.max_minutes, t.step_minutes, t.daily_limit_minutes,
                      t.rule_set_id
               FROM facilities f
               LEFT JOIN rule_sets r ON r.facility_id = f.id AND ? BETWEEN r.effective_from AND r.effective_to
               LEFT JOIN time_selection_policies t ON t.rule_set_id = r.id""",
            (use_date,),
        ).fetchall()
    policies = {}
    for row in rows:
        facility_id = row["id"]
        if facility_id in policies:
            policies[facility_id] = None
        else:
            policies[facility_id] = dict(row) if row["selection_type"] is not None else None
    return policies
