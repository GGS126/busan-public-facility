"""Use the common rules engine after SQLite closure and regulation checks."""

from pathlib import Path

from app.compare import compare_facility
from app.facility_catalog import closure_holiday_codes, load_query_api
from app.models import CompareResult, Conditions, FeeResult, ReviewItem, Source, Terms
from app.repository import load_sqlite_rule_data


def compare_sqlite(path: Path, facility: dict[str, str], conditions: Conditions,
                   *, closures: dict[str, dict] | None = None) -> CompareResult:
    query = load_query_api()
    facility_id = facility["facility_id"]
    day = conditions.date.isoformat()
    with query.read_snapshot(path) as connection:
        active = query.fetch(connection, """
            SELECT r.id, r.source_id, s.url, s.checked_on, s.license
            FROM rule_sets r JOIN sources s ON s.id=r.source_id
            WHERE r.facility_id=? AND ? BETWEEN r.effective_from AND r.effective_to
        """, (facility_id, day))
        if len(active) != 1:
            return _blocked(facility, "needs_review",
                            "rule_conflict" if active else "rule_not_in_effect",
                            "적용 기간이 겹치는 요금 규정이 있습니다." if active else "적용기간 내 요금 규정이 없습니다.")
        if closures is None:
            closures = query.closure_statuses(connection, day, closure_holiday_codes(conditions.date))
        closure = closures.get(facility_id)
        if closure is None or closure["is_closed"] is None:
            return _blocked(facility, "needs_review", "rule_missing", "명절 휴장 여부를 확인해 주세요.", active[0])
        if closure["is_closed"]:
            notes = " / ".join(dict.fromkeys(item["note"] for item in closure["matched_rules"]))
            return _blocked(facility, "not_eligible", "rule_not_in_effect", f"정기 휴장일입니다. {notes}", active[0])
        data = load_sqlite_rule_data(path, connection=connection)
        rules = next(item for item in data.facilities if item.facility_id == facility_id)
        return compare_facility(rules, conditions)


def _blocked(facility, status, code, reason, source=None):
    source_id = source["source_id"] if source else None
    sources = []
    if source and source["checked_on"]:
        sources.append(Source(source_id=source_id, url=source["url"], checked_at=source["checked_on"],
                              license=source["license"] or "이용허락범위 미확인"))
    return CompareResult(
        facility_id=facility["facility_id"], facility_name=facility["name"],
        fee=FeeResult(status=status, items=[], total=None, payment_due=None, online_prepay=None,
                      onsite_payment=None, payment_unverified=None, expected_refund=None, net_cost_after_refund=None,
                      review_items=[ReviewItem(code=code, target="base", reason=reason, source_id=source_id)]),
        terms=Terms(), checklist=[], checklist_review_items=[], sources=sources,
    )
