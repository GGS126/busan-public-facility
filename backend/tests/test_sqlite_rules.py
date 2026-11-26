"""팀 DB(SQLite)의 실제 규정을 규칙 엔진으로 계산해 database/의 정답 사례와 비교한다(AC-006)."""

import json
import sqlite3
import sys
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.compare import compare_facility
from app.detail import facility_detail
from app.engine import calculate
from app.models import Conditions
from app.refund import estimate_cancel_refund
from app.repository import load_sqlite_rule_data

DATABASE_DIR = Path(__file__).resolve().parents[2] / "database"
CASE_FILES = ["test_cases.json", "samrak_test_cases.json", "gudeok_test_cases.json"]
WEEKDAY, WEEKEND = date(2026, 11, 9), date(2026, 11, 7)

# 취소·환불 정답 사례. 요금 대신 cancel_refund로 검증한다. 사례에 시간이 없어 시설의 평일 기본 회차로 예약한다.
REFUND_CASE_TIMES = {
    "busan_haeundae_arboretum_tennis": ("07:00", "09:00"),
    "busan_samrak_ecopark_tennis": ("08:00", "10:00"),
    "busan_gudeok_stadium_tennis": ("10:00", "12:00"),
}
REFUND_CASES = {"T09", "T10", "T11", "T12", "S05", "S06", "S07", "gudeok_cancel_d1", "gudeok_rain_d0"}

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


def build_database(directory: Path) -> Path:
    sys.path.insert(0, str(DATABASE_DIR))
    try:
        from build_db import build
    finally:
        sys.path.remove(str(DATABASE_DIR))
    return build(directory / "facilities.sqlite3")


@pytest.fixture(scope="module")
def facilities(tmp_path_factory):
    path = build_database(tmp_path_factory.mktemp("db"))
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
    if case["id"] in REFUND_CASES:
        check_refund_case(case, facilities)
        return

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
        "total_fee_won": result.total,
        "base_court_won": by_type.get("base", 0),
        "mandatory_lighting_won": by_type.get("lighting", 0),
        "lighting_won": by_type.get("lighting", 0),
    }
    for key, actual in checks.items():
        if key in expected:
            assert actual == expected[key], key


def check_refund_case(case, facilities):
    inputs, expected = case["inputs"], case["expected"]
    facility = facilities[inputs["facility_id"]]
    reason = inputs.get("reason", "user_cancel")
    cancellation = {"reason": reason}
    if reason == "user_cancel":
        cancellation["cancel_date"] = WEEKDAY - timedelta(days=inputs["days_before"])
    start, end = REFUND_CASE_TIMES[facility.facility_id]
    conditions = Conditions(
        sport="tennis", date=WEEKDAY, start_time=start, end_time=end, cancellation=cancellation, source="direct"
    )
    result = compare_facility(facility, conditions)

    refund = result.cancel_refund
    assert refund.status == "calculated", refund.review_items
    assert refund.rate_percent == expected["refund_percent"]
    if "initial_paid_won" in inputs:
        assert result.fee.online_prepay == inputs["initial_paid_won"]
    if "refund_won" in expected:
        assert refund.refund_amount == expected["refund_won"]
    if "final_cost_won" in expected:
        assert refund.cost_after_refund == expected["final_cost_won"]
    assert refund.note
    assert refund.source_id in {source.source_id for source in result.sources}


def test_every_case_is_checked_or_listed():
    ids = {param.id for param in load_cases()}
    assert (REFUND_CASES | CASE_TIMES.keys()) <= ids


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
    terms = rules.terms_on(WEEKDAY)

    assert terms.booking_open == "이용일 60일 전부터 2일 전까지 온라인 신청"
    assert terms.refund == "3일 전까지 취소 100%, 2일 전 취소 90%, 1일 전 취소 80%, 당일 취소 0%"
    assert [source.source_id for source in rules.sources] == ["busan_reserve_395_winter_2026"]


@pytest.mark.parametrize(("start", "end"), [("10:00", "13:00"), ("08:00", "11:00")])
def test_gudeok_over_two_hours_not_eligible(facilities, start, end):
    rules = facilities["busan_gudeok_stadium_tennis"]
    result = calculate(rules, Conditions(sport="tennis", date=WEEKDAY, start_time=start, end_time=end, source="direct"))

    assert result.status == "not_eligible"
    assert result.review_items[0].code == "duration_not_allowed"
    assert result.review_items[0].source_id == "busan_reserve_472_2026winter"


