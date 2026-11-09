from datetime import date

import pytest

from app.engine import calculate
from app.models import Conditions, DiscountRule, FacilityRules, FeeRule, Source, TimePolicy

SATURDAY = date(2026, 11, 7)
MONDAY = date(2026, 11, 9)


def base_rule(**overrides) -> FeeRule:
    values = dict(
        rule_id="BASE",
        sport="futsal",
        type="base",
        amount=20000,
        unit_minutes=60,
        partial_unit="round_up",
        day_types=["weekday", "weekend", "holiday"],
        time_from="00:00",
        time_to="24:00",
        effective_from="2026-01-01",
        source_id="S-01",
    )
    return FeeRule(**(values | overrides))


def lighting_rule(**overrides) -> FeeRule:
    values = dict(rule_id="LIGHT", type="lighting", amount=5000, time_from="18:00", time_to="22:00")
    return base_rule(**(values | overrides))


def discount_rule(**overrides) -> DiscountRule:
    values = dict(
        rule_id="DISC",
        discount_type="multi_child",
        rate="0.5",
        applies_to="base",
        method="prepay_refund",
        effective_from="2026-01-01",
        source_id="S-02",
    )
    return DiscountRule(**(values | overrides))


def time_policy(**overrides) -> TimePolicy:
    values = dict(
        policy_id="TIME",
        sport="futsal",
        selection="fixed_slot",
        slots=[
            {"start_time": "07:00", "end_time": "09:00"},
            {"start_time": "13:00", "end_time": "14:00"},
            {"start_time": "20:00", "end_time": "22:00"},
        ],
        effective_from="2026-10-01",
        effective_to="2027-03-31",
        source_id="S-01",
    )
    return TimePolicy(**(values | overrides))


def flexible_policy(**overrides) -> TimePolicy:
    values = dict(slots=[], selection="flexible", allowed_minutes=[60, 120], open_time="08:00", close_time="22:00")
    return time_policy(**(values | overrides))


def facility(fee_rules=None, discount_rules=None, holidays=None, time_policies=()) -> FacilityRules:
    return FacilityRules(
        facility_id="F",
        name="가상 시설",
        source_id="S-00",
        holidays=holidays or [],
        time_policies=list(time_policies),
        fee_rules=[base_rule()] if fee_rules is None else fee_rules,
        discount_rules=discount_rules or [],
        sources=[
            Source(source_id=source_id, url="https://example.com", checked_at="2026-11-05", license="가상")
            for source_id in ("S-00", "S-01", "S-02")
        ],
    )


def conditions(day=SATURDAY, start="10:00", end="12:00", discounts=()) -> Conditions:
    return Conditions(
        sport="futsal",
        date=day,
        start_time=start,
        end_time=end,
        discount_types=list(discounts),
        source="direct",
    )


def amounts(result) -> dict[str, int]:
    return {item.type: item.amount for item in result.items}


def assert_review(result, target, code):
    assert result.status == "needs_review"
    assert (result.total, result.payment_due, result.expected_refund, result.net_cost_after_refund) == (None,) * 4
    assert [(item.target, item.code) for item in result.review_items] == [(target, code)]


def test_refund_discount_matches_sdd_example():
    rules = facility([base_rule(), lighting_rule()], [discount_rule()])
    result = calculate(rules, conditions(start="18:00", end="20:00", discounts=["multi_child"]))

    assert result.status == "calculated"
    assert amounts(result) == {"base": 40000, "lighting": 10000, "discount": -20000}
    assert result.payment_due == 50000
    assert result.expected_refund == 20000
    assert result.net_cost_after_refund == 30000
    assert result.total == 30000


def test_onsite_discount_reduces_payment_due():
    rules = facility(discount_rules=[discount_rule(method="onsite")])
    result = calculate(rules, conditions(discounts=["multi_child"]))

    assert (result.payment_due, result.expected_refund, result.total) == (20000, 0, 20000)


