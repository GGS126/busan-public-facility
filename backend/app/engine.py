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
    HolidayCalendar,
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
    """공휴일인지 알 수 없는 날은 공휴일인 경우와 아닌 경우를 모두 계산한다.

    두 경우의 금액이 같으면 그 금액을 보여 주고, 다르거나 계산하지 못하면 확인 필요로 보낸다.
    """
    unavailable = _check_time(rules, conditions)
    if unavailable is not None:
        return unavailable

    results = [
        _calculate(rules, conditions, day_types)
        for day_types in _day_type_candidates(conditions.date, rules.holiday_calendar)
    ]
    first = results[0]
    if all(_amount_key(result) == _amount_key(first) for result in results):
        return first
    return FeeResult(
        status="needs_review",
        items=[],
        total=None,
        payment_due=None,
        onsite_payment=None,
        payment_unverified=None,
        expected_refund=None,
        net_cost_after_refund=None,
        review_items=[
            ReviewItem(
                code="rule_missing",
                target=_differing_target(results),
                reason="이용일이 공휴일인지 확인할 수 없습니다.",
                source_id=rules.source_on(conditions.date),
            )
        ],
    )


def _amount_key(result: FeeResult) -> tuple:
    """이용자에게 보이는 금액과 확인 필요 사유. 근거 규정이 달라도 금액이 같으면 같은 결과로 본다."""
    if result.status != "calculated":
        return (result.status, tuple((r.code, r.target, r.reason, r.source_id) for r in result.review_items))
    sums = {}
    for item in result.items:
        sums[item.type] = sums.get(item.type, 0) + item.amount
    return (
        result.status,
        tuple(sorted(sums.items())),
        result.payment_due,
        result.onsite_payment,
        result.payment_unverified,
        result.expected_refund,
    )


def _differing_target(results: list[FeeResult]) -> str:
    def section(result: FeeResult, target: str) -> tuple:
        reviews = sorted(r.code for r in result.review_items if r.target == target)
        return (sum(item.amount for item in result.items if item.type == target), reviews)

    for target in ("base", "lighting", "discount"):
        if any(section(result, target) != section(results[0], target) for result in results):
            return target
    return "base"


def _calculate(rules: FacilityRules, conditions: Conditions, day_types: set[str]) -> FeeResult:
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
                    source_id=review.source_id or rules.source_on(conditions.date),
                )
            )
            return False

    base_ok = attempt("base", lambda: _base_items(rules, conditions, day_types))
    lighting_ok = attempt("lighting", lambda: _lighting_items(rules, conditions, day_types))
    optional_lighting_ok = attempt("lighting", lambda: _optional_lighting_items(rules, conditions, day_types))
    lighting_ok = lighting_ok and optional_lighting_ok
    attempt("discount", lambda: _discount_items(rules, conditions, items, base_ok, lighting_ok))

    if reviews:
        return FeeResult(
            status="needs_review",
            items=items,
            total=None,
            payment_due=None,
            onsite_payment=None,
            payment_unverified=None,
            expected_refund=None,
            net_cost_after_refund=None,
            review_items=reviews,
        )

    refund = -sum(item.amount for item in items if item.method == "prepay_refund")
    onsite = sum(item.amount for item in items if item.payment == "onsite")
    unverified = sum(item.amount for item in items if item.payment == "unverified")
    due = sum(
        item.amount for item in items if item.method != "prepay_refund" and item.payment not in ("onsite", "unverified")
    )
    return FeeResult(
        status="calculated",
        items=items,
        total=due + onsite + unverified - refund,
        # 결제 방식을 모르는 금액이 있으면 최초 납부액을 확정하지 않는다.
        payment_due=None if unverified else due,
        onsite_payment=onsite,
        payment_unverified=unverified,
        expected_refund=refund,
        net_cost_after_refund=due + onsite + unverified - refund,
        review_items=[],
    )


