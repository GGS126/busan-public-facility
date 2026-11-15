"""팀 DB(SQLite)의 실제 규정을 규칙 엔진으로 계산해 database/의 정답 사례와 비교한다(AC-006)."""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from app.engine import calculate
from app.models import Conditions
from app.repository import load_sqlite_rule_data

DATABASE_DIR = Path(__file__).resolve().parents[2] / "database"
CASE_FILES = ["test_cases.json", "samrak_test_cases.json", "gudeok_test_cases.json"]
WEEKDAY, WEEKEND = date(2026, 11, 9), date(2026, 11, 7)

# 정답 사례 중 요금 계산 API의 범위가 아닌 것. 사유가 없어지면 이 목록에서 빼고 검증한다.
NOT_FEE_CASES = {
    "T09", "T10", "T11", "T12", "S05", "S06", "S07", "gudeok_cancel_d1", "gudeok_rain_d0",
}  # 취소·환불 금액은 계산하지 않고 terms 문구로만 안내한다.

# 시간이 적혀 있지 않은 사례는 사례 설명의 요금(기본요금, 조명료 유무, 1시간 요금 미확인)에 맞는 시간으로 계산한다.
CASE_TIMES = {
    "T_rounding_unverified": ("07:00", "09:00"),
    "H_OPTION_30": ("07:00", "09:00"),
    "H_OPTION_60": ("07:00", "09:00"),
    "S_rounding_unverified": ("08:00", "10:00"),
    "gudeok_discount": ("10:00", "12:00"),
    "gudeok_companion_eligible_only": ("10:00", "12:00"),
    "gudeok_holder_eligible_night": ("18:00", "20:00"),
    "gudeok_holder_eligible_one_hour": ("10:00", "11:00"),
    "gudeok_rounding_unverified": ("10:00", "12:00"),
}


@pytest.fixture(scope="module")
def facilities(tmp_path_factory):
    sys.path.insert(0, str(DATABASE_DIR))
    try:
        from build_db import build
    finally:
        sys.path.remove(str(DATABASE_DIR))
    path = build(tmp_path_factory.mktemp("db") / "facilities.sqlite3")
    return {facility.facility_id: facility for facility in load_sqlite_rule_data(path).facilities}


def load_cases():
    return [
        pytest.param(case, id=case["id"])
        for name in CASE_FILES
        for case in json.loads((DATABASE_DIR / name).read_text(encoding="utf-8"))["cases"]
    ]


def slot_times(facility, slot: int) -> tuple[str, str]:
    policy = facility.time_policies[0]
    selected = policy.slots[slot - 1]
    return selected.start_time, selected.end_time


def conditions_for(case, facility) -> Conditions:
    inputs = case["inputs"]
    if "slot" in inputs:
        start, end = slot_times(facility, inputs["slot"])
    elif "start" in inputs:
        start, end = inputs["start"], inputs["end"]
    else:
        start, end = CASE_TIMES[case["id"]]

    if "use_date" in inputs:
        day = date.fromisoformat(inputs["use_date"])
    else:
        day = WEEKEND if inputs.get("is_weekend_or_holiday") else WEEKDAY

    holder = inputs.get("reservation_holder_eligible", False)
    # 대표자도 감면 대상 인원에 포함한다.
    eligible = inputs.get("eligible_count") or (1 if holder else 0)
    discounts = (
        [{"type": inputs.get("discount_category", "disabled"), "count": eligible, "holder": holder}]
        if eligible or holder
        else []
    )
    headcount = inputs.get("party_size") or (4 if discounts else None)
    return Conditions(
        sport=facility.time_policies[0].sport if facility.time_policies else "tennis",
        date=day,
        start_time=start,
        end_time=end,
        headcount=headcount,
        discounts=discounts,
        optional_lighting_minutes=inputs.get("optional_lighting_minutes") or inputs.get("lighting_minutes") or 0,
        source="direct",
    )


@pytest.mark.parametrize("case", load_cases())
def test_matches_official_case(case, facilities):
    if case["id"] in NOT_FEE_CASES:
        pytest.skip("요금 계산 범위 밖")

    expected = case["expected"]
    facility = facilities[case["inputs"]["facility_id"]]
    result = calculate(facility, conditions_for(case, facility))

    if expected.get("status") == "needs_review":
        assert result.status == "needs_review"
        assert result.net_cost_after_refund is None
        return

    assert result.status == "calculated", result.review_items
    optional_ids = {rule.rule_id for rule in facility.fee_rules if rule.type == "optional_lighting"}
    by_type = {}
    for item in result.items:
        if item.rule_id not in optional_ids:
            by_type[item.type] = by_type.get(item.type, 0) + item.amount
    checks = {
        "initial_payment_won": result.payment_due,
        "optional_lighting_on_site_won": result.onsite_payment,
        "discount_refund_won": result.expected_refund,
        "final_expected_cost_won": result.net_cost_after_refund,
        "total_fee_won": result.payment_due,
        "base_court_won": by_type.get("base", 0),
        "mandatory_lighting_won": by_type.get("lighting", 0),
        "lighting_won": by_type.get("lighting", 0),
    }
    for key, actual in checks.items():
        if key in expected:
            assert actual == expected[key], key


def test_every_case_is_checked_or_listed():
    ids = {param.id for param in load_cases()}
    assert (NOT_FEE_CASES | CASE_TIMES.keys()) <= ids


def test_slot_mismatch_not_eligible(facilities):
    rules = facilities["busan_haeundae_arboretum_tennis"]
    result = calculate(
        rules, Conditions(sport="tennis", date=WEEKDAY, start_time="08:00", end_time="10:00", source="direct")
    )

    assert result.status == "not_eligible"
    assert result.review_items[0].code == "slot_mismatch"


def test_discount_types_without_count_needs_review(facilities):
    rules = facilities["busan_samrak_ecopark_tennis"]
    result = calculate(
        rules,
        Conditions(sport="tennis", date=WEEKDAY, start_time="08:00", end_time="10:00", discount_types=["disabled"], source="direct"),
    )

    assert result.status == "needs_review"
    assert result.review_items[0].target == "discount"


def test_terms_and_sources_from_database(facilities):
    rules = facilities["busan_samrak_ecopark_tennis"]

    assert rules.terms.booking_open == "이용일 60일 전부터 2일 전까지 온라인 신청"
    assert rules.terms.refund == "3일 전까지 취소 100%, 2일 전 취소 90%, 1일 전 취소 80%, 당일 취소 0%"
    assert [source.source_id for source in rules.sources] == ["busan_reserve_395_winter_2026"]