def test_lighting_excluded_when_outside_band():
    result = calculate(facility([base_rule(), lighting_rule()]), conditions())

    assert result.status == "calculated"
    assert amounts(result) == {"base": 40000}


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("17:00", "19:00", 5000),
        ("17:30", "19:30", 10000),
        ("21:00", "23:00", 5000),
        ("18:00", "18:30", 5000),
    ],
)
def test_lighting_charged_per_overlapping_unit(start, end, expected):
    result = calculate(facility([base_rule(), lighting_rule()]), conditions(start=start, end=end))

    assert amounts(result)["lighting"] == expected


def test_lighting_months_filter():
    rule = lighting_rule(months=[6, 7, 8])
    result = calculate(facility([base_rule(), rule]), conditions(start="18:00", end="20:00"))

    assert "lighting" not in amounts(result)


def test_lighting_without_band_needs_review_but_keeps_base():
    rule = lighting_rule(time_from=None, time_to=None)
    result = calculate(facility([base_rule(), rule]), conditions())

    assert_review(result, "lighting", "rule_missing")
    assert amounts(result) == {"base": 40000}


def test_overlapping_lighting_rules_conflict():
    rules = [base_rule(), lighting_rule(), lighting_rule(rule_id="LIGHT2", amount=7000)]
    result = calculate(facility(rules), conditions(start="18:00", end="20:00"))

    assert_review(result, "lighting", "rule_conflict")


def test_base_rate_changes_by_day_type():
    rules = [
        base_rule(rule_id="WEEKDAY", amount=10000, day_types=["weekday"]),
        base_rule(rule_id="WEEKEND", amount=30000, day_types=["weekend"]),
    ]
    assert amounts(calculate(facility(rules), conditions(day=MONDAY)))["base"] == 20000
    assert amounts(calculate(facility(rules), conditions(day=SATURDAY)))["base"] == 60000


def test_weekday_holiday_does_not_use_weekday_rate():
    rules = [base_rule(day_types=["weekday"])]
    result = calculate(facility(rules, holidays=[MONDAY]), conditions(day=MONDAY))

    assert_review(result, "base", "rule_missing")


def test_holiday_rate_applied():
    rules = [
        base_rule(rule_id="WEEKDAY", amount=10000, day_types=["weekday"]),
        base_rule(rule_id="HOLIDAY", amount=30000, day_types=["holiday"]),
    ]
    result = calculate(facility(rules, holidays=[MONDAY]), conditions(day=MONDAY))

    assert amounts(result)["base"] == 60000


def test_base_rate_changes_by_time_band_with_separate_items():
    rules = [
        base_rule(rule_id="DAY", amount=10000, time_from="06:00", time_to="18:00"),
        base_rule(rule_id="NIGHT", amount=30000, time_from="18:00", time_to="24:00"),
    ]
    result = calculate(facility(rules), conditions(start="17:00", end="19:00"))

    assert [(item.rule_id, item.amount) for item in result.items] == [("DAY", 10000), ("NIGHT", 30000)]
    assert result.total == 40000


def test_unit_crossing_time_band_needs_review():
    rules = [
        base_rule(rule_id="DAY", amount=10000, time_from="06:00", time_to="18:00"),
        base_rule(rule_id="NIGHT", amount=30000, time_from="18:00", time_to="24:00"),
    ]
    result = calculate(facility(rules), conditions(start="17:30", end="18:30"))

    assert_review(result, "base", "rule_missing")
    assert result.items == []


def test_partial_unit_round_up():
    result = calculate(facility(), conditions(start="10:00", end="11:30"))

    assert result.total == 40000


def test_partial_unit_prorate():
    rule = base_rule(partial_unit="prorate")
    result = calculate(facility([rule]), conditions(start="10:00", end="11:30"))

    assert result.total == 30000