def _check_time(rules: FacilityRules, conditions: Conditions) -> FeeResult | None:
    """규정상 예약할 수 없는 시간이면 요금을 계산하지 않고 사유를 돌려준다.

    이용일에 유효한 이용시간 규정이 없으면 제한을 확인하지 않고, 요금 규정이 있는지로 판단한다.
    """
    policies = [
        p for p in rules.time_policies if p.sport == conditions.sport and p.in_effect(conditions.date)
    ]
    if not policies:
        return None
    if len(policies) > 1:
        return _not_calculated("needs_review", "rule_conflict", "이용시간 규정이 충돌합니다.", policies[0].source_id)

    policy = policies[0]
    start, end = to_minutes(conditions.start_time), to_minutes(conditions.end_time)
    if policy.open_time is not None and (
        start < to_minutes(policy.open_time) or end > to_minutes(policy.close_time)
    ):
        reason = f"운영시간({policy.open_time}~{policy.close_time}) 안에서 선택해 주세요."
        return _not_calculated("not_eligible", "outside_hours", reason, policy.source_id)
    if policy.selection == "fixed_slot":
        slots = [(slot.start_time, slot.end_time) for slot in policy.slots]
        if (conditions.start_time, conditions.end_time) not in slots:
            choices = ", ".join(f"{slot_start}~{slot_end}" for slot_start, slot_end in slots)
            reason = f"정해진 회차로만 예약할 수 있습니다. 가능한 회차: {choices}"
            return _not_calculated("not_eligible", "slot_mismatch", reason, policy.source_id)
    elif policy.max_minutes is not None and end - start > policy.max_minutes:
        reason = f"이용 시간은 최대 {policy.max_minutes}분까지 선택할 수 있습니다."
        return _not_calculated("not_eligible", "duration_not_allowed", reason, policy.source_id)
    elif policy.allowed_minutes and end - start not in policy.allowed_minutes:
        choices = ", ".join(f"{minutes}분" for minutes in policy.allowed_minutes)
        reason = f"이용 시간은 {choices} 중에서 선택할 수 있습니다."
        return _not_calculated("not_eligible", "duration_not_allowed", reason, policy.source_id)
    return None


def _not_calculated(status: str, code: str, reason: str, source_id: str) -> FeeResult:
    return FeeResult(
        status=status,
        items=[],
        total=None,
        payment_due=None,
        onsite_payment=None,
        payment_unverified=None,
        expected_refund=None,
        net_cost_after_refund=None,
        review_items=[ReviewItem(code=code, target="time", reason=reason, source_id=source_id)],
    )


def _day_type_candidates(day: date, calendar: HolidayCalendar | None) -> list[set[str]]:
    """이용일의 요일 구분. 공휴일 목록에 없는 기간이면 공휴일인 경우와 아닌 경우를 모두 돌려준다."""
    weekend = day.weekday() >= 5
    plain = {"weekend"} if weekend else {"weekday"}
    holiday = {"holiday", "weekend"} if weekend else {"holiday"}
    if calendar is None or not calendar.covers(day):
        return [plain, holiday]
    return [holiday] if calendar.is_holiday(day) else [plain]


def _active_fee_rules(
    rules: FacilityRules, conditions: Conditions, fee_type: str, day_types: set[str]
) -> list[FeeRule]:
    """이 이용에 적용되는 유효한 규정을 고른다.

    요일이나 시간대가 None인 규정은 적용 여부를 알 수 없으므로 확인 필요로 보낸다.
    이용일에 유효하지 않은 규정은 유효한 규정이 그 시간을 대신하지 못할 때만 확인 필요로 보낸다.
    """
    start, end = to_minutes(conditions.start_time), to_minutes(conditions.end_time)
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


def _base_items(rules: FacilityRules, conditions: Conditions, day_types: set[str]) -> list[FeeItem]:
    active = _active_fee_rules(rules, conditions, "base", day_types)
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


def _lighting_items(rules: FacilityRules, conditions: Conditions, day_types: set[str]) -> list[FeeItem]:
    """단위가 조명 시간대와 겹치면 가산한다."""
    active = _active_fee_rules(rules, conditions, "lighting", day_types)
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
        items.append(
            FeeItem(type="lighting", amount=amount, rule_id=rule.rule_id, source_id=rule.source_id, payment=_item_payment(rule))
        )
    return items


