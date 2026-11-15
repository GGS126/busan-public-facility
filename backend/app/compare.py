"""비교 서비스(COMP-07). 규칙 엔진 결과에 예약·취소 조건, 증빙서류, 출처를 묶는다."""

from app.engine import calculate
from app.models import CompareResult, Conditions, FacilityRules, ReviewItem


def compare_facility(rules: FacilityRules, conditions: Conditions) -> CompareResult:
    fee = calculate(rules, conditions)

    used = {item.source_id for item in fee.items} | {item.source_id for item in fee.review_items}
    if rules.terms.source_id is not None:
        used.add(rules.terms.source_id)

    checklist: list[str] = []
    checklist_reviews: list[ReviewItem] = []
    for discount_type in dict.fromkeys(conditions.discount_types):
        matched = [
            rule
            for rule in rules.discount_rules
            if rule.discount_type == discount_type and rule.in_effect(conditions.date)
        ]
        for rule in matched:
            if rule.required_documents is not None:
                checklist.extend(doc for doc in rule.required_documents if doc not in checklist)
                used.add(rule.source_id)
        # 증빙서류를 모르는 것과 필요 없는 것을 구분해, 빈 목록이 '서류 불필요'로 보이지 않게 한다.
        if not matched or any(rule.required_documents is None for rule in matched):
            source_id = matched[0].source_id if matched else rules.source_id
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
    # 공휴일 요금을 적용했으면 공휴일 판정의 근거도 함께 보여 준다.
    calendar = rules.holiday_calendar
    if calendar is not None and calendar.is_holiday(conditions.date):
        sources.append(calendar.source)

    return CompareResult(
        facility_id=rules.facility_id,
        facility_name=rules.name,
        fee=fee,
        terms=rules.terms,
        checklist=checklist,
        checklist_review_items=checklist_reviews,
        sources=sources,
    )
