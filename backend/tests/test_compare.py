from datetime import date

import pytest
from test_engine import MONDAY, SATURDAY, base_rule, calendar, conditions, discount_rule, facility, time_policy

from app.compare import compare_facility
from app.models import ClosureRule, Holiday


def source_ids(result) -> list[str]:
    return [source.source_id for source in result.sources]


def test_known_documents_listed_without_review():
    rules = facility(discount_rules=[discount_rule(required_documents=["서류"])])
    result = compare_facility(rules, conditions(discounts=["multi_child"]))

    assert result.checklist == ["서류"]
    assert result.checklist_review_items == []


def test_no_documents_required_is_not_a_review():
    rules = facility(discount_rules=[discount_rule(required_documents=[])])
    result = compare_facility(rules, conditions(discounts=["multi_child"]))

    assert result.checklist == []
    assert result.checklist_review_items == []


def test_unknown_documents_are_reported_with_source_and_keep_fee():
    rules = facility(discount_rules=[discount_rule(required_documents=None)])
    result = compare_facility(rules, conditions(discounts=["multi_child"]))

    assert result.fee.status == "calculated"
    assert result.checklist == []
    review = result.checklist_review_items[0]
    assert (review.code, review.target, review.source_id) == ("rule_missing", "checklist", "S-02")
    assert "S-02" in source_ids(result)


def test_discount_without_rule_points_checklist_to_facility_source():
    result = compare_facility(facility(), conditions(discounts=["multi_child"]))

    assert result.checklist_review_items[0].source_id == "S-00"
    assert "S-00" in source_ids(result)


def test_every_discount_document_keeps_its_source():
    rules = facility(
        [base_rule(source_id="S-00")],
        [
            discount_rule(source_id="S-01", required_documents=["첫째 서류"]),
            discount_rule(rule_id="DISC2", discount_type="disabled", source_id="S-02", required_documents=["둘째 서류"]),
        ],
    )
    result = compare_facility(rules, conditions(discounts=["multi_child", "disabled"]))

    assert result.fee.status == "needs_review"
    assert result.checklist == ["첫째 서류", "둘째 서류"]
    assert source_ids(result) == ["S-00", "S-01", "S-02"]


def test_no_discount_selected_gives_empty_checklist():
    rules = facility(discount_rules=[discount_rule(required_documents=None)])
    result = compare_facility(rules, conditions())

    assert result.checklist == []
    assert result.checklist_review_items == []


def test_holiday_source_listed_when_date_is_holiday():
    result = compare_facility(facility(holidays=[MONDAY]), conditions(day=MONDAY))

    assert "S-HOLIDAY" in source_ids(result)


def test_holiday_source_not_listed_on_ordinary_day():
    result = compare_facility(facility(), conditions(day=MONDAY))

    assert "S-HOLIDAY" not in source_ids(result)


def closure(type_, value, **overrides) -> ClosureRule:
    values = dict(type=type_, value=value, note="정기 휴장", source_id="S-02", effective_from="2026-01-01")
    return ClosureRule(**(values | overrides))


def with_closures(rules, *closures):
    return rules.model_copy(update={"closure_rules": list(closures)})


def test_closed_on_annual_date_is_not_calculated():
    rules = with_closures(facility(), closure("annual_date", SATURDAY.strftime("%m-%d"), note="개장 기념일 휴장"))
    result = compare_facility(rules, conditions(day=SATURDAY))

    assert result.fee.status == "not_eligible"
    assert result.fee.items == [] and result.fee.total is None and result.fee.payment_due is None
    review = result.fee.review_items[0]
    assert (review.code, review.target, review.source_id) == ("facility_closed", "time", "S-02")
    assert "개장 기념일 휴장" in review.reason
    assert "S-02" in source_ids(result)


def test_closed_on_exact_date():
    rules = with_closures(facility(), closure("exact_date", SATURDAY.isoformat()))

    assert compare_facility(rules, conditions(day=SATURDAY)).fee.status == "not_eligible"