def test_gudeok_outside_operating_hours_not_eligible(facilities):
    rules = facilities["busan_gudeok_stadium_tennis"]
    result = calculate(rules, Conditions(sport="tennis", date=WEEKDAY, start_time="07:00", end_time="09:00", source="direct"))

    assert result.status == "not_eligible"
    assert result.review_items[0].code == "outside_hours"


@pytest.fixture(scope="module")
def two_period_facility(tmp_path_factory):
    """같은 출처를 쓰는 규정 기간이 둘이고, 출처와 예약 조건이 다른 기간이 하나 더 있는 시설."""
    path = build_database(tmp_path_factory.mktemp("db"))
    with closing(sqlite3.connect(path)) as con, con:
        con.execute(
            "INSERT INTO sources (id, url, title, checked_on, verification_level) VALUES (?, ?, ?, ?, ?)",
            ("haeundae_2027h1", "https://example.com/2027h1", "2027년 상반기", "2026-12-20", "official_page_verified"),
        )
        con.executemany(
            "INSERT INTO rule_sets (id, facility_id, source_id, effective_from, effective_to, status)"
            " VALUES (?, ?, ?, ?, ?, 'confirmed')",
            [
                ("haeundae_2026h1", "busan_haeundae_arboretum_tennis", "busan_reserve_619_2026h2", "2026-01-01", "2026-06-30"),
                ("haeundae_2027h1", "busan_haeundae_arboretum_tennis", "haeundae_2027h1", "2027-01-01", "2027-06-30"),
            ],
        )
        con.execute("INSERT INTO reservation_rules VALUES ('haeundae_2027h1', 30, 2, 5, NULL)")
    return {f.facility_id: f for f in load_sqlite_rule_data(path).facilities}["busan_haeundae_arboretum_tennis"]


def test_rule_sets_sharing_source_load(two_period_facility):
    ids = [source.source_id for source in two_period_facility.sources]

    assert sorted(ids) == ["busan_reserve_619_2026h2", "haeundae_2027h1"]


def test_terms_and_source_follow_use_date(two_period_facility):
    rules = two_period_facility
    later = date(2027, 2, 1)

    assert rules.terms_on(WEEKDAY).booking_open == "이용일 14일 전부터 1일 전까지 온라인 신청"
    assert rules.terms_on(WEEKDAY).source_id == "busan_reserve_619_2026h2"
    assert rules.terms_on(later).booking_open == "이용일 30일 전부터 2일 전까지 온라인 신청"
    assert rules.terms_on(later).source_id == "haeundae_2027h1"
    # 근거 규정이 없을 때 안내하는 출처도 이용일의 규정 기간을 따른다.
    assert rules.source_on(WEEKDAY) == "busan_reserve_619_2026h2"
    assert rules.source_on(later) == "haeundae_2027h1"


def test_compare_shows_terms_and_sources_of_use_date(two_period_facility):
    later = Conditions(sport="tennis", date=date(2027, 2, 1), start_time="07:00", end_time="09:00", source="direct")
    result = compare_facility(two_period_facility, later)

    assert result.terms.source_id == "haeundae_2027h1"
    assert result.terms.cancel_deadline == "이용일 5일 전까지 온라인 취소"
    # 2027년 요금 규정은 없으므로 '확인 필요'의 근거로 만료된 요금 규정의 출처도 함께 보인다.
    assert result.fee.review_items[0].code == "rule_not_in_effect"
    assert {source.source_id for source in result.sources} == {"haeundae_2027h1", "busan_reserve_619_2026h2"}