def test_partial_unit_prorate_with_fraction_needs_review():
    rule = base_rule(amount=10000, partial_unit="prorate")
    result = calculate(facility([rule]), conditions(start="10:00", end="10:20"))

    assert_review(result, "base", "rule_missing")


def test_partial_unit_unknown_needs_review():
    rule = base_rule(partial_unit=None)
    result = calculate(facility([rule]), conditions(start="10:00", end="11:30"))

    assert_review(result, "base", "rule_missing")


def test_full_units_do_not_need_partial_rule():
    rule = base_rule(partial_unit=None)

    assert calculate(facility([rule]), conditions()).total == 40000


@pytest.mark.parametrize(
    "overrides",
    [{"amount": None}, {"unit_minutes": None}],
)
def test_unknown_base_values_need_review(overrides):
    result = calculate(facility([base_rule(**overrides)]), conditions())

    assert_review(result, "base", "rule_missing")
    assert result.items == []


def test_no_base_rule_points_to_facility_source():
    result = calculate(facility([]), conditions())

    assert_review(result, "base", "rule_missing")
    assert result.review_items[0].source_id == "S-00"


def test_duplicate_base_rules_conflict():
    rules = [base_rule(), base_rule(rule_id="BASE2", amount=30000)]

    assert_review(calculate(facility(rules), conditions()), "base", "rule_conflict")


@pytest.mark.parametrize(
    ("period", "status"),
    [
        ({"effective_from": "2026-11-07"}, "calculated"),
        ({"effective_from": "2026-11-08"}, "needs_review"),
        ({"effective_from": "2025-01-01", "effective_to": "2026-11-07"}, "calculated"),
        ({"effective_from": "2025-01-01", "effective_to": "2026-11-06"}, "needs_review"),
    ],
)
def test_effective_period_boundaries(period, status):
    result = calculate(facility([base_rule(**period)]), conditions())

    assert result.status == status
    if status == "needs_review":
        assert_review(result, "base", "rule_not_in_effect")


def test_rule_replaced_by_new_period():
    rules = [
        base_rule(rule_id="OLD", amount=10000, effective_from="2025-01-01", effective_to="2026-06-30"),
        base_rule(rule_id="NEW", amount=20000, effective_from="2026-07-01"),
    ]
    result = calculate(facility(rules), conditions())

    assert [item.rule_id for item in result.items] == ["NEW"]


def test_discount_on_base_and_lighting():
    rules = facility([base_rule(), lighting_rule()], [discount_rule(applies_to="base_and_lighting")])
    result = calculate(rules, conditions(start="18:00", end="20:00", discounts=["multi_child"]))

    assert amounts(result)["discount"] == -25000


@pytest.mark.parametrize(
    ("rounding", "expected"),
    [("floor_10", -10330), ("ceil_10", -10340), ("round_100", -10300), ("floor_1000", -10000)],
)
def test_discount_rounding(rounding, expected):
    rules = facility(
        [base_rule(amount=31000, unit_minutes=120)],
        [discount_rule(rate="0.3333", rounding=rounding)],
    )
    result = calculate(rules, conditions(discounts=["multi_child"]))

    assert amounts(result)["discount"] == expected


def test_fractional_discount_without_rounding_needs_review():
    rules = facility(discount_rules=[discount_rule(rate="0.33333")])
    result = calculate(rules, conditions(discounts=["multi_child"]))

    assert_review(result, "discount", "rule_missing")
    assert amounts(result) == {"base": 40000}


def test_fixed_discount():
    rules = facility(discount_rules=[discount_rule(rate=None, fixed_amount=3000)])
    result = calculate(rules, conditions(discounts=["multi_child"]))

    assert amounts(result)["discount"] == -3000


def test_fixed_discount_larger_than_target_conflicts():
    rules = facility(discount_rules=[discount_rule(rate=None, fixed_amount=99000)])
    result = calculate(rules, conditions(discounts=["multi_child"]))

    assert_review(result, "discount", "rule_conflict")