def test_closure_outside_its_period_is_ignored():
    rules = with_closures(
        facility(), closure("exact_date", SATURDAY.isoformat(), effective_from="2025-01-01", effective_to="2025-12-31")
    )

    assert compare_facility(rules, conditions(day=SATURDAY)).fee.status == "calculated"


def test_holiday_closure_uses_holiday_calendar_name():
    lunar = date(2027, 2, 7)
    holidays = calendar().model_copy(update={"holidays": [Holiday(date=lunar, name="설날")]})
    rules = facility(holiday_calendar=holidays).model_copy(
        update={"closure_rules": [closure("holiday_code", "lunar_new_year_day", note="설날 당일 휴장")]}
    )

    assert compare_facility(rules, conditions(day=lunar)).fee.status == "not_eligible"
    # 설날 전날은 휴장 규정에 없으므로 계산한다.
    assert compare_facility(rules, conditions(day=date(2027, 2, 6))).fee.status == "calculated"


def test_holiday_closure_outside_calendar_needs_review():
    narrow = calendar(covered_from="2026-01-01", covered_to="2026-06-30")
    rules = facility(holiday_calendar=narrow).model_copy(
        update={"closure_rules": [closure("holiday_code", "chuseok_day")]}
    )
    fee = compare_facility(rules, conditions(day=SATURDAY)).fee

    assert fee.status == "needs_review"
    assert fee.total is None and fee.payment_due is None and fee.online_prepay is None
    assert [(r.code, r.target) for r in fee.review_items][-1] == ("rule_missing", "time")


def test_not_eligible_time_is_kept_when_holiday_closure_unknown():
    narrow = calendar(covered_from="2026-01-01", covered_to="2026-06-30")
    # 10:00~12:00은 지정 회차가 아니다.
    rules = facility(holiday_calendar=narrow, time_policies=[time_policy()]).model_copy(
        update={"closure_rules": [closure("holiday_code", "chuseok_day")]}
    )
    fee = compare_facility(rules, conditions(day=SATURDAY)).fee

    assert [r.code for r in fee.review_items] == ["slot_mismatch"]
    assert fee.status == "not_eligible"


def test_closed_holiday_does_not_cite_holiday_source():
    rules = with_closures(facility(holidays=[SATURDAY]), closure("exact_date", SATURDAY.isoformat()))
    result = compare_facility(rules, conditions(day=SATURDAY))

    assert result.fee.status == "not_eligible"
    assert "S-HOLIDAY" not in source_ids(result)


@pytest.mark.parametrize(
    ("type_", "value"),
    [("annual_date", "1-1"), ("annual_date", "02-30"), ("exact_date", "2027/02/07"), ("holiday_code", "seollal")],
)
def test_malformed_closure_value_is_rejected(type_, value):
    with pytest.raises(ValueError, match="휴장 규정 값"):
        closure(type_, value)


def test_leap_day_annual_closure_is_allowed():
    assert closure("annual_date", "02-29").value == "02-29"


def test_application_deadline_and_guardian_note_join_checklist():
    rule = discount_rule(required_documents=["서류"], application_deadline="이용 전 게시판 접수", guardian_note="관계 증빙")
    result = compare_facility(facility(discount_rules=[rule]), conditions(discounts=["multi_child"]))

    assert result.checklist == ["서류", "감면 신청 기한: 이용 전 게시판 접수", "보호자 동반 시: 관계 증빙"]
    assert "S-02" in source_ids(result)


def test_deadline_without_documents_still_reports_unknown_documents():
    rule = discount_rule(required_documents=None, application_deadline="이용 전 게시판 접수")
    result = compare_facility(facility(discount_rules=[rule]), conditions(discounts=["multi_child"]))

    assert result.checklist == ["감면 신청 기한: 이용 전 게시판 접수"]
    assert [item.target for item in result.checklist_review_items] == ["checklist"]