# 정답 사례가 아직 없는 시설(PR #27). DB 요금표 그대로 변환되는지 확인한다.
@pytest.mark.parametrize(
    ("facility_id", "sport", "day", "start", "end", "lighting_minutes", "expected"),
    [
        ("busan_hwamyeong_ecopark_night_soccer", "soccer", WEEKDAY, "18:00", "21:00", 0, (20000, 30000, 50000, 0)),
        ("busan_haeundae_arboretum_soccer", "soccer", WEEKDAY, "19:00", "22:00", 0, (120000, 20000, 140000, 0)),
        ("busan_haeundae_arboretum_soccer", "soccer", WEEKDAY, "16:00", "19:00", 60, (120000, 10000, 120000, 10000)),
        # 19:00~20:00 선택 조명 60분은 현장 결제, 20:00~22:00 필수 조명 20,000원은 회차 요금과 함께 선결제(database/README.md)
        ("busan_haeundae_arboretum_soccer", "soccer", WEEKDAY, "19:00", "22:00", 60, (120000, 30000, 140000, 10000)),
        ("busan_samrak_ecopark_soccer", "soccer", WEEKEND, "08:00", "11:00", 0, (30000, 0, 30000, 0)),
        ("busan_hwamyeong_ecopark_tennis", "tennis", WEEKDAY, "08:00", "10:00", 0, (6000, 0, 6000, 0)),
    ],
)
def test_added_facilities_follow_database(facilities, facility_id, sport, day, start, end, lighting_minutes, expected):
    conditions = Conditions(
        sport=sport, date=day, start_time=start, end_time=end, optional_lighting_minutes=lighting_minutes, source="direct"
    )
    result = calculate(facilities[facility_id], conditions)

    by_type = {}
    for item in result.items:
        by_type[item.type] = by_type.get(item.type, 0) + item.amount
    assert result.status == "calculated", result.review_items
    assert (by_type["base"], by_type.get("lighting", 0), result.payment_due, result.onsite_payment) == expected


def test_optional_lighting_longer_than_its_band_rejected(facilities):
    # 해운대 축구 19:00~22:00 회차의 선택 조명은 시간대(07:00~20:00)와 겹치는 19:00~20:00의 60분까지다.
    conditions = Conditions(
        sport="soccer", date=WEEKDAY, start_time="19:00", end_time="22:00", optional_lighting_minutes=90, source="direct"
    )
    result = calculate(facilities["busan_haeundae_arboretum_soccer"], conditions)

    assert result.status == "needs_review"
    assert (result.review_items[0].target, result.review_items[0].code) == ("lighting", "duration_not_allowed")


@pytest.mark.parametrize(
    ("facility_id", "start", "end", "minutes", "expected"),
    [
        # 구덕은 선택 조명이 없어 입력한 조명 시간을 쓰지 않고 필수 조명료만 계산한다.
        ("busan_gudeok_stadium_tennis", "18:00", "20:00", 60, ("calculated", None)),
        # 해운대 20:00~22:00 회차는 조명이 회차 요금에 포함돼 선택 조명을 고를 수 없다.
        ("busan_haeundae_arboretum_tennis", "20:00", "22:00", 30, ("needs_review", "duration_not_allowed")),
    ],
)
def test_optional_lighting_minutes_in_multi_facility_compare(facilities, facility_id, start, end, minutes, expected):
    conditions = Conditions(
        sport="tennis", date=WEEKDAY, start_time=start, end_time=end, optional_lighting_minutes=minutes, source="direct"
    )
    result = calculate(facilities[facility_id], conditions)

    assert (result.status, result.review_items[0].code if result.review_items else None) == expected


def test_gudeok_lighting_payment_unverified(facilities):
    # 구덕 야간 조명료는 결제 시점·장소가 공식 자료에 없어 최초 납부액으로 확정하지 않는다.
    conditions = Conditions(sport="tennis", date=WEEKDAY, start_time="18:00", end_time="20:00", source="direct")
    result = calculate(facilities["busan_gudeok_stadium_tennis"], conditions)

    assert result.status == "calculated"
    assert (result.total, result.payment_due, result.onsite_payment, result.payment_unverified) == (28000, None, 0, 20000)
    # 기본요금 8,000원은 예약할 때 온라인으로 낸다.
    assert result.online_prepay == 8000


def test_facility_detail_flexible(facilities):
    detail = facility_detail(facilities["busan_gudeok_stadium_tennis"], WEEKDAY)

    assert detail.address == "부산 서구 망양로 57 (서대신동3가, 구덕운동장)"
    assert detail.booking_url == "https://reserve.busan.go.kr/rent/view?resveGroupSn=475&progrmSn=472"
    assert (detail.operating_hours.open_time, detail.operating_hours.close_time) == ("08:00", "22:00")
    assert detail.closure_note == "연중무휴(명절 등 별도 공지일 제외)"
    [option] = detail.time_options
    assert (option.selection, option.max_minutes, option.slots) == ("flexible", 120, [])
    assert [source.source_id for source in detail.sources] == ["busan_reserve_472_2026winter"]


