"""규정 데이터와 요청·응답 형식. 규정의 모르는 값은 추정하지 않고 None으로 둔다."""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic_core import PydanticCustomError

KST = timezone(timedelta(hours=9))


def _date_only(value):
    """날짜는 YYYY-MM-DD만 받는다. 기본 변환은 시각이 붙은 문자열이나 타임스탬프도 날짜로 바꾼다."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    raise PydanticCustomError("date_format", "날짜는 YYYY-MM-DD 형식으로 입력해 주세요.")


IsoDate = Annotated[date, BeforeValidator(_date_only)]

ClockTime = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
BandTime = Annotated[str, StringConstraints(pattern=r"^(([01]\d|2[0-3]):[0-5]\d|24:00)$")]
Rounding = Annotated[str, StringConstraints(pattern=r"^(floor|ceil|round)_(1|10|100|1000)$")]
DayType = Literal["weekday", "weekend", "holiday"]
DiscountMethod = Literal["onsite", "prepay_refund"]
PaymentMethod = Literal["prepay", "onsite"]
# 금액 항목의 결제 방식. unverified: 공식 자료에서 결제 시점·장소를 확인하지 못함
ItemPayment = Literal["prepay", "onsite", "unverified"]
DiscountBasis = Literal["whole_fee", "per_eligible_person", "holder_whole_fee"]


def to_minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


# 이용 조건


class DiscountSelection(BaseModel):
    """감면 대상자 입력. 이름·증빙 번호 같은 개인정보는 받지 않고 인원수만 받는다."""

    type: str = Field(min_length=1)
    count: int = Field(ge=1)
    holder: bool = False


class Conditions(BaseModel):
    sport: str = Field(min_length=1)
    districts: list[str] = []
    date: IsoDate
    start_time: ClockTime
    end_time: BandTime
    headcount: int | None = Field(default=None, ge=1)
    # 인원을 모르는 감면 선택. 인원 비례 감면 시설은 discounts로 받아야 계산한다.
    discount_types: list[str] = []
    discounts: list[DiscountSelection] = []
    # 지정 회차 중 사용자가 조명을 켤 시간. 필수 조명은 이용 시간으로 자동 계산한다.
    optional_lighting_minutes: int = Field(default=0, ge=0)
    source: Literal["direct", "llm"]

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, value: str, info: ValidationInfo) -> str:
        start = info.data.get("start_time")
        if start is not None and to_minutes(value) <= to_minutes(start):
            raise PydanticCustomError("invalid_time_range", "종료 시간은 시작 시간보다 늦어야 합니다.")
        return value

    @model_validator(mode="after")
    def check_optional_lighting(self) -> "Conditions":
        if self.optional_lighting_minutes > to_minutes(self.end_time) - to_minutes(self.start_time):
            raise PydanticCustomError("invalid_lighting_minutes", "선택 조명 사용 시간은 이용 시간보다 길 수 없습니다.")
        return self

    @model_validator(mode="after")
    def check_discounts(self) -> "Conditions":
        types = [*dict.fromkeys(self.discount_types), *(d.type for d in self.discounts)]
        if len(set(types)) != len(types):
            raise PydanticCustomError("invalid_discount", "같은 감면 유형을 두 번 선택할 수 없습니다.")
        if sum(d.holder for d in self.discounts) > 1:
            raise PydanticCustomError("invalid_discount", "예약 대표자는 감면 유형 하나에만 해당할 수 있습니다.")
        if self.discounts and self.headcount is None:
            raise PydanticCustomError("invalid_discount", "감면 대상 인원을 입력하면 전체 이용 인원도 입력해야 합니다.")
        if self.discounts and sum(d.count for d in self.discounts) > self.headcount:
            raise PydanticCustomError("invalid_discount", "감면 대상 인원이 전체 이용 인원보다 많습니다.")
        return self

    @property
    def discount_selections(self) -> list[tuple[str, int | None, bool | None]]:
        """(유형, 대상 인원, 대표자 여부). discount_types로 받은 감면은 인원과 대표자 여부를 모른다."""
        return [(t, None, None) for t in dict.fromkeys(self.discount_types)] + [
            (d.type, d.count, d.holder) for d in self.discounts
        ]


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
    # optional_lighting: 사용자가 고른 조명 사용 시간으로 계산한다. time_from~time_to는 선택할 수 있는 이용 시간대다.
    type: Literal["base", "lighting", "optional_lighting"]
    amount: int | None = Field(default=None, ge=0)
    unit_minutes: int | None = Field(default=None, gt=0)
    # 단위 시간을 채우고 남은 시간에 붙는 요금. 예: 60분 10,000원 + 남은 10분마다 1,600원
    extra_unit_minutes: int | None = Field(default=None, gt=0)
    extra_unit_amount: int | None = Field(default=None, ge=0)
    partial_unit: Literal["round_up", "prorate"] | None = None
    # 조명료를 온라인으로 선결제하는지 현장에서 결제하는지. 모르면 None
    payment: PaymentMethod | None = None
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
        if (self.extra_unit_minutes is None) != (self.extra_unit_amount is None):
            raise ValueError("extra_unit_minutes와 extra_unit_amount는 함께 입력해야 합니다.")
        if self.extra_unit_minutes is not None and self.type != "optional_lighting":
            raise ValueError("추가 단위 요금은 선택 조명 규정에만 입력할 수 있습니다.")
        if self.payment is not None and self.type == "base":
            raise ValueError("결제 방식은 조명 규정에만 입력할 수 있습니다.")
        return self


class DiscountRule(EffectivePeriod):
    rule_id: str
    discount_type: str
    rate: Decimal | None = Field(default=None, ge=0, le=1)
    fixed_amount: int | None = Field(default=None, ge=0)
    applies_to: Literal["base", "base_and_lighting"] | None = None
    method: DiscountMethod | None = None
    # whole_fee: 대상 요금 전체, per_eligible_person: 대상 요금 ÷ 전체 인원 × 대상 인원,
    # holder_whole_fee: 예약 대표자가 대상일 때만 대상 요금 전체
    basis: DiscountBasis = "whole_fee"
    stackable: bool | None = None
    rounding: Rounding | None = None
    required_documents: list[str] | None = None
    source_id: str

    @model_validator(mode="after")
    def check_amount(self) -> "DiscountRule":
        if self.rate is not None and self.fixed_amount is not None:
            raise ValueError("rate와 fixed_amount는 함께 입력할 수 없습니다.")
        if self.fixed_amount is not None and self.basis != "whole_fee":
            raise ValueError("fixed_amount는 basis가 whole_fee일 때만 입력할 수 있습니다.")
        return self


class Terms(BaseModel):
    booking_open: str | None = None
    cancel_deadline: str | None = None
    refund: str | None = None
    source_id: str | None = None


class PeriodTerms(Terms, EffectivePeriod):
    """규정 기간마다 다른 예약·취소 조건. 이용일에 유효한 조건을 응답에 쓴다."""


class Holiday(BaseModel):
    date: date
    name: str


class HolidayCalendar(BaseModel):
    """관공서 공휴일 목록. 기간 밖의 날짜는 공휴일인지 알 수 없는 날로 본다."""

    covered_from: date
    covered_to: date
    holidays: list[Holiday]
    source: Source

    def covers(self, day: date) -> bool:
        return self.covered_from <= day <= self.covered_to

    def is_holiday(self, day: date) -> bool:
        return any(holiday.date == day for holiday in self.holidays)

    @model_validator(mode="after")
    def check_range(self) -> "HolidayCalendar":
        outside = [h.date.isoformat() for h in self.holidays if not self.covers(h.date)]
        if outside:
            raise ValueError(f"기간 밖의 공휴일: {outside}")
        return self


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
    # 한 번에 이용할 수 있는 최대 시간. allowed_minutes 없이 상한만 확인된 시설에 쓴다.
    max_minutes: int | None = Field(default=None, gt=0)
    open_time: ClockTime | None = None
    close_time: BandTime | None = None
    source_id: str

    @model_validator(mode="after")
    def check_selection(self) -> "TimePolicy":
        if self.selection == "fixed_slot" and not self.slots:
            raise ValueError("지정 회차 시설은 slots가 필요합니다.")
        if self.selection == "flexible" and not self.allowed_minutes and self.max_minutes is None:
            raise ValueError("자유 선택 시설은 allowed_minutes나 max_minutes가 필요합니다.")
        for slot in self.slots:
            if to_minutes(slot.end_time) <= to_minutes(slot.start_time):
                raise ValueError("회차의 종료 시간은 시작 시간보다 늦어야 합니다.")
        if (self.open_time is None) != (self.close_time is None):
            raise ValueError("open_time과 close_time은 함께 입력해야 합니다.")
        if self.open_time is not None and to_minutes(self.close_time) <= to_minutes(self.open_time):
            raise ValueError("운영시간의 종료 시간은 시작 시간보다 늦어야 합니다.")
        return self


class OperatingHours(BaseModel):
    open_time: ClockTime | None = None
    close_time: BandTime | None = None
    note: str | None = None


class FacilityInfo(BaseModel):
    """시설 기본정보. 요금 계산에는 쓰지 않고 상세 화면에만 보여 준다."""

    address: str | None = None
    phone: str | None = None
    booking_url: str | None = None
    operating_hours: OperatingHours = OperatingHours()


class PeriodNote(EffectivePeriod):
    """규정 기간마다 다른 안내 문구(휴장 안내 등)."""

    note: str
    source_id: str


class FacilityRules(BaseModel):
    facility_id: str
    name: str
    district: str | None = None
    source_id: str
    info: FacilityInfo = FacilityInfo()
    closure_notes: list[PeriodNote] = []
    # 공통 공휴일 목록을 저장소에서 붙인다. 없으면 모든 날짜의 공휴일 여부를 알 수 없다.
    holiday_calendar: HolidayCalendar | None = None
    fee_rules: list[FeeRule] = []
    discount_rules: list[DiscountRule] = []
    # 비어 있으면 이용시간 제한을 확인하지 않는다.
    time_policies: list[TimePolicy] = []
    terms: Terms = Terms()
    # 규정 기간별 예약·취소 조건. 있으면 terms 대신 이용일에 유효한 조건을 쓴다.
    terms_by_period: list[PeriodTerms] = []
    sources: list[Source]

    def _period_terms(self, day: date) -> PeriodTerms | None:
        matched = [terms for terms in self.terms_by_period if terms.in_effect(day)]
        return matched[0] if len(matched) == 1 else None

    def terms_on(self, day: date) -> Terms:
        """이용일의 예약·취소 조건. 기간별 조건 중 유효한 것이 없으면 모든 값을 모르는 것으로 둔다."""
        if not self.terms_by_period:
            return self.terms
        period = self._period_terms(day)
        if period is None:
            return Terms()
        return Terms(**period.model_dump(exclude={"effective_from", "effective_to"}))

    def source_on(self, day: date) -> str:
        """근거 규정이 없을 때 안내할 공식 출처. 규정 기간별 출처가 있으면 이용일의 출처를 쓴다."""
        return self.period_source_on(day) or self.source_id

    def period_source_on(self, day: date) -> str | None:
        """이용일에 유효한 규정 기간의 출처. 기간별 규정이 없으면 시설 출처, 유효한 기간이 없으면 None"""
        if not self.terms_by_period:
            return self.source_id
        period = self._period_terms(day)
        return period.source_id if period is not None else None

    @property
    def sports(self) -> set[str]:
        """요금을 계산할 수 있는 종목. 규정과 어긋나지 않도록 따로 저장하지 않는다."""
        return {rule.sport for rule in self.fee_rules if rule.type == "base"}

    @model_validator(mode="after")
    def check_sources(self) -> "FacilityRules":
        known = {source.source_id for source in self.sources}
        rules = [*self.fee_rules, *self.discount_rules, *self.time_policies, *self.closure_notes]
        used = {self.source_id, *(rule.source_id for rule in rules)}
        used |= {terms.source_id for terms in [self.terms, *self.terms_by_period] if terms.source_id is not None}
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
    # 조명료만. 다른 금액 항목은 온라인 선결제다.
    payment: ItemPayment | None = None

    @model_serializer(mode="wrap")
    def omit_empty_method(self, handler):
        data = handler(self)
        for key in ("method", "payment"):
            if data[key] is None:
                del data[key]
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
    # 이용 당일 현장에서 따로 내는 금액. payment_due에는 들어가지 않는다.
    onsite_payment: int | None
    # 결제 방식을 확인하지 못한 금액. 0보다 크면 payment_due는 None이다.
    payment_unverified: int | None
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


# 시설 상세


class TimeOption(BaseModel):
    """이용일에 유효한 이용시간 규정. 화면의 회차·이용시간 선택지로 쓴다."""

    sport: str
    selection: Literal["fixed_slot", "flexible"]
    slots: list[Slot]
    allowed_minutes: list[int]
    max_minutes: int | None
    open_time: str | None
    close_time: str | None
    source_id: str


class FacilityDetail(BaseModel):
    facility_id: str
    name: str
    sports: list[str]
    district: str | None
    address: str | None
    phone: str | None
    operating_hours: OperatingHours
    closure_note: str | None
    booking_url: str | None
    time_options: list[TimeOption]
    # 이용일에 유효한 규정 기간이 없으면 None. 지난 기간의 출처는 보여 주지 않는다.
    source_id: str | None
    sources: list[Source]
