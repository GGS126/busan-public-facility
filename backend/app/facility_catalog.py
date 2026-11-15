"""Read the SQLite catalog shared by facility search and AI extraction."""

import sys
from datetime import date
from functools import cache, lru_cache
from importlib import import_module
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.models import HolidayCalendar, Option, OptionsResponse
from app.repository import HOLIDAYS_PATH

DB_PATH = Path(__file__).resolve().parents[2] / "database" / "facilities.sqlite3"
SPORT_LABELS = {"tennis": "테니스"}


@cache
def load_query_api(path: Path):
    package_name = "_facility_database"
    spec = spec_from_file_location(package_name, path.parent / "__init__.py")
    if spec is None or spec.loader is None:
        raise ImportError("SQLite query module is unavailable")
    package = module_from_spec(spec)
    sys.modules.setdefault(package_name, package)
    return import_module(f"{package_name}.query_api")


@cache
def _holiday_calendar() -> HolidayCalendar:
    return HolidayCalendar.model_validate_json(HOLIDAYS_PATH.read_text(encoding="utf-8"))


def facility_closures(path: Path, day: date) -> dict[str, dict]:
    calendar = _holiday_calendar()
    codes = None
    if calendar.covers(day):
        holiday_codes = {"설날": "lunar_new_year_day", "추석": "chuseok_day"}
        codes = [holiday_codes[item.name] for item in calendar.holidays
                 if item.date == day and item.name in holiday_codes]
    return load_query_api(DB_PATH.with_name("query_api.py")).closure_statuses(path, day.isoformat(), codes)


def read_catalog(path: Path) -> tuple[list[dict[str, str]], OptionsResponse]:
    return _read_catalog(path, _file_version(path))


def _file_version(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=4)
def _read_catalog(path, _file_version):
    query = load_query_api(DB_PATH.with_name("query_api.py"))
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
    return load_query_api(DB_PATH.with_name("query_api.py")).fixed_slots_by_facility(path, use_date)
