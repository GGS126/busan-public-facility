"""비교 서비스(COMP-07). 규칙 엔진 결과에 예약·취소 조건, 증빙서류, 출처를 묶는다."""

from app.engine import calculate
from app.models import CompareResult, Conditions, FacilityRules


def compare_facility(rules: FacilityRules, conditions: Conditions) -> CompareResult:
    fee = calculate(rules, conditions)

    checklist: list[str] = []
    for rule in rules.discount_rules:
        if rule.discount_type in conditions.discount_types and rule.in_effect(conditions.date):
            checklist.extend(doc for doc in rule.required_documents or [] if doc not in checklist)

    used = {item.source_id for item in fee.items} | {item.source_id for item in fee.review_items}
    if rules.terms.source_id is not None:
        used.add(rules.terms.source_id)

    return CompareResult(
        facility_id=rules.facility_id,
        facility_name=rules.name,
        fee=fee,
        terms=rules.terms,
        checklist=checklist,
        sources=[source for source in rules.sources if source.source_id in used],
    )
