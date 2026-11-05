"""요금 규칙 엔진(COMP-06).

규정과 조건만으로 결과가 정해지는 순수 함수이며 LLM, DB, 현재 시각에 의존하지 않는다.
규정이 없거나 충돌하면 계산하지 않고 '확인 필요'를 반환한다(SDD 3.5).
"""

from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from app.models import (
    Conditions,
    DiscountRule,
    FacilityRules,
    FeeItem,
    FeeResult,
    FeeRule,
    ReviewItem,
    to_minutes,
)

ROUNDING_MODES = {"floor": ROUND_FLOOR, "ceil": ROUND_CEILING, "round": ROUND_HALF_UP}


class NeedsReview(Exception):
    def __init__(self, code: str, reason: str, source_id: str | None = None):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.source_id = source_id


def calculate(rules: FacilityRules, conditions: Conditions) -> FeeResult:
    items: list[FeeItem] = []
    reviews: list[ReviewItem] = []

    def attempt(target: str, section) -> bool:
        try:
            items.extend(section())
            return True
        except NeedsReview as review:
            reviews.append(
                ReviewItem(
                    code=review.code,
                    target=target,
                    reason=review.reason,
                    # 근거 규정이 없으면 시설의 공식 출처로 안내한다(AC-007).
                    source_id=review.source_id or rules.source_id,
                )
            )
            return False

    base_ok = attempt("base", lambda: _base_items(rules, conditions))
    lighting_ok = attempt("lighting", lambda: _lighting_items(rules, conditions))
    attempt("discount", lambda: _discount_items(rules, conditions, items, base_ok, lighting_ok))

    if reviews:
        return FeeResult(
            status="needs_review",
            items=items,
            total=None,
            payment_due=None,
            expected_refund=None,
            net_cost_after_refund=None,
            review_items=reviews,
        )

    refund = -sum(item.amount for item in items if item.method == "prepay_refund")
    due = sum(item.amount for item in items if item.method != "prepay_refund")
    return FeeResult(
        status="calculated",
        items=items,
        total=due - refund,
        payment_due=due,
        expected_refund=refund,
        net_cost_after_refund=due - refund,
        review_items=[],
    )


def _day_types(day: date, holidays: list[date]) -> set[str]:
    weekend = day.weekday() >= 5
    if day in holidays:
        return {"holiday", "weekend"} if weekend else {"holiday"}
    return {"weekend"} if weekend else {"weekday"}


def _active_fee_rules(rules: FacilityRules, conditions: Conditions, fee_type: str) -> list[FeeRule]:
    """이 이용에 적용되는 유효한 규정을 고른다.

    요일이나 시간대가 None인 규정은 적용 여부를 알 수 없으므로 확인 필요로 보낸다.
    이용일에 유효하지 않은 규정은 유효한 규정이 그 시간을 대신하지 못할 때만 확인 필요로 보낸다.
    """
    start, end = to_minutes(conditions.start_time), to_minutes(conditions.end_time)
    day_types = _day_types(conditions.date, rules.holidays)
    relevant = [
        r
        for r in rules.fee_rules
        if r.type == fee_type
        and r.sport == conditions.sport
        and (r.months is None or conditions.date.month in r.months)
        and (r.day_types is None or day_types & set(r.day_types))
        and (r.time_from is None or (to_minutes(r.time_from) < end and start < to_minutes(r.time_to)))
    ]

    active = [r for r in relevant if r.in_effect(conditions.date)]
    for rule in active:
        if rule.day_types is None:
            raise NeedsReview("rule_missing", "요금 규정의 적용 요일을 확인할 수 없습니다.", rule.source_id)
        if rule.time_from is None:
            raise NeedsReview("rule_missing", "요금 규정의 적용 시간대를 확인할 수 없습니다.", rule.source_id)

    covered = {
        minute for r in active for minute in range(to_minutes(r.time_from), to_minutes(r.time_to))
    }
    for rule in relevant:
        if rule in active:
            continue
        rule_start = start if rule.time_from is None else max(start, to_minutes(rule.time_from))
        rule_end = end if rule.time_to is None else min(end, to_minutes(rule.time_to))
        if any(minute not in covered for minute in range(rule_start, rule_end)):
            raise NeedsReview("rule_not_in_effect", "이용일에 적용되는 요금 규정이 없습니다.", rule.source_id)
    return active