@pytest.mark.parametrize(
    "overrides",
    [{"rate": None}, {"applies_to": None}, {"method": None}],
)
def test_unknown_discount_values_need_review(overrides):
    rules = facility(discount_rules=[discount_rule(**overrides)])
    result = calculate(rules, conditions(discounts=["multi_child"]))

    assert_review(result, "discount", "rule_missing")


def test_selected_discount_without_rule_needs_review():
    result = calculate(facility(), conditions(discounts=["multi_child"]))

    assert_review(result, "discount", "rule_missing")


def test_discount_out_of_period():
    rules = facility(discount_rules=[discount_rule(effective_to="2026-01-31")])
    result = calculate(rules, conditions(discounts=["multi_child"]))

    assert_review(result, "discount", "rule_not_in_effect")


def test_duplicate_discount_rules_conflict():
    rules = facility(discount_rules=[discount_rule(), discount_rule(rule_id="DISC2", rate="0.3")])
    result = calculate(rules, conditions(discounts=["multi_child"]))

    assert_review(result, "discount", "rule_conflict")


@pytest.mark.parametrize("stackable", [None, False, True])
def test_multiple_discounts_are_not_calculated(stackable):
    rules = facility(
        discount_rules=[
            discount_rule(stackable=stackable),
            discount_rule(rule_id="DISC2", discount_type="disabled", stackable=stackable),
        ]
    )
    result = calculate(rules, conditions(discounts=["multi_child", "disabled"]))

    assert_review(result, "discount", "rule_missing")
    assert amounts(result) == {"base": 40000}


def test_repeated_discount_type_applied_once():
    rules = facility(discount_rules=[discount_rule()])
    result = calculate(rules, conditions(discounts=["multi_child", "multi_child"]))

    assert amounts(result)["discount"] == -20000


def test_discount_not_calculated_when_target_fee_unknown():
    rules = facility([base_rule(amount=None)], [discount_rule()])
    result = calculate(rules, conditions(discounts=["multi_child"]))

    assert result.status == "needs_review"
    assert [item.target for item in result.review_items] == ["base", "discount"]
    assert result.items == []


def test_base_discount_still_calculated_when_lighting_unknown():
    rules = facility([base_rule(), lighting_rule(amount=None)], [discount_rule()])
    result = calculate(rules, conditions(start="18:00", end="20:00", discounts=["multi_child"]))

    assert_review(result, "lighting", "rule_missing")
    assert amounts(result) == {"base": 40000, "discount": -20000}


def test_unit_straddling_two_lighting_bands_needs_review():
    rules = [
        base_rule(),
        lighting_rule(rule_id="EARLY", time_to="20:00"),
        lighting_rule(rule_id="LATE", amount=7000, time_from="20:00"),
    ]
    result = calculate(facility(rules), conditions(start="19:30", end="20:30"))

    assert_review(result, "lighting", "rule_missing")
    assert amounts(result) == {"base": 20000}


def test_units_inside_adjacent_lighting_bands_are_charged_separately():
    rules = [
        base_rule(),
        lighting_rule(rule_id="EARLY", time_to="20:00"),
        lighting_rule(rule_id="LATE", amount=7000, time_from="20:00"),
    ]
    result = calculate(facility(rules), conditions(start="19:00", end="21:00"))

    assert [(item.rule_id, item.amount) for item in result.items if item.type == "lighting"] == [
        ("EARLY", 5000),
        ("LATE", 7000),
    ]
    assert result.total == 52000


@pytest.mark.parametrize(
    ("amount", "rate", "rounding", "method"),
    [(500, "0.5", "ceil_1000", "onsite"), (800, "1", "ceil_1000", "prepay_refund")],
)
def test_rounded_discount_larger_than_target_conflicts(amount, rate, rounding, method):
    rules = facility(
        [base_rule(amount=amount, unit_minutes=120)],
        [discount_rule(rate=rate, rounding=rounding, method=method)],
    )
    result = calculate(rules, conditions(discounts=["multi_child"]))

    assert_review(result, "discount", "rule_conflict")


