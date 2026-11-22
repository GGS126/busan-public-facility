"""Adapt the SQLite quote to the comparison response used by the web UI."""

from pathlib import Path

from app.facility_catalog import holiday_calendar, load_query_api
from app.models import CompareResult, Conditions, FeeItem, FeeResult, ReviewItem, Source, Terms


def compare_sqlite(
    path: Path, facility: dict[str, str], conditions: Conditions, *, closures: dict[str, dict] | None = None,
) -> CompareResult:
    query = load_query_api()
    with query.read_snapshot(path) as connection:
        if closures is None:
            from app.facility_catalog import closure_holiday_codes
            closures = query.closure_statuses(connection, conditions.date.isoformat(),
                                              closure_holiday_codes(conditions.date))
        return _compare_sqlite(connection, facility, conditions, closures)


def _compare_sqlite(path, facility, conditions, closures):
    query = load_query_api()
    facility_id = facility["facility_id"]

    day = conditions.date.isoformat()
    rules = query.fetch(path, """
        SELECT s.*, r.id AS rule_set_id, rr.online_open_days_before,
               rr.online_close_days_before, rr.normal_cancel_online_min_days_before
        FROM rule_sets r JOIN sources s ON s.id = r.source_id
        LEFT JOIN reservation_rules rr ON rr.rule_set_id = r.id
        WHERE r.facility_id = ? AND ? BETWEEN r.effective_from AND r.effective_to
        ORDER BY r.effective_from DESC, r.id
    """, (facility_id, day))
    rule = rules[0] if len(rules) == 1 else None
    source_id = rule["id"] if rule and rule["checked_on"] else None
    sources = []
    if rule and rule["checked_on"]:
        sources.append(Source(source_id=source_id, url=rule["url"],
                              checked_at=rule["checked_on"], license=rule.get("license") or "이용조건 확인 필요"))

    terms = Terms()
    if len(rules) == 1:
        opens = rule["online_open_days_before"]
        closes = rule["online_close_days_before"]
        cancels = rule["normal_cancel_online_min_days_before"]
        terms = Terms(
            booking_open=f"이용일 {opens}일 전부터 {closes}일 전까지" if opens is not None and closes is not None else None,
            cancel_deadline=f"이용일 {cancels}일 전까지 온라인 취소" if cancels is not None else None,
            refund="취소 시점과 사유에 따른 환불률은 공식 안내를 확인해 주세요.",
            source_id=source_id,
        )

    items = []
    reviews = []
    invalid_time = False
    quote = {}
    if len(rules) > 1:
        reviews.append(ReviewItem(code="rule_conflict", target="base", source_id=source_id,
                                  reason="적용 기간이 겹치는 요금 규정이 있습니다."))
    elif not rules:
        reviews.append(ReviewItem(code="rule_not_in_effect", target="base", source_id=None,
                                  reason="적용기간 내 요금 규정이 없습니다."))
    else:
        closure = closures.get(facility_id)
        if closure is None or closure["is_closed"] is None:
            reviews.append(ReviewItem(code="rule_missing", target="base", source_id=source_id,
                                      reason="명절 휴장 여부를 확인해 주세요."))
        elif closure["is_closed"]:
            invalid_time = True
            notes = " / ".join(dict.fromkeys(item["note"] for item in closure["matched_rules"]))
            reviews.append(ReviewItem(code="rule_not_in_effect", target="base", source_id=source_id,
                                      reason=f"정기 휴장일입니다. {notes}"))
    if not reviews:
        args = (path, facility_id, day, conditions.start_time, conditions.end_time)
        weekend = conditions.date.weekday() >= 5
        calendar = holiday_calendar()
        covered = calendar.covers(conditions.date)
        holiday_or_weekend = weekend or (covered and calendar.is_holiday(conditions.date))
        def read_quote(holiday_or_weekend):
            try:
                return query.quote(*args, holiday_or_weekend)
            except ValueError as error:
                conflict = str(error) in {"중복된 요금 규정", "조명 옵션 중복", "중복 조명 옵션"}
                return {
                    "status": "rule_conflict" if conflict else "rule_missing",
                    "reason": "요금 규정이 중복됩니다." if conflict else "선택한 시간의 요금 규정을 확인할 수 없습니다.",
                }

        quote = read_quote(holiday_or_weekend)
        if quote["status"] == "priced":
            holiday = quote if weekend or covered else read_quote(True)
            if holiday["status"] != "priced" or quote["total_won"] != holiday["total_won"]:
                reviews.append(ReviewItem(
                    code="rule_conflict" if holiday["status"] == "rule_conflict" else "rule_missing",
                    target="base", source_id=source_id,
                    reason=holiday.get("reason") or "평일 공휴일 여부에 따라 요금이 달라 공식 안내 확인이 필요합니다.",
                ))
            else:
                items.append(FeeItem(type="base", amount=quote["base_fee_won"],
                                     rule_id=quote["price_rule_id"], source_id=source_id))
                if quote["lighting_fee_won"]:
                    items.append(FeeItem(type="lighting", amount=quote["lighting_fee_won"],
                                         rule_id=quote["lighting_rule_id"], source_id=source_id))
                for review in quote.get("review_items", []):
                    reviews.append(ReviewItem(code="rule_missing", target="lighting",
                                              source_id=source_id, reason=review["reason"]))
        else:
            details = quote.get("review_items", [])
            reason = details[0]["reason"] if details else quote.get("reason")
            invalid_time = quote["status"] in {"invalid_time", "invalid_optional_lighting"}
            code = {"not_available": "rule_not_in_effect", "rule_conflict": "rule_conflict",
                    "invalid_time": "slot_mismatch" if quote.get("selection_type") == "fixed_slot"
                    else "duration_not_allowed", "invalid_optional_lighting": "duration_not_allowed"}
            target = "time" if invalid_time else (
                "lighting" if quote["status"] in {"option_rule_inconsistent", "lighting_calculation_unavailable"} else "base"
            )
            reviews.append(ReviewItem(
                code=code.get(quote["status"], "rule_missing"),
                target=target,
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
            status="not_eligible" if invalid_time else "needs_review" if reviews else "calculated",
            items=items, total=total, payment_due=None if reviews else quote.get("payment_due"),
            online_prepay=quote.get("online_prepay_won"),
            onsite_payment=quote.get("onsite_payment"),
            payment_unverified=quote.get("payment_unverified_won"),
            expected_refund=None if reviews else 0, net_cost_after_refund=total,
            review_items=reviews,
        ),
        terms=terms, checklist=[], checklist_review_items=checklist_reviews, sources=sources,
    )
