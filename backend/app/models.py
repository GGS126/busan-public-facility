"""규정 데이터와 요청·응답 형식. 규정의 모르는 값은 추정하지 않고 None으로 둔다."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic_core import PydanticCustomError

KST = timezone(timedelta(hours=9))

ClockTime = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
BandTime = Annotated[str, StringConstraints(pattern=r"^(([01]\d|2[0-3]):[0-5]\d|24:00)$")]
Rounding = Annotated[str, StringConstraints(pattern=r"^(floor|ceil|round)_(1|10|100|1000)$")]
DayType = Literal["weekday", "weekend", "holiday"]
DiscountMethod = Literal["onsite", "prepay_refund"]


def to_minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


# 이용 조건


class Conditions(BaseModel):
    sport: str = Field(min_length=1)
    districts: list[str] = []
    date: date
    start_time: ClockTime
    end_time: BandTime
    headcount: int | None = Field(default=None, ge=1)
    discount_types: list[str] = []
    source: Literal["direct", "llm"]

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, value: str, info: ValidationInfo) -> str:
        start = info.data.get("start_time")
        if start is not None and to_minutes(value) <= to_minutes(start):
            raise PydanticCustomError("invalid_time_range", "종료 시간은 시작 시간보다 늦어야 합니다.")
        return value


class RequestConditions(Conditions):
    """API 입력 조건. 현재 날짜에 의존하는 검증은 규칙 엔진의 입력과 분리한다."""

    @field_validator("date")
    @classmethod
    def not_in_past(cls, value: date) -> date:
        if value < datetime.now(KST).date():
            raise PydanticCustomError("past_date", "지난 날짜는 선택할 수 없습니다.")
        return value


class CompareRequest(BaseModel):
    facility_ids: list[str] = Field(min_length=1)
    conditions: RequestConditions


# 규정 데이터


class Source(BaseModel):
    source_id: str
    url: str
    checked_at: date
    license: str


class EffectivePeriod(BaseModel):
    effective_from: date
    effective_to: date | None = None

    def in_effect(self, day: date) -> bool:
        return self.effective_from <= day and (self.effective_to is None or day <= self.effective_to)


class FeeRule(EffectivePeriod):
    rule_id: str
    sport: str
    type: Literal["base", "lighting"]
    amount: int | None = Field(default=None, ge=0)
    unit_minutes: int | None = Field(default=None, gt=0)
    partial_unit: Literal["round_up", "prorate"] | None = None
    day_types: list[DayType] | None = None
    months: list[Annotated[int, Field(ge=1, le=12)]] | None = None
    time_from: BandTime | None = None
    time_to: BandTime | None = None
    source_id: str

    @model_validator(mode="after")
    def check_band(self) -> "FeeRule":
        if (self.time_from is None) != (self.time_to is None):
            raise ValueError("time_from과 time_to는 함께 입력해야 합니다.")
        if self.time_from is not None and to_minutes(self.time_from) >= to_minutes(self.time_to):
            raise ValueError("time_from은 time_to보다 빨라야 합니다.")
        return self


class DiscountRule(EffectivePeriod):
    rule_id: str
    discount_type: str
    rate: Decimal | None = Field(default=None, ge=0, le=1)
    fixed_amount: int | None = Field(default=None, ge=0)
    applies_to: Literal["base", "base_and_lighting"] | None = None
    method: DiscountMethod | None = None
    stackable: bool | None = None
    rounding: Rounding | None = None
    required_documents: list[str] | None = None
    source_id: str

    @model_validator(mode="after")
    def check_amount(self) -> "DiscountRule":
        if self.rate is not None and self.fixed_amount is not None:
            raise ValueError("rate와 fixed_amount는 함께 입력할 수 없습니다.")
        return self


class Terms(BaseModel):
    booking_open: str | None = None
    cancel_deadline: str | None = None
    refund: str | None = None
    source_id: str | None = None


class Slot(BaseModel):
    start_time: ClockTime
    end_time: BandTime


class TimePolicy(EffectivePeriod):
    """예약할 수 있는 시간. 지정 회차만 받는 시설과 허용 이용시간 안에서 고르는 시설을 구분한다."""

    policy_id: str
    sport: str
    selection: Literal["fixed_slot", "flexible"]
    slots: list[Slot] = []
    allowed_minutes: list[Annotated[int, Field(gt=0)]] = []
    open_time: ClockTime | None = None
    close_time: BandTime | None = None
    source_id: str

    @model_validator(mode="after")
    def check_selection(self) -> "TimePolicy":
        if self.selection == "fixed_slot" and not self.slots:
            raise ValueError("지정 회차 시설은 slots가 필요합니다.")
        if self.selection == "flexible" and not self.allowed_minutes:
            raise ValueError("자유 선택 시설은 allowed_minutes가 필요합니다.")
        for slot in self.slots:
            if to_minutes(slot.end_time) <= to_minutes(slot.start_time):
                raise ValueError("회차의 종료 시간은 시작 시간보다 늦어야 합니다.")
        if (self.open_time is None) != (self.close_time is None):
            raise ValueError("open_time과 close_time은 함께 입력해야 합니다.")
        return self


class FacilityRules(BaseModel):
    facility_id: str
    name: str
    district: str | None = None
    source_id: str
    holidays: list[date] = []
    fee_rules: list[FeeRule] = []
    discount_rules: list[DiscountRule] = []
    # 비어 있으면 이용시간 제한을 확인하지 않는다.
    time_policies: list[TimePolicy] = []
    terms: Terms = Terms()
    sources: list[Source]

    @property
    def sports(self) -> set[str]:
        """요금을 계산할 수 있는 종목. 규정과 어긋나지 않도록 따로 저장하지 않는다."""
        return {rule.sport for rule in self.fee_rules if rule.type == "base"}

    @model_validator(mode="after")
    def check_sources(self) -> "FacilityRules":
        known = {source.source_id for source in self.sources}
        rules = [*self.fee_rules, *self.discount_rules, *self.time_policies]
        used = {self.source_id, *(rule.source_id for rule in rules)}
        if self.terms.source_id is not None:
            used.add(self.terms.source_id)
        if used - known:
            raise ValueError(f"등록되지 않은 출처: {sorted(used - known)}")
        return self


class Labels(BaseModel):
    """화면에 표시할 이름. 요금 계산에는 코드만 사용한다."""

    sports: dict[str, str]
    discount_types: dict[str, str]


class RuleData(BaseModel):
    labels: Labels
    facilities: list[FacilityRules]

    @model_validator(mode="after")
    def check_labels(self) -> "RuleData":
        sports = {sport for facility in self.facilities for sport in facility.sports}
        discounts = {
            rule.discount_type for facility in self.facilities for rule in facility.discount_rules
        }
        missing = (sports - self.labels.sports.keys()) | (discounts - self.labels.discount_types.keys())
        if missing:
            raise ValueError(f"표시 이름이 없는 코드: {sorted(missing)}")
        return self


# 입력 선택지


class Option(BaseModel):
    code: str
    label: str


class OptionsResponse(BaseModel):
    sports: list[Option]
    districts: list[str]
    discount_types: list[Option]


# 계산 결과


class FeeItem(BaseModel):
    type: Literal["base", "lighting", "discount"]
    amount: int
    rule_id: str
    source_id: str
    method: DiscountMethod | None = None

    @model_serializer(mode="wrap")
    def omit_empty_method(self, handler):
        data = handler(self)
        if data["method"] is None:
            del data["method"]
        return data


class ReviewItem(BaseModel):
    code: Literal[
        "rule_missing",
        "rule_conflict",
        "rule_not_in_effect",
        "slot_mismatch",
        "duration_not_allowed",
        "outside_hours",
    ]
    target: Literal["base", "lighting", "discount", "checklist", "time"]
    reason: str
    source_id: str


class FeeResult(BaseModel):
    status: Literal["calculated", "needs_review", "not_eligible"]
    items: list[FeeItem]
    total: int | None
    payment_due: int | None
    expected_refund: int | None
    net_cost_after_refund: int | None
    review_items: list[ReviewItem]


class CompareResult(BaseModel):
    facility_id: str
    facility_name: str
    fee: FeeResult
    terms: Terms
    checklist: list[str]
    checklist_review_items: list[ReviewItem]
    sources: list[Source]


class CompareResponse(BaseModel):
    results: list[CompareResult]