def test_full_discount_is_allowed():
    rules = facility(discount_rules=[discount_rule(rate="1")])
    result = calculate(rules, conditions(discounts=["multi_child"]))

    assert (result.status, result.total) == ("calculated", 0)


def test_expired_rule_for_this_day_is_not_replaced_by_other_day_rule():
    rules = [
        base_rule(),
        lighting_rule(rule_id="WEEKEND", day_types=["weekend"], effective_to="2026-06-30"),
        lighting_rule(rule_id="WEEKDAY", day_types=["weekday"]),
    ]
    result = calculate(facility(rules), conditions(day=SATURDAY, start="18:00", end="20:00"))

    assert_review(result, "lighting", "rule_not_in_effect")


def test_expired_rule_partly_covered_by_live_rule_needs_review():
    rules = [
        base_rule(),
        lighting_rule(rule_id="OLD", time_to="20:00", effective_to="2026-06-30"),
        lighting_rule(rule_id="NEW", time_from="20:00"),
    ]
    result = calculate(facility(rules), conditions(start="19:00", end="21:00"))

    assert_review(result, "lighting", "rule_not_in_effect")


def test_expired_rule_fully_replaced_by_live_rule_is_ignored():
    rules = [
        base_rule(),
        lighting_rule(rule_id="OLD", effective_to="2026-06-30"),
        lighting_rule(rule_id="NEW", amount=6000, effective_from="2026-07-01"),
    ]
    result = calculate(facility(rules), conditions(start="18:00", end="20:00"))

    assert result.status == "calculated"
    assert [item.rule_id for item in result.items if item.type == "lighting"] == ["NEW"]


def test_expired_rule_outside_booking_time_is_ignored():
    rules = [base_rule(), lighting_rule(effective_to="2026-06-30")]
    result = calculate(facility(rules), conditions(start="10:00", end="12:00"))

    assert result.status == "calculated"
    assert amounts(result) == {"base": 40000}


@pytest.mark.parametrize(
    "overrides",
    [{"day_types": None}, {"time_from": None, "time_to": None}],
)
def test_unknown_day_or_band_on_base_rule_needs_review(overrides):
    result = calculate(facility([base_rule(**overrides)]), conditions())

    assert_review(result, "base", "rule_missing")
    assert result.items == []


def test_unknown_day_on_lighting_rule_needs_review():
    rules = [base_rule(), lighting_rule(day_types=None)]
    result = calculate(facility(rules), conditions(start="18:00", end="20:00"))

    assert_review(result, "lighting", "rule_missing")


def test_unknown_day_on_rule_outside_booking_time_is_ignored():
    rules = [base_rule(), lighting_rule(day_types=None)]
    result = calculate(facility(rules), conditions(start="10:00", end="12:00"))

    assert result.status == "calculated"


def test_booking_can_end_at_midnight():
    rules = [base_rule(), lighting_rule(time_to="24:00")]
    result = calculate(facility(rules), conditions(start="22:00", end="24:00"))

    assert amounts(result) == {"base": 40000, "lighting": 10000}


def test_every_item_keeps_rule_and_source():
    rules = facility([base_rule(), lighting_rule()], [discount_rule()])
    result = calculate(rules, conditions(start="18:00", end="20:00", discounts=["multi_child"]))

    assert [(item.rule_id, item.source_id) for item in result.items] == [
        ("BASE", "S-01"),
        ("LIGHT", "S-01"),
        ("DISC", "S-02"),
    ]


def test_same_input_gives_same_result():
    rules = facility([base_rule(), lighting_rule()], [discount_rule()])
    request = conditions(start="18:00", end="20:00", discounts=["multi_child"])

    assert calculate(rules, request) == calculate(rules, request)