def _optional_lighting_items(rules: FacilityRules, conditions: Conditions, day_types: set[str]) -> list[FeeItem]:
    """사용자가 고른 조명 사용 시간만큼 계산한다.

    조명은 이용 시간 중 선택 조명 시간대와 겹치는 동안에만 쓸 수 있다.
    예: 19:00~22:00 회차에서 선택 조명 시간대가 07:00~20:00이면 19:00~20:00의 60분까지
    """
    minutes = conditions.optional_lighting_minutes
    if not minutes:
        return []
    options = [r for r in rules.fee_rules if r.type == "optional_lighting" and r.sport == conditions.sport]
    # 선택 조명이 없는 시설(예: 18시 이후 조명이 필수인 구덕)은 여러 시설을 비교할 때 입력한 조명 시간을 쓰지 않는다.
    if not options:
        return []
    start, end = to_minutes(conditions.start_time), to_minutes(conditions.end_time)
    active = _active_fee_rules(rules, conditions, "optional_lighting", day_types)
    if not active:
        # 규정은 있지만 이용 시간과 겹치지 않는다. 데이터 누락이 아니라 이 시간에 고를 수 없는 것이다.
        current = [r for r in options if r.in_effect(conditions.date) and r.time_from is not None] or options
        bands = ", ".join(sorted({f"{r.time_from}~{r.time_to}" for r in current if r.time_from is not None}))
        raise NeedsReview(
            "duration_not_allowed",
            f"이 이용 시간에는 선택 조명을 사용할 수 없습니다. 선택 조명 시간대: {bands}",
            current[0].source_id,
        )
    if len(active) > 1:
        raise NeedsReview("rule_conflict", "이용 시간에 적용되는 선택 조명 규정이 충돌합니다.", active[0].source_id)

    rule = active[0]
    band_start, band_end = max(start, to_minutes(rule.time_from)), min(end, to_minutes(rule.time_to))
    if minutes > band_end - band_start:
        reason = (
            f"선택 조명은 {_clock(band_start)}~{_clock(band_end)} 사이 "
            f"최대 {band_end - band_start}분까지 사용할 수 있습니다."
        )
        raise NeedsReview("duration_not_allowed", reason, rule.source_id)
    unit = _require_unit(rule)
    full_units, rest = divmod(minutes, unit)
    amount = full_units * _unit_charge(rule, unit)
    if rest and rule.extra_unit_minutes is None:
        amount += _unit_charge(rule, rest)
    elif rest:
        steps, leftover = divmod(rest, rule.extra_unit_minutes)
        if leftover and rule.partial_unit != "round_up":
            raise NeedsReview("rule_missing", "조명 추가 단위 미만의 처리 방식을 확인할 수 없습니다.", rule.source_id)
        amount += (steps + (1 if leftover else 0)) * rule.extra_unit_amount
    return [FeeItem(type="lighting", amount=amount, rule_id=rule.rule_id, source_id=rule.source_id, payment=_item_payment(rule))]


def _clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"

def _item_payment(rule: FeeRule) -> str:
    # 결제 방식을 모르면 금액은 계산하되 최초 납부액과 현장 결제액 어느 쪽에도 넣지 않는다.
    return rule.payment or "unverified"