def _unit_charge(rule: FeeRule, minutes: int) -> int:
    """요금 단위 하나의 금액. minutes는 단위 안에서 실제 이용한 시간이다."""
    if rule.amount is None:
        raise NeedsReview("rule_missing", "요금 금액을 확인할 수 없습니다.", rule.source_id)
    if minutes == rule.unit_minutes or rule.partial_unit == "round_up":
        return rule.amount
    if rule.partial_unit is None:
        raise NeedsReview("rule_missing", "요금 단위 미만의 처리 방식을 확인할 수 없습니다.", rule.source_id)
    charge = Decimal(rule.amount) * minutes / rule.unit_minutes
    if charge != charge.to_integral_value():
        raise NeedsReview("rule_missing", "단위 미만 요금의 끝전 처리 방식을 확인할 수 없습니다.", rule.source_id)
    return int(charge)


def _require_unit(rule: FeeRule) -> int:
    if rule.unit_minutes is None:
        raise NeedsReview("rule_missing", "요금 단위를 확인할 수 없습니다.", rule.source_id)
    return rule.unit_minutes


def _base_items(rules: FacilityRules, conditions: Conditions) -> list[FeeItem]:
    active = _active_fee_rules(rules, conditions, "base")
    start, end = to_minutes(conditions.start_time), to_minutes(conditions.end_time)
    totals: dict[str, int] = {}
    by_id = {rule.rule_id: rule for rule in active}

    cursor = start
    while cursor < end:
        hits = [r for r in active if to_minutes(r.time_from) <= cursor < to_minutes(r.time_to)]
        if not hits:
            raise NeedsReview("rule_missing", "이용 시간에 적용되는 기본요금 규정이 없습니다.")
        if len(hits) > 1:
            raise NeedsReview("rule_conflict", "이용 시간에 적용되는 기본요금 규정이 충돌합니다.", hits[0].source_id)
        rule = hits[0]
        unit = _require_unit(rule)
        unit_end = min(cursor + unit, end)
        # 단위가 시간대 경계를 넘을 때 어느 요금을 적용할지는 규정에 따라 다르므로 추정하지 않는다.
        if unit_end > to_minutes(rule.time_to):
            raise NeedsReview("rule_missing", "요금 단위가 시간대 경계를 넘을 때의 처리 방식을 확인할 수 없습니다.", rule.source_id)
        totals[rule.rule_id] = totals.get(rule.rule_id, 0) + _unit_charge(rule, unit_end - cursor)
        cursor += unit

    return [
        FeeItem(type="base", amount=amount, rule_id=rule_id, source_id=by_id[rule_id].source_id)
        for rule_id, amount in totals.items()
    ]


def _lighting_items(rules: FacilityRules, conditions: Conditions) -> list[FeeItem]:
    """단위가 조명 시간대와 겹치면 가산한다."""
    active = _active_fee_rules(rules, conditions, "lighting")
    start, end = to_minutes(conditions.start_time), to_minutes(conditions.end_time)

    for index, rule in enumerate(active):
        for other in active[index + 1 :]:
            overlap_start = max(to_minutes(rule.time_from), to_minutes(other.time_from), start)
            overlap_end = min(to_minutes(rule.time_to), to_minutes(other.time_to), end)
            if overlap_start < overlap_end:
                raise NeedsReview("rule_conflict", "이용 시간에 적용되는 조명료 규정이 충돌합니다.", rule.source_id)

    items = []
    charged_units: list[tuple[str, int, int]] = []
    for rule in active:
        unit = _require_unit(rule)
        amount = 0
        for unit_start in range(start, end, unit):
            unit_end = min(unit_start + unit, end)
            if unit_start < to_minutes(rule.time_to) and to_minutes(rule.time_from) < unit_end:
                # 한 단위가 두 조명 시간대에 걸치면 어느 요금을 적용할지 추정하지 않는다.
                if any(
                    rule_id != rule.rule_id and unit_start < other_end and other_start < unit_end
                    for rule_id, other_start, other_end in charged_units
                ):
                    raise NeedsReview("rule_missing", "요금 단위가 조명 시간대 경계를 넘을 때의 처리 방식을 확인할 수 없습니다.", rule.source_id)
                charged_units.append((rule.rule_id, unit_start, unit_end))
                amount += _unit_charge(rule, unit_end - unit_start)
        items.append(FeeItem(type="lighting", amount=amount, rule_id=rule.rule_id, source_id=rule.source_id))
    return items


