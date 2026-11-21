"""Read the SQLite catalog shared by facility search and AI extraction."""

import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

from app.models import Option, OptionsResponse

DB_PATH = Path(__file__).resolve().parents[2] / "database" / "facilities.sqlite3"
SPORT_LABELS = {"tennis": "테니스", "soccer": "축구", "futsal": "풋살"}


def read_catalog(path: Path) -> tuple[list[dict[str, str]], OptionsResponse]:
    return _read_catalog(path, _file_version(path))


def _file_version(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=4)
def _read_catalog(path, _file_version):
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
        rows = connection.execute(
            "SELECT id, name, facility_type, address, booking_url, district FROM facilities ORDER BY name"
        ).fetchall()
        discounts = connection.execute("SELECT id, name FROM discount_categories ORDER BY id").fetchall()

    facilities = []
    for facility_id, name, sport, address, booking_url, district in rows:
        facilities.append({
            "facility_id": facility_id,
            "name": name,
            "sport": sport,
            "district": district,
            "address": address,
            "booking_url": booking_url,
        })
    sports = sorted({facility["sport"] for facility in facilities})
    return facilities, OptionsResponse(
        sports=[Option(code=code, label=SPORT_LABELS.get(code, code)) for code in sports],
        districts=sorted({facility["district"] for facility in facilities}),
        discount_types=[Option(code=code, label=label) for code, label in discounts],
    )


def read_fixed_slots(path: Path, use_date: str) -> dict[str, list[dict[str, str]]]:
    return _read_fixed_slots(path, use_date, _file_version(path))


@lru_cache(maxsize=32)
def _read_fixed_slots(path, use_date, _version):
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
        rows = connection.execute(
            """SELECT r.facility_id, p.start_time, p.end_time
               FROM pricing_rules p JOIN rule_sets r ON r.id = p.rule_set_id
               WHERE p.selection_type = 'fixed_slot' AND ? BETWEEN r.effective_from AND r.effective_to
               ORDER BY r.facility_id, p.slot_no""",
            (use_date,),
        ).fetchall()
    slots = {}
    for facility_id, start_time, end_time in rows:
        slots.setdefault(facility_id, []).append({"start_time": start_time, "end_time": end_time})
    return slots

def read_search_time_policies(path: Path, use_date: str) -> dict[str, dict]:
    return _read_search_time_policies(path, use_date, _file_version(path))


@lru_cache(maxsize=32)
def _read_search_time_policies(path, use_date, _version):
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT f.id, f.open_time, f.close_time, t.selection_type, t.available_start_time,
                      t.available_end_time, t.min_minutes, t.max_minutes, t.step_minutes, t.daily_limit_minutes,
                      EXISTS(SELECT 1 FROM rule_sets h JOIN time_selection_policies p ON p.rule_set_id = h.id
                             WHERE h.facility_id = f.id AND p.selection_type = 'fixed_slot') AS fixed_slot_known
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
