"""비교 서비스(COMP-07). 규칙 엔진 결과에 예약·취소 조건, 증빙서류, 출처를 묶는다."""

from datetime import date

from app.engine import _not_calculated, calculate
from app.models import ClosureRule, CompareResult, Conditions, FacilityRules, FeeResult, ReviewItem
from app.refund import estimate_cancel_refund

# 공휴일 목록의 이름과 DB의 명절 휴장 코드. 전날·다음날은 휴장 규정에 없으므로 당일만 연결한다.
HOLIDAY_CLOSURE_CODES = {"설날": "lunar_new_year_day", "추석": "chuseok_day"}
UNCALCULATED = dict(
    total=None, payment_due=None, online_prepay=None, onsite_payment=None,
    payment_unverified=None, expected_refund=None, net_cost_after_refund=None,
)


def compare_facility(rules: FacilityRules, conditions: Conditions) -> CompareResult:
    fee = _fee_with_closure(rules, conditions)
    terms = rules.terms_on(conditions.date)

    used = {item.source_id for item in fee.items} | {item.source_id for item in fee.review_items}
    if terms.source_id is not None:
        used.add(terms.source_id)

    cancel_refund = None
    if conditions.cancellation is not None:
        cancel_refund = estimate_cancel_refund(rules, conditions, conditions.cancellation, fee)
        used |= {item.source_id for item in cancel_refund.review_items}
        if cancel_refund.source_id is not None:
            used.add(cancel_refund.source_id)

    checklist: list[str] = []
    checklist_reviews: list[ReviewItem] = []
    for discount_type, _, _ in conditions.discount_selections:
        matched = [
            rule
            for rule in rules.discount_rules
            if rule.discount_type == discount_type and rule.in_effect(conditions.date)
        ]
        for rule in matched:
            items = list(rule.required_documents or [])
            # 사후 반환 감면은 신청 기한을 놓치면 반환받지 못하므로 서류와 함께 준비사항으로 안내한다.
            if rule.application_deadline:
                items.append(f"감면 신청 기한: {rule.application_deadline}")
            if rule.guardian_note:
                items.append(f"보호자 동반 시: {rule.guardian_note}")
            if items:
                checklist.extend(item for item in items if item not in checklist)
                used.add(rule.source_id)
        # 증빙서류를 모르는 것과 필요 없는 것을 구분해, 빈 목록이 '서류 불필요'로 보이지 않게 한다.
        if not matched or any(rule.required_documents is None for rule in matched):
            source_id = matched[0].source_id if matched else rules.source_on(conditions.date)
            used.add(source_id)
            checklist_reviews.append(
                ReviewItem(
                    code="rule_missing",
                    target="checklist",
                    reason=f"{discount_type} 감면의 증빙서류를 확인할 수 없습니다. 공식 안내를 확인해 주세요.",
                    source_id=source_id,
                )
            )

    sources = [source for source in rules.sources if source.source_id in used]
    # 공휴일 요금을 적용했으면 공휴일 판정의 근거도 함께 보여 준다. 이용할 수 없는 날은 요금을 적용하지 않았다.
    calendar = rules.holiday_calendar
    if fee.status != "not_eligible" and calendar is not None and calendar.is_holiday(conditions.date):
        sources.append(calendar.source)

    return CompareResult(
        facility_id=rules.facility_id,
        facility_name=rules.name,
        fee=fee,
        terms=terms,
        checklist=checklist,
        checklist_review_items=checklist_reviews,
        sources=sources,
        cancel_refund=cancel_refund,
    )


def _fee_with_closure(rules: FacilityRules, conditions: Conditions) -> FeeResult:
    """정기 휴장일이면 요금을 계산하지 않는다. 명절 휴장인지 알 수 없으면 계산하되 확인 필요로 둔다."""
    closed, unresolved = _closures_on(rules, conditions.date)
    if closed:
        notes = " / ".join(dict.fromkeys(rule.note for rule in closed))
        return _not_calculated("not_eligible", "facility_closed", f"정기 휴장일입니다. {notes}", closed[0].source_id)

    fee = calculate(rules, conditions)
    if not unresolved or fee.status == "not_eligible":
        return fee
    review = ReviewItem(
        code="rule_missing",
        target="time",
        reason="이용일이 명절 휴장일인지 확인할 수 없습니다. 공식 안내를 확인해 주세요.",
        source_id=unresolved[0].source_id,
    )
    return fee.model_copy(
        update={"status": "needs_review", **UNCALCULATED, "review_items": [*fee.review_items, review]}
    )


def _closures_on(rules: FacilityRules, day: date) -> tuple[list[ClosureRule], list[ClosureRule]]:
    """(이용일에 해당하는 휴장 규정, 공휴일 목록 밖이라 판정하지 못한 명절 휴장 규정)"""
    active = [rule for rule in rules.closure_rules if rule.in_effect(day)]
    calendar = rules.holiday_calendar
    known = calendar is not None and calendar.covers(day)
    codes = (
        {HOLIDAY_CLOSURE_CODES[h.name] for h in calendar.holidays if h.date == day and h.name in HOLIDAY_CLOSURE_CODES}
        if known
        else set()
    )
    closed = [
        rule
        for rule in active
        if (rule.type == "annual_date" and rule.value == day.strftime("%m-%d"))
        or (rule.type == "exact_date" and rule.value == day.isoformat())
        or (rule.type == "holiday_code" and rule.value in codes)
    ]
    unresolved = [] if known else [rule for rule in active if rule.type == "holiday_code"]
    return closed, unresolved