def test_facility_detail_fixed_slots(facilities):
    detail = facility_detail(facilities["busan_samrak_ecopark_tennis"], WEEKDAY)

    [option] = detail.time_options
    assert [(slot.start_time, slot.end_time) for slot in option.slots] == [
        ("08:00", "10:00"), ("10:00", "12:00"), ("13:00", "15:00"), ("15:00", "17:00"),
    ]


def test_facility_detail_outside_rule_period_shows_unknown(facilities):
    # 동절기 규정이 끝난 날에는 지난 회차나 휴장 안내를 보여 주지 않는다.
    detail = facility_detail(facilities["busan_samrak_ecopark_tennis"], date(2027, 5, 1))

    assert detail.time_options == []
    assert detail.closure_note is None
    assert detail.booking_url is not None
    # 만료된 동절기 규정의 출처와 종목도 보여 주지 않는다.
    assert detail.source_id is None
    assert detail.sources == []
    assert detail.sports == []


def test_facility_detail_follows_use_date(two_period_facility):
    detail = facility_detail(two_period_facility, date(2027, 2, 1))

    assert detail.source_id == "haeundae_2027h1"
    assert [source.source_id for source in detail.sources] == ["haeundae_2027h1"]


def test_facility_detail_api_with_database(facilities, monkeypatch):
    # 실제 DB의 모든 시설을 API로 조회한다. 날짜를 생략하면 오늘 기준이다.
    from fastapi.testclient import TestClient

    from app import main

    monkeypatch.setattr(main, "facilities", facilities)
    client = TestClient(main.app)
    for facility_id in facilities:
        response = client.get(f"/api/facilities/{facility_id}")

        assert response.status_code == 200, facility_id
        detail = response.json()
        assert detail["facility_id"] == facility_id
        used = {detail["source_id"], *(option["source_id"] for option in detail["time_options"])} - {None}
        assert used == {source["source_id"] for source in detail["sources"]}


def test_period_without_source_uses_facility_source(two_period_facility):
    # 유효한 기간에 출처가 비어 있으면 기간 밖처럼 숨기지 않고 시설 출처를 보여 준다.
    periods = [
        period.model_copy(update={"source_id": None}) if period.effective_from == date(2027, 1, 1) else period
        for period in two_period_facility.terms_by_period
    ]
    rules = two_period_facility.model_copy(update={"terms_by_period": periods})
    detail = facility_detail(rules, date(2027, 2, 1))

    assert detail.source_id == rules.source_id
    assert rules.source_id in [source.source_id for source in detail.sources]


def test_facility_detail_sports_follow_rule_months(facilities):
    # 적용 기간 안이어도 그 달에 기본요금 규정이 없는 종목은 보여 주지 않는다.
    rules = facilities["busan_samrak_ecopark_tennis"]
    winter_only = rules.model_copy(
        update={
            "fee_rules": [
                r.model_copy(update={"months": [11, 12, 1, 2]}) if r.type == "base" else r for r in rules.fee_rules
            ]
        }
    )

    assert facility_detail(winter_only, WEEKDAY).sports == ["tennis"]
    assert facility_detail(winter_only, date(2027, 3, 10)).sports == []


def cancel_refund(facility, start, end, cancellation, **conditions):
    conditions = Conditions(
        sport="tennis", date=WEEKDAY, start_time=start, end_time=end, cancellation=cancellation, source="direct",
        **conditions,
    )
    return compare_facility(facility, conditions).cancel_refund


def test_same_day_cancel_without_rule_needs_review(facilities):
    # 구덕은 당일 사용자 취소의 환불 규정이 없다(당일 온라인 취소 불가). 다른 날의 환불률로 대신하지 않는다.
    refund = cancel_refund(
        facilities["busan_gudeok_stadium_tennis"], "10:00", "12:00", {"reason": "user_cancel", "cancel_date": WEEKDAY}
    )

    assert refund.status == "needs_review"
    assert (refund.days_before, refund.rate_percent, refund.refund_amount) == (0, None, None)
    assert refund.review_items[0].code == "rule_missing"
    assert refund.review_items[0].target == "refund"


def test_onsite_payment_refund_needs_review(facilities):
    # 해운대 선택 조명료는 현장에서 따로 낸다. 취소 시 그 금액을 어떻게 처리하는지는 공식 자료에 없다.
    refund = cancel_refund(
        facilities["busan_haeundae_arboretum_tennis"], "18:00", "20:00",
        {"cancel_date": WEEKDAY - timedelta(days=2)}, optional_lighting_minutes=60,
    )

    assert refund.status == "needs_review"
    assert refund.rate_percent == 90
    assert refund.review_items[0].code == "amount_unverified"