def _discount_items(
    rules: FacilityRules,
    conditions: Conditions,
    items: list[FeeItem],
    base_ok: bool,
    lighting_ok: bool,
) -> list[FeeItem]:
    selections = conditions.discount_selections
    if not selections:
        return []

    selected = [
        (_discount_rule(rules, conditions.date, discount_type), count, holder)
        for discount_type, count, holder in selections
    ]

    # 서로 다른 이용자의 감면을 인원별로 나눠 계산할 수 있을 때만 함께 계산한다.
    # 한 요금 전체에 감면을 겹쳐 적용하는 순서는 공식 근거를 확인하기 전까지 추정하지 않는다.
    if len(selected) > 1 and any(count is None or rule.basis != "per_eligible_person" for rule, count, _ in selected):
        names = ", ".join(rule.discount_type for rule, _, _ in selected)
        reason = (
            f"{names} 감면의 중복 적용 여부를 확인할 수 없습니다."
            if any(rule.stackable is None for rule, _, _ in selected)
            else f"{names} 감면을 함께 선택했을 때의 계산 방식을 확인할 수 없습니다."
        )
        raise NeedsReview("rule_missing", reason, selected[0][0].source_id)

    discounts = []
    for rule, count, holder in selected:
        if rule.applies_to is None or rule.method is None:
            raise NeedsReview("rule_missing", "감면 대상 요금이나 감면 방식을 확인할 수 없습니다.", rule.source_id)
        if not base_ok or (rule.applies_to == "base_and_lighting" and not lighting_ok):
            raise NeedsReview("rule_missing", "감면 대상 요금을 계산하지 못해 감면액을 계산할 수 없습니다.", rule.source_id)

        target_types = {"base"} if rule.applies_to == "base" else {"base", "lighting"}
        target = sum(item.amount for item in items if item.type in target_types)
        amount = _discount_amount(rule, target, _discount_share(rule, conditions.headcount, count, holder))
        discounts.append(
            FeeItem(type="discount", amount=-amount, rule_id=rule.rule_id, source_id=rule.source_id, method=rule.method)
        )
    return discounts


def _discount_share(
    rule: DiscountRule, headcount: int | None, count: int | None, holder: bool | None
) -> tuple[int, int]:
    """감면 대상 요금 중 이 감면이 적용되는 비율(분자, 분모)."""
    if rule.basis == "whole_fee":
        return (1, 1)
    if rule.basis == "per_eligible_person":
        if count is None or headcount is None:
            raise NeedsReview("rule_missing", f"{rule.discount_type} 감면은 감면 대상 인원과 전체 이용 인원을 입력해야 계산할 수 있습니다.", rule.source_id)
        return (count, headcount)
    if holder is None:
        raise NeedsReview("rule_missing", f"{rule.discount_type} 감면은 예약 대표자가 감면 대상인지 입력해야 계산할 수 있습니다.", rule.source_id)
    return (1 if holder else 0, 1)


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


def _discount_amount(rule: DiscountRule, target: int, share: tuple[int, int]) -> int:
    amount = _uncapped_discount_amount(rule, target, share)
    if amount > target:
        raise NeedsReview("rule_conflict", "감면액이 감면 대상 요금보다 큽니다.", rule.source_id)
    return amount


def _uncapped_discount_amount(rule: DiscountRule, target: int, share: tuple[int, int]) -> int:
    if rule.fixed_amount is not None:
        return rule.fixed_amount
    if rule.rate is None:
        raise NeedsReview("rule_missing", "감면율이나 감면액을 확인할 수 없습니다.", rule.source_id)

    numerator, denominator = share
    if rule.basis == "per_eligible_person":
        # 감면은 대상자 한 명씩 적용되므로 인당 감면액의 끝전을 처리한 뒤 인원을 곱한다.
        # 합계가 나눠 떨어져도(20,000원 ÷ 3명 × 3명) 인당 금액에 끝전이 있으면 추정하지 않는다.
        per_person = Decimal(target) * rule.rate / denominator
        return _rounded(rule, per_person, "인당 감면액의 끝전 처리 방식을 확인할 수 없습니다.") * numerator
    value = Decimal(target) * rule.rate * numerator / denominator
    return _rounded(rule, value, "감면액의 끝전 처리 방식을 확인할 수 없습니다.")


def _rounded(rule: DiscountRule, value: Decimal, reason: str) -> int:
    if rule.rounding is not None:
        mode, unit = rule.rounding.split("_")
        return int((value / int(unit)).to_integral_value(ROUNDING_MODES[mode]) * int(unit))
    if value != value.to_integral_value():
        raise NeedsReview("rule_missing", reason, rule.source_id)
    return int(value)
