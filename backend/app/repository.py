"""규정 데이터를 읽어 규칙 엔진의 입력(FacilityRules)으로 만든다.

가상 데이터(JSON)와 팀 DB(SQLite)를 같은 형식으로 읽는다. DB의 값 중 엔진이 표현하지 못하는
규정은 추정해 바꾸지 않고, 계산에서 빼거나 ValueError로 알린다.
"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from app.models import RuleData

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAMPLE_RULES_PATH = DATA_DIR / "sample_rules.json"
HOLIDAYS_PATH = DATA_DIR / "holidays_kr.json"
SQLITE_PATH = DATA_DIR.parent.parent / "database" / "facilities.sqlite3"

# DB에는 종목 표시 이름이 없다.
SPORT_LABELS = {"tennis": "테니스", "soccer": "축구"}
DISCOUNT_BASIS = {"per_eligible_person_equal_split": "per_eligible_person"}
DISCOUNT_TARGET = {"base_court_fee_only": "base"}
DISCOUNT_METHOD = {"pay_full_then_refund": "prepay_refund"}
DISCOUNT_ROUNDING = {
    "round_half_up": "round_1",
    "floor_won": "floor_1",
    "ceil_won": "ceil_1",
    "truncate_10_won": "floor_10",
    "truncate_100_won": "floor_100",
}
LIGHTING_PARTIAL_UNIT = {"exact_units": None, "round_up": "round_up", "proportional_if_exact": "prorate"}
OPTION_PAYMENT = {"online_prepay": "prepay", "onsite": "onsite", None: None}
ALL_DAYS = ["weekday", "weekend", "holiday"]


def load_rule_data(path: Path = SAMPLE_RULES_PATH, holidays_path: Path = HOLIDAYS_PATH) -> RuleData:
    data = json.loads(path.read_text(encoding="utf-8"))
    return _with_calendar(data, holidays_path)


def load_sqlite_rule_data(path: Path = SQLITE_PATH, holidays_path: Path = HOLIDAYS_PATH) -> RuleData:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row

        def rows(sql: str, *params) -> list[dict]:
            return [dict(row) for row in con.execute(sql, params)]

        facilities = [_sqlite_facility(rows, facility) for facility in rows("SELECT * FROM facilities ORDER BY id")]
        labels = {
            "sports": SPORT_LABELS,
            "discount_types": {row["id"]: row["name"] for row in rows("SELECT * FROM discount_categories")},
        }
    return _with_calendar({"labels": labels, "facilities": facilities}, holidays_path)


def _with_calendar(data: dict, holidays_path: Path) -> RuleData:
    # 공휴일은 시설과 무관한 공통 자료이므로 모든 시설에 같은 목록을 붙인다.
    calendar = json.loads(holidays_path.read_text(encoding="utf-8"))
    for facility in data["facilities"]:
        facility["holiday_calendar"] = calendar
    return RuleData.model_validate(data)


def _sqlite_facility(rows, facility: dict) -> dict:
    rule_sets = rows(
        "SELECT * FROM rule_sets WHERE facility_id = ? ORDER BY effective_from DESC", facility["id"]
    )
    if not rule_sets:
        raise ValueError(f"규정 기간이 없는 시설: {facility['id']}")

    fee_rules, discount_rules, time_policies, source_ids = [], [], [], []
    for rule_set in rule_sets:
        period = {"effective_from": rule_set["effective_from"], "effective_to": rule_set["effective_to"]}
        source_id = rule_set["source_id"]
        source_ids.append(source_id)
        sport = facility["facility_type"]
        rule_set_id = rule_set["id"]

        prices = rows("SELECT * FROM pricing_rules WHERE rule_set_id = ? ORDER BY start_time, duration_minutes", rule_set_id)
        policy = next(iter(rows("SELECT * FROM time_selection_policies WHERE rule_set_id = ?", rule_set_id)), None)
        fee_rules += _base_rules(prices, policy, facility, sport, period, source_id)
        fee_rules += _lighting_rules(
            prices, rows("SELECT * FROM facility_options WHERE rule_set_id = ?", rule_set_id), sport, period, source_id
        )
        if policy is not None and policy["selection_type"] == "fixed_slot":
            time_policies.append(
                {
                    "policy_id": f"{rule_set_id}_time",
                    "sport": sport,
                    "selection": "fixed_slot",
                    "slots": [{"start_time": p["start_time"], "end_time": p["end_time"]} for p in prices],
                    "open_time": facility["open_time"],
                    "close_time": facility["close_time"],
                    "source_id": source_id,
                    **period,
                }
            )
        elif policy is not None:
            time_policies += _flexible_time_policy(policy, facility, sport, period, source_id)

        for discount in rows("SELECT * FROM facility_discounts WHERE rule_set_id = ?", rule_set_id):
            discount_rules.append(
                {
                    "rule_id": discount["id"],
                    "discount_type": discount["category_id"],
                    "rate": f"{discount['percent'] / 100}",
                    "applies_to": _mapped(DISCOUNT_TARGET, discount["applies_to"], "감면 대상 요금"),
                    "method": _mapped(DISCOUNT_METHOD, discount["processing"], "감면 방식"),
                    "basis": _mapped(DISCOUNT_BASIS, discount["basis"], "감면 계산 방식"),
                    "rounding": DISCOUNT_ROUNDING[discount["discount_rounding_policy"]]
                    if discount["discount_rounding_policy"] is not None
                    else None,
                    "required_documents": [discount["documents"]] if discount["documents"] else None,
                    "source_id": source_id,
                    **period,
                }
            )

    # 여러 규정 기간이 같은 출처를 쓰면 자리표시자와 값의 개수가 같도록 중복을 먼저 뺀다.
    source_ids = list(dict.fromkeys(source_ids))
    sources = rows(f"SELECT * FROM sources WHERE id IN ({','.join('?' * len(source_ids))})", *source_ids)
    latest = rule_sets[0]
    return {
        "facility_id": facility["id"],
        "name": facility["name"],
        "district": facility["district"],
        "source_id": latest["source_id"],
        "info": {
            "address": facility["address"],
            "phone": facility["phone"],
            "booking_url": facility["booking_url"],
            "operating_hours": {
                "open_time": facility["open_time"],
                "close_time": facility["close_time"],
                "note": facility["holiday_note"],
            },
        },
        "closure_notes": [
            {
                "note": reservation["closure_note"],
                "source_id": rule_set["source_id"],
                "effective_from": rule_set["effective_from"],
                "effective_to": rule_set["effective_to"],
            }
            for rule_set in rule_sets
            for reservation in rows("SELECT closure_note FROM reservation_rules WHERE rule_set_id = ?", rule_set["id"])
            if reservation["closure_note"]
        ],
        "fee_rules": fee_rules,
        "discount_rules": discount_rules,
        "time_policies": time_policies,
        # 예약·취소 조건은 규정 기간마다 달라질 수 있어 기간별로 두고, 이용일에 맞는 것을 고른다.
        "terms_by_period": [
            _terms(rows, rule_set)
            | {"effective_from": rule_set["effective_from"], "effective_to": rule_set["effective_to"]}
            for rule_set in rule_sets
        ],
        "sources": [
            {
                "source_id": source["id"],
                "url": source["url"],
                "checked_at": source["checked_on"],
                "license": source["license"] or "이용허락범위 미확인",
            }
            for source in sources
        ],
    }


def _flexible_time_policy(policy: dict, facility: dict, sport: str, period: dict, source_id: str) -> list[dict]:
    """자유 선택 시설의 운영시간과 1회 최대 이용시간. 허용 이용시간 목록은 확인되지 않아 만들지 않는다.

    최대 시간 안의 이용시간은 요금 단위 미만으로 처리되어 '확인 필요'가 된다(database/README.md).
    하루 이용 한도(daily_limit_minutes)는 예약 이력이 있어야 확인할 수 있어 여기서 다루지 않는다.
    """
    if policy["min_minutes"] is not None or policy["step_minutes"] is not None:
        raise ValueError(f"변환할 수 없는 이용시간 규정: {policy['rule_set_id']}")
    if policy["max_minutes"] is None:
        return []
    return [
        {
            "policy_id": f"{policy['rule_set_id']}_time",
            "sport": sport,
            "selection": "flexible",
            "max_minutes": policy["max_minutes"],
            "open_time": policy["available_start_time"] or facility["open_time"],
            "close_time": policy["available_end_time"] or facility["close_time"],
            "source_id": source_id,
            **period,
        }
    ]


def _base_rules(prices: list[dict], policy: dict | None, facility: dict, sport: str, period: dict, source_id: str) -> list[dict]:
    flexible = [p for p in prices if p["selection_type"] == "flexible_interval"]
    # 엔진은 한 요금 단위를 반복해 계산하므로, 이용시간별 요금이 여럿이면 표현할 수 없다.
    if len(flexible) > 1:
        raise ValueError(f"이용시간별 요금이 여럿인 자유 선택 시설은 아직 변환할 수 없습니다: {flexible[0]['rule_set_id']}")

    rules = []
    for price in prices:
        if price["selection_type"] == "fixed_slot":
            band = {"time_from": price["start_time"], "time_to": price["end_time"]}
        else:
            band = {
                "time_from": (policy or {}).get("available_start_time") or facility["open_time"],
                "time_to": (policy or {}).get("available_end_time") or facility["close_time"],
            }
        common = {
            "sport": sport,
            "type": "base",
            "unit_minutes": price["duration_minutes"],
            # 단위 미만의 요금은 공식 근거가 없으므로 '확인 필요'로 남긴다.
            "partial_unit": None,
            "source_id": source_id,
            **band,
            **period,
        }
        if price["weekday_base_won"] == price["weekend_holiday_base_won"]:
            rules.append({"rule_id": price["id"], "amount": price["weekday_base_won"], "day_types": ALL_DAYS, **common})
        else:
            rules.append({"rule_id": f"{price['id']}_weekday", "amount": price["weekday_base_won"], "day_types": ["weekday"], **common})
            rules.append(
                {
                    "rule_id": f"{price['id']}_weekend_holiday",
                    "amount": price["weekend_holiday_base_won"],
                    "day_types": ["weekend", "holiday"],
                    **common,
                }
            )
    return rules


def _lighting_rules(prices: list[dict], options: list[dict], sport: str, period: dict, source_id: str) -> list[dict]:
    """필수 조명료는 이용 시간으로, 선택 조명료는 사용자가 고른 조명 사용 시간으로 계산하는 규정을 만든다."""
    common = {"sport": sport, "type": "lighting", "day_types": ALL_DAYS, "source_id": source_id, **period}
    # 회차 요금에 포함된 필수 조명료는 회차와 같은 시간대의 조명 항목으로 따로 보여 준다.
    # 회차 요금과 함께 예약 시 온라인으로 결제한다.
    rules = [
        {
            "rule_id": f"{price['id']}_lighting",
            "amount": price["mandatory_light_won"],
            "unit_minutes": price["duration_minutes"],
            "partial_unit": None,
            "payment": "prepay",
            "time_from": price["start_time"],
            "time_to": price["end_time"],
            **common,
        }
        for price in prices
        if price["selection_type"] == "fixed_slot" and price["mandatory_light_won"] > 0
    ]
    for option in options:
        if option["option_id"] != "lighting" or option["application_type"] == "included_in_base_price":
            continue
        if option["application_type"] == "optional":
            rules.append(_optional_lighting_rule(option, common))
            continue
        if option["calculation_type"] != "time_overlap_units" or option["extra_unit_minutes"] is not None:
            raise ValueError(f"변환할 수 없는 필수 조명 규정: {option['id']}")
        rules.append(
            {
                "rule_id": option["id"],
                "amount": option["hour_price"],
                "unit_minutes": 60,
                "partial_unit": _mapped(LIGHTING_PARTIAL_UNIT, option["rounding_policy"], "조명료 단위 처리"),
                "payment": _mapped(OPTION_PAYMENT, option["payment_type"], "조명료 결제 방식"),
                "time_from": option["applies_from"],
                "time_to": option["applies_to"],
                **common,
            }
        )
    return rules


def _optional_lighting_rule(option: dict, common: dict) -> dict:
    if option["calculation_type"] not in ("hour_blocks_plus_steps", "rounded_units"):
        raise ValueError(f"변환할 수 없는 선택 조명 규정: {option['id']}")
    return {
        **common,
        "type": "optional_lighting",
        "rule_id": option["id"],
        "amount": option["hour_price"],
        "unit_minutes": 60,
        "extra_unit_minutes": option["extra_unit_minutes"],
        "extra_unit_amount": option["extra_unit_price"],
        "partial_unit": _mapped(LIGHTING_PARTIAL_UNIT, option["rounding_policy"], "조명료 단위 처리"),
        "payment": _mapped(OPTION_PAYMENT, option["payment_type"], "선택 조명료 결제 방식"),
        "time_from": option["applies_from"],
        "time_to": option["applies_to"],
    }


def _terms(rows, rule_set: dict) -> dict:
    reservation = next(iter(rows("SELECT * FROM reservation_rules WHERE rule_set_id = ?", rule_set["id"])), None)
    refunds = rows(
        "SELECT * FROM refund_rules WHERE rule_set_id = ? AND reason = 'user_cancel' ORDER BY days_before_min DESC",
        rule_set["id"],
    )
    terms = {"source_id": rule_set["source_id"]}
    if reservation is not None:
        terms["booking_open"] = (
            f"이용일 {reservation['online_open_days_before']}일 전부터 "
            f"{reservation['online_close_days_before']}일 전까지 온라인 신청"
        )
        terms["cancel_deadline"] = f"이용일 {reservation['normal_cancel_online_min_days_before']}일 전까지 온라인 취소"
    if refunds:
        terms["refund"] = ", ".join(f"{_refund_when(refund)} {refund['rate_percent']}%" for refund in refunds)
    return terms


def _refund_when(refund: dict) -> str:
    low, high = refund["days_before_min"], refund["days_before_max"]
    if low == 0 and high == 0:
        return "당일 취소"
    if high is None:
        return f"{low}일 전까지 취소"
    if low == high:
        return f"{low}일 전 취소"
    return f"{high}~{low}일 전 취소"


def _mapped(table: dict, value: str, name: str):
    if value not in table:
        raise ValueError(f"변환할 수 없는 {name}: {value}")
    return table[value]