def _discount_items(
    rules: FacilityRules,
    conditions: Conditions,
    items: list[FeeItem],
    base_ok: bool,
    lighting_ok: bool,
) -> list[FeeItem]:
    types = list(dict.fromkeys(conditions.discount_types))
    if not types:
        return []

    selected = [_discount_rule(rules, conditions.date, discount_type) for discount_type in types]

    # 중복 감면의 계산 순서는 공식 근거를 확인하기 전까지 추정하지 않는다.
    if len(selected) > 1:
        names = ", ".join(types)
        reason = (
            f"{names} 감면의 중복 적용 여부를 확인할 수 없습니다."
            if any(rule.stackable is None for rule in selected)
            else f"{names} 감면을 함께 선택했을 때의 계산 방식을 확인할 수 없습니다."
        )
        raise NeedsReview("rule_missing", reason, selected[0].source_id)

    rule = selected[0]
    if rule.applies_to is None or rule.method is None:
        raise NeedsReview("rule_missing", "감면 대상 요금이나 감면 방식을 확인할 수 없습니다.", rule.source_id)
    if not base_ok or (rule.applies_to == "base_and_lighting" and not lighting_ok):
        raise NeedsReview("rule_missing", "감면 대상 요금을 계산하지 못해 감면액을 계산할 수 없습니다.", rule.source_id)

    target_types = {"base"} if rule.applies_to == "base" else {"base", "lighting"}
    target = sum(item.amount for item in items if item.type in target_types)
    amount = _discount_amount(rule, target)
    return [
        FeeItem(type="discount", amount=-amount, rule_id=rule.rule_id, source_id=rule.source_id, method=rule.method)
    ]


def _discount_rule(rules: FacilityRules, day: date, discount_type: str) -> DiscountRule:
    candidates = [r for r in rules.discount_rules if r.discount_type == discount_type]
    in_effect = [r for r in candidates if r.in_effect(day)]
    if not candidates:
        raise NeedsReview("rule_missing", f"{discount_type} 감면 규정을 확인할 수 없습니다.")
    if not in_effect:
        raise NeedsReview("rule_not_in_effect", f"이용일에 적용되는 {discount_type} 감면 규정이 없습니다.", candidates[0].source_id)
    if len(in_effect) > 1:
        raise NeedsReview("rule_conflict", f"{discount_type} 감면 규정이 충돌합니다.", in_effect[0].source_id)
    return in_effect[0]


def _discount_amount(rule: DiscountRule, target: int) -> int:
    amount = _uncapped_discount_amount(rule, target)
    if amount > target:
        raise NeedsReview("rule_conflict", "감면액이 감면 대상 요금보다 큽니다.", rule.source_id)
    return amount


def _uncapped_discount_amount(rule: DiscountRule, target: int) -> int:
    if rule.fixed_amount is not None:
        return rule.fixed_amount
    if rule.rate is None:
        raise NeedsReview("rule_missing", "감면율이나 감면액을 확인할 수 없습니다.", rule.source_id)

    value = Decimal(target) * rule.rate
    if rule.rounding is not None:
        mode, unit = rule.rounding.split("_")
        return int((value / int(unit)).to_integral_value(ROUNDING_MODES[mode]) * int(unit))
    if value != value.to_integral_value():
        raise NeedsReview("rule_missing", "감면액의 끝전 처리 방식을 확인할 수 없습니다.", rule.source_id)
    return int(value)