def test_unverified_payment_refund_needs_review(facilities):
    # 구덕 야간 조명료는 결제 방식이 확인되지 않았다.
    refund = cancel_refund(
        facilities["busan_gudeok_stadium_tennis"], "18:00", "20:00", {"cancel_date": WEEKDAY - timedelta(days=1)}
    )

    assert refund.status == "needs_review"
    assert refund.review_items[0].code == "amount_unverified"


def test_discount_refund_with_cancel_needs_review(facilities):
    refund = cancel_refund(
        facilities["busan_samrak_ecopark_tennis"], "08:00", "10:00", {"cancel_date": WEEKDAY - timedelta(days=3)},
        headcount=4, discounts=[{"type": "disabled", "count": 2}],
    )

    assert refund.status == "needs_review"
    assert "감면 환급" in refund.review_items[0].reason


def test_refund_with_fraction_of_won_needs_review(facilities):
    # 실제 DB 요금은 모두 100원 단위라 끝전이 생기지 않아, 6,005원을 낸 것으로 바꿔 확인한다.
    # 6,005원의 90%는 5,404.5원이라 원 미만 처리 기준이 있어야 금액을 정할 수 있다.
    facility = facilities["busan_samrak_ecopark_tennis"]
    conditions = Conditions(
        sport="tennis", date=WEEKDAY, start_time="08:00", end_time="10:00",
        cancellation={"cancel_date": WEEKDAY - timedelta(days=2)}, source="direct",
    )
    fee = calculate(facility, conditions)
    odd_fee = fee.model_copy(update={"online_prepay": 6005, "payment_due": 6005, "total": 6005})

    refund = estimate_cancel_refund(facility, conditions, conditions.cancellation, odd_fee)

    assert refund.status == "needs_review"
    assert refund.rate_percent == 90
    assert refund.review_items[0].code == "amount_unverified"


def test_closed_day_refund_is_not_calculated(facilities):
    closed_day = date(2027, 2, 7)  # 설날: 삼락 정기 휴장
    conditions = Conditions(
        sport="tennis", date=closed_day, start_time="08:00", end_time="10:00",
        cancellation={"cancel_date": closed_day - timedelta(days=3)}, source="direct",
    )
    refund = compare_facility(facilities["busan_samrak_ecopark_tennis"], conditions).cancel_refund

    assert refund.status == "needs_review"
    assert refund.refund_amount is None
    assert "예약할 수 없어" in refund.review_items[0].reason


def test_refund_rules_outside_period_not_in_effect(facilities):
    facility = facilities["busan_samrak_ecopark_tennis"]
    # 환불 규정은 있지만 모두 다른 기간의 규정인 경우
    other_period = facility.model_copy(update={"refund_rules": [
        rule.model_copy(update={"effective_from": date(2030, 1, 1), "effective_to": date(2030, 12, 31)})
        for rule in facility.refund_rules
    ]})
    refund = cancel_refund(other_period, "08:00", "10:00", {"cancel_date": WEEKDAY})

    assert refund.review_items[0].code == "rule_not_in_effect"


def test_facility_without_refund_rules_is_rule_missing(facilities):
    # 가상 데이터(JSON)처럼 환불 규정을 읽지 않은 시설은 '기간 밖'이 아니라 '규정 없음'이다.
    facility = facilities["busan_samrak_ecopark_tennis"].model_copy(update={"refund_rules": []})
    refund = cancel_refund(facility, "08:00", "10:00", {"cancel_date": WEEKDAY})

    assert refund.review_items[0].code == "rule_missing"


@pytest.mark.parametrize(("cancellation", "message"), [
    ({"reason": "user_cancel"}, "취소일을 입력"),
    ({"reason": "rain_unused", "cancel_date": "2026-11-08"}, "취소일을 받지 않습니다"),
    ({"cancel_date": "2026-11-10"}, "이용일보다 늦을 수 없습니다"),
])
def test_invalid_cancellation_rejected(cancellation, message):
    with pytest.raises(ValueError, match=message):
        Conditions(
            sport="tennis", date=WEEKDAY, start_time="08:00", end_time="10:00", cancellation=cancellation,
            source="direct",
        )
