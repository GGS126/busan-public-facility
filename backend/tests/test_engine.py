from datetime import date

import pytest

from app.engine import calculate
from app.models import Conditions, DiscountRule, FacilityRules, FeeRule, Holiday, HolidayCalendar, Source

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


def calendar(holidays=(), covered_from="2026-01-01", covered_to="2027-12-31") -> HolidayCalendar:
    return HolidayCalendar(
        covered_from=covered_from,
        covered_to=covered_to,
        holidays=[Holiday(date=day, name="가상 공휴일") for day in holidays],
        source=Source(source_id="S-HOLIDAY", url="https://example.com", checked_at="2026-11-05", license="가상"),
    )


def facility(fee_rules=None, discount_rules=None, holidays=(), holiday_calendar=None) -> FacilityRules:
    return FacilityRules(
        facility_id="F",
        name="가상 시설",
        source_id="S-00",
        holiday_calendar=holiday_calendar or calendar(holidays),
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


def test_weekend_holiday_matches_weekend_rate():
    rules = [
        base_rule(rule_id="WEEKDAY", amount=10000, day_types=["weekday"]),
        base_rule(rule_id="WEEKEND", amount=30000, day_types=["weekend"]),
    ]
    result = calculate(facility(rules, holidays=[SATURDAY]), conditions(day=SATURDAY))

    assert amounts(result)["base"] == 60000


def test_day_outside_calendar_needs_review_when_holiday_changes_rate():
    rules = [
        base_rule(rule_id="WEEKDAY", amount=10000, day_types=["weekday"]),
        base_rule(rule_id="HOLIDAY", amount=30000, day_types=["holiday"]),
    ]
    outside = calendar(covered_from="2026-01-01", covered_to="2026-10-31")
    result = calculate(facility(rules, holiday_calendar=outside), conditions(day=MONDAY))

    assert_review(result, "base", "rule_missing")
    assert result.review_items[0].reason == "이용일이 공휴일인지 확인할 수 없습니다."
    assert result.review_items[0].source_id == "S-00"


def test_day_outside_calendar_calculated_when_rate_is_same_every_day():
    outside = calendar(covered_from="2026-01-01", covered_to="2026-10-31")
    result = calculate(facility(holiday_calendar=outside), conditions(day=MONDAY))

    assert result.status == "calculated"
    assert amounts(result)["base"] == 40000


def test_holiday_outside_covered_range_rejected():
    with pytest.raises(ValueError, match="기간 밖의 공휴일"):
        calendar(holidays=[date(2028, 1, 1)])


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