def assert_not_eligible(result, code, source_id="S-01"):
    assert result.status == "not_eligible"
    assert result.items == []
    assert (result.total, result.payment_due, result.expected_refund, result.net_cost_after_refund) == (None,) * 4
    assert [(item.target, item.code, item.source_id) for item in result.review_items] == [("time", code, source_id)]


def test_fixed_slot_calculated_when_time_matches():
    result = calculate(facility(time_policies=[time_policy()]), conditions(day=MONDAY, start="07:00", end="09:00"))

    assert result.status == "calculated"
    assert amounts(result)["base"] == 40000


@pytest.mark.parametrize(("start", "end"), [("09:00", "10:00"), ("07:00", "08:00"), ("07:00", "14:00")])
def test_time_outside_fixed_slots_not_eligible(start, end):
    result = calculate(facility(time_policies=[time_policy()]), conditions(day=MONDAY, start=start, end=end))

    assert_not_eligible(result, "slot_mismatch")
    assert result.review_items[0].reason.endswith("07:00~09:00, 13:00~14:00, 20:00~22:00")


@pytest.mark.parametrize(("start", "end"), [("10:00", "11:00"), ("10:30", "12:30")])
def test_flexible_allowed_duration_calculated(start, end):
    result = calculate(facility(time_policies=[flexible_policy()]), conditions(day=MONDAY, start=start, end=end))

    assert result.status == "calculated"


def test_flexible_duration_not_allowed():
    result = calculate(facility(time_policies=[flexible_policy()]), conditions(day=MONDAY, start="10:00", end="13:00"))

    assert_not_eligible(result, "duration_not_allowed")
    assert result.review_items[0].reason == "이용 시간은 60분, 120분 중에서 선택할 수 있습니다."


@pytest.mark.parametrize(("start", "end"), [("07:00", "09:00"), ("21:00", "23:00")])
def test_outside_operating_hours_not_eligible(start, end):
    result = calculate(facility(time_policies=[flexible_policy()]), conditions(day=MONDAY, start=start, end=end))

    assert_not_eligible(result, "outside_hours")


def test_time_check_skips_discount_and_fee_calculation():
    rules = facility(discount_rules=[discount_rule()], time_policies=[time_policy()])
    result = calculate(rules, conditions(day=MONDAY, start="09:00", end="10:00", discounts=["multi_child"]))

    assert_not_eligible(result, "slot_mismatch")


def test_policy_for_other_sport_ignored():
    result = calculate(facility(time_policies=[time_policy(sport="tennis")]), conditions(day=MONDAY))

    assert result.status == "calculated"


def test_policy_not_in_effect_ignored():
    # 동절기 회차는 여름 이용일에 적용하지 않는다. 이용시간 확인은 요금 규정 확인에 맡긴다.
    policy = time_policy(effective_to="2026-10-31")
    result = calculate(facility(time_policies=[policy]), conditions(day=MONDAY, start="09:00", end="10:00"))

    assert result.status == "calculated"


def test_conflicting_policies_need_review():
    policies = [time_policy(), flexible_policy(policy_id="TIME-2")]
    result = calculate(facility(time_policies=policies), conditions(day=MONDAY, start="07:00", end="09:00"))

    assert result.status == "needs_review"
    assert [(item.target, item.code) for item in result.review_items] == [("time", "rule_conflict")]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (dict(slots=[]), "slots가 필요"),
        (dict(selection="flexible", slots=[]), "allowed_minutes가 필요"),
        (dict(slots=[{"start_time": "09:00", "end_time": "09:00"}]), "종료 시간은 시작 시간보다"),
        (dict(open_time="08:00"), "함께 입력"),
    ],
)
def test_invalid_time_policy_rejected(overrides, message):
    with pytest.raises(ValueError, match=message):
        time_policy(**overrides)


def test_time_policy_source_must_be_registered():
    with pytest.raises(ValueError, match="등록되지 않은 출처"):
        facility(time_policies=[time_policy(source_id="S-99")])
