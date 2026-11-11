"""Read the SQLite catalog shared by facility search and AI extraction."""

import re
import sqlite3
from contextlib import closing
from pathlib import Path

from app.models import Option, OptionsResponse

DB_PATH = Path(__file__).resolve().parents[2] / "database" / "facilities.sqlite3"
SPORT_LABELS = {"tennis": "테니스"}


def read_catalog(path: Path) -> tuple[list[dict[str, str]], OptionsResponse]:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
        columns = {column[1] for column in connection.execute("PRAGMA table_info(facilities)")}
        district_column = "district" if "district" in columns else "NULL"
        rows = connection.execute(
            f"SELECT id, name, facility_type, address, booking_url, {district_column} FROM facilities ORDER BY name"
        ).fetchall()
        discounts = connection.execute("SELECT id, name FROM discount_categories ORDER BY id").fetchall()

    facilities = []
    for facility_id, name, sport, address, booking_url, district in rows:
        if not district:
            match = re.match(r"^부산(?:광역시)?\s+([^\s]+[구군])\s", address)
            if match is None:
                raise ValueError(f"Facility district is missing for {facility_id}")
            district = match[1]
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
