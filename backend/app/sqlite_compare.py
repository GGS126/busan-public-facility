"""Adapt the SQLite quote to the comparison response used by the web UI."""

from functools import cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.facility_catalog import DB_PATH
from app.models import CompareResult, Conditions, FeeItem, FeeResult, ReviewItem, Source, Terms


@cache
def load_query_api(path: Path):
    spec = spec_from_file_location("facility_query_api", path)
    if spec is None or spec.loader is None:
        raise ImportError("SQLite query module is unavailable")
    query = module_from_spec(spec)
    spec.loader.exec_module(query)
    return query


def compare_sqlite(path: Path, facility_id: str, conditions: Conditions) -> CompareResult | None:
    query = load_query_api(DB_PATH.with_name("query_api.py"))
    facility = next((row for row in query.facilities(path) if row["id"] == facility_id), None)
    if facility is None or facility["facility_type"] != conditions.sport:
        return None

    day = conditions.date.isoformat()
    rules = query.fetch(path, """
        SELECT r.id, s.id AS source_id, s.url, s.checked_on, rr.online_open_days_before,
               rr.online_close_days_before, rr.normal_cancel_online_min_days_before
        FROM rule_sets r JOIN sources s ON s.id = r.source_id
        LEFT JOIN reservation_rules rr ON rr.rule_set_id = r.id
        WHERE r.facility_id = ?
        ORDER BY (? BETWEEN r.effective_from AND r.effective_to) DESC, r.effective_from DESC
    """, (facility_id, day))
    rule = rules[0] if rules else None
    source_id = rule["source_id"] if rule else facility_id
    sources = []
    if rule and rule["checked_on"]:
        sources.append(Source(source_id=source_id, url=rule["url"],
                              checked_at=rule["checked_on"], license="이용조건 확인 필요"))

    prices = query.pricing_rules(path, facility_id, day, False)
    active_rule_ids = {price["rule_set_id"] for price in prices}
    terms = Terms()
    if len(active_rule_ids) == 1 and rule and rule["id"] in active_rule_ids:
        if rule["online_open_days_before"] is not None:
            terms = Terms(
                booking_open=f'이용일 {rule["online_open_days_before"]}일 전부터 {rule["online_close_days_before"]}일 전까지',
                cancel_deadline=f'이용일 {rule["normal_cancel_online_min_days_before"]}일 전까지 온라인 취소',
                refund="취소 시점과 사유에 따른 환불률은 공식 안내를 확인해 주세요.",
                source_id=source_id,
            )

    items = []
    reviews = []
    if len(active_rule_ids) > 1:
        reviews.append(ReviewItem(code="rule_conflict", target="base", source_id=source_id,
                                  reason="적용 기간이 겹치는 요금 규정이 있습니다."))
    else:
        args = (path, facility_id, day, conditions.start_time, conditions.end_time)
        weekend = conditions.date.weekday() >= 5
        quote = query.quote(*args, weekend)
        if quote["status"] == "priced":
            holiday = quote if weekend else query.quote(*args, True)
            if holiday["status"] != "priced" or quote["total_won"] != holiday["total_won"]:
                reviews.append(ReviewItem(code="rule_missing", target="base", source_id=source_id,
                                          reason="평일 공휴일 여부에 따라 요금이 달라 공식 안내 확인이 필요합니다."))
            else:
                items.append(FeeItem(type="base", amount=quote["base_fee_won"],
                                     rule_id=quote["price_rule_id"], source_id=source_id))
                if quote["lighting_fee_won"]:
                    items.append(FeeItem(type="lighting", amount=quote["lighting_fee_won"],
                                         rule_id=quote["price_rule_id"], source_id=source_id))
        else:
            details = quote.get("review_items", [])
            reason = details[0]["reason"] if details else quote.get("reason")
            reviews.append(ReviewItem(
                code="rule_not_in_effect" if quote["status"] == "not_available" else "rule_missing",
                target="base",
                reason=reason or "선택한 시간에 적용할 요금 규정을 확인할 수 없습니다.",
                source_id=source_id,
            ))

    checklist_reviews = []
    if conditions.discount_types:
        reviews.append(ReviewItem(code="rule_missing", target="discount", source_id=source_id,
                                  reason="감면 적용 금액은 공식 안내에서 확인해 주세요."))
        checklist_reviews.append(ReviewItem(code="rule_missing", target="checklist", source_id=source_id,
                                            reason="감면에 필요한 증빙서류는 공식 안내에서 확인해 주세요."))

    total = None if reviews else sum(item.amount for item in items)
    return CompareResult(
        facility_id=facility_id, facility_name=facility["name"],
        fee=FeeResult(
            status="needs_review" if reviews else "calculated",
            items=items, total=total, payment_due=total,
            expected_refund=None if reviews else 0, net_cost_after_refund=total,
            review_items=reviews,
        ),
        terms=terms, checklist=[], checklist_review_items=checklist_reviews, sources=sources,
    )
