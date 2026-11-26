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
# 환불 사유. user_cancel만 취소 시점(이용일 며칠 전)으로 환불률이 갈린다.
RefundReason = Literal["user_cancel", "rain_same_day", "rain_unused", "force_majeure_or_city_event"]


def to_minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


# 이용 조건


class DiscountSelection(BaseModel):
    """감면 대상자 입력. 이름·증빙 번호 같은 개인정보는 받지 않고 인원수만 받는다."""

    type: str = Field(min_length=1)
    count: int = Field(ge=1)
    holder: bool = False


class Cancellation(BaseModel):
    """예약을 취소하거나 이용하지 못했을 때의 예상 환불을 묻는 입력.

    사용자 취소는 취소일로 환불률이 정해지므로 취소일이 필요하다. 우천·불가항력은 사유로 환불률이 정해지고,
    실제로 그 사유가 인정되는지는 시설이 판단하므로 취소일을 받지 않는다.
    """

    reason: RefundReason = "user_cancel"
    cancel_date: IsoDate | None = None

    @model_validator(mode="after")
    def cancel_date_matches_reason(self) -> "Cancellation":
        """이용일과 비교하는 검증은 Conditions.cancel_date_before_use에 있다."""
        if self.reason == "user_cancel" and self.cancel_date is None:
            raise PydanticCustomError("invalid_cancellation", "사용자 취소는 취소일을 입력해야 합니다.")
        if self.reason != "user_cancel" and self.cancel_date is not None:
            raise PydanticCustomError("invalid_cancellation", "우천·불가항력 환불은 취소일을 받지 않습니다.")
        return self


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
    # 있으면 이 조건으로 예약한 뒤 취소했을 때의 예상 환불도 계산한다.
    cancellation: Cancellation | None = None
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

    @model_validator(mode="after")
    def cancel_date_before_use(self) -> "Conditions":
        cancel_date = self.cancellation.cancel_date if self.cancellation else None
        if cancel_date is not None and cancel_date > self.date:
            raise PydanticCustomError("invalid_cancellation", "취소일은 이용일보다 늦을 수 없습니다.")
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

    @field_validator("cancellation")
    @classmethod
    def cancel_not_in_past(cls, value: Cancellation | None) -> Cancellation | None:
        # 이미 지난 날 취소했다고 가정하면 지금은 받을 수 없는 환불을 안내하게 된다.
        if value is not None and value.cancel_date is not None and value.cancel_date < datetime.now(KST).date():
            raise PydanticCustomError("invalid_cancellation", "지난 날짜에 취소한 경우는 계산할 수 없습니다.")
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
    # 감면을 받기 위한 신청 기한·방법. 사후 반환 감면은 이 기한을 놓치면 반환받지 못한다.
    application_deadline: str | None = None
    # 보호자 동반 감면의 증빙 안내
    guardian_note: str | None = None
    source_id: str

    @model_validator(mode="after")
    def check_amount(self) -> "DiscountRule":
        if self.rate is not None and self.fixed_amount is not None:
            raise ValueError("rate와 fixed_amount는 함께 입력할 수 없습니다.")
        if self.fixed_amount is not None and self.basis != "whole_fee":
            raise ValueError("fixed_amount는 basis가 whole_fee일 때만 입력할 수 있습니다.")
        return self


class RefundRule(EffectivePeriod):
    """환불 규정 하나. 사용자 취소는 이용일 며칠 전에 취소했는지(0은 당일)의 범위로 환불률이 정해진다.

    days_before_min·max가 None이면 그쪽 범위 제한이 없다. 공식 자료로 확인하지 못한 규정은 계산에 쓰지 않는다.
    """

    rule_id: str
    reason: RefundReason
    days_before_min: int | None = Field(default=None, ge=0)
    days_before_max: int | None = Field(default=None, ge=0)
    rate_percent: int | None = Field(default=None, ge=0, le=100)
    confirmed: bool
    # 신청 방법·환급 시기 안내(terms.refund_notes와 같은 문구)
    note: str
    source_id: str

    def covers(self, days_before: int) -> bool:
        return (self.days_before_min is None or days_before >= self.days_before_min) and (
            self.days_before_max is None or days_before <= self.days_before_max
        )


class Terms(BaseModel):
    booking_open: str | None = None
    cancel_deadline: str | None = None
    refund: str | None = None
    # 환불 사유별 안내. 사용자 취소의 신청 방법·환급 시기와 우천·불가항력 환불을 함께 적는다.
    refund_notes: list[str] = []
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


class ClosureRule(EffectivePeriod):
    """정기 휴장일. annual_date는 MM-DD, exact_date는 YYYY-MM-DD, holiday_code는 명절 코드다."""

    type: Literal["annual_date", "exact_date", "holiday_code"]
    value: str
    note: str
    source_id: str

    @model_validator(mode="after")
    def check_value(self) -> "ClosureRule":
        # 형식이 틀린 값은 어떤 날짜와도 일치하지 않아 휴장일이 조용히 빠지므로 읽을 때 막는다.
        if self.type == "annual_date":
            valid = len(self.value) == 5 and _is_date(f"2024-{self.value}")  # 2월 29일을 허용하는 해
        elif self.type == "exact_date":
            valid = _is_date(self.value)
        else:
            valid = self.value in ("lunar_new_year_day", "chuseok_day")
        if not valid:
            raise ValueError(f"휴장 규정 값 형식 오류: {self.type}={self.value}")
        return self


def _is_date(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


class FacilityRules(BaseModel):
    facility_id: str
    name: str
    district: str | None = None
    source_id: str
    info: FacilityInfo = FacilityInfo()
    closure_notes: list[PeriodNote] = []
    closure_rules: list[ClosureRule] = []
    # 공통 공휴일 목록을 저장소에서 붙인다. 없으면 모든 날짜의 공휴일 여부를 알 수 없다.
    holiday_calendar: HolidayCalendar | None = None
    fee_rules: list[FeeRule] = []
    discount_rules: list[DiscountRule] = []
    # 비어 있으면 취소 환불을 계산하지 않고 확인 필요로 안내한다.
    refund_rules: list[RefundRule] = []
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
        """이용일에 유효한 규정 기간의 출처. 기간별 규정이 없거나 기간에 출처가 없으면 시설 출처, 유효한 기간이 없으면 None"""
        if not self.terms_by_period:
            return self.source_id
        period = self._period_terms(day)
        if period is None:
            return None
        return period.source_id or self.source_id

    @property
    def sports(self) -> set[str]:
        """요금을 계산할 수 있는 종목. 규정과 어긋나지 않도록 따로 저장하지 않는다."""
        return {rule.sport for rule in self.fee_rules if rule.type == "base"}

    @model_validator(mode="after")
    def check_sources(self) -> "FacilityRules":
        known = {source.source_id for source in self.sources}
        rules = [*self.fee_rules, *self.discount_rules, *self.time_policies, *self.closure_notes, *self.closure_rules]
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
        "facility_closed",
        # 금액 계산에 필요한 결제액·끝전 처리 등이 확인되지 않음
        "amount_unverified",
    ]
    target: Literal["base", "lighting", "discount", "checklist", "time", "refund"]
    reason: str
    source_id: str


class FeeResult(BaseModel):
    status: Literal["calculated", "needs_review", "not_eligible"]
    items: list[FeeItem]
    total: int | None
    payment_due: int | None
    # 결제 방식이 확인된 온라인 선결제액. payment_due가 None이어도 계산했으면 값이 있다.
    online_prepay: int | None
    # 이용 당일 현장에서 따로 내는 금액. payment_due에는 들어가지 않는다.
    onsite_payment: int | None
    # 결제 방식을 확인하지 못한 금액. 0보다 크면 payment_due는 None이다.
    payment_unverified: int | None
    expected_refund: int | None
    net_cost_after_refund: int | None
    review_items: list[ReviewItem]


class CancelRefund(BaseModel):
    """취소·미이용 시 예상 환불. fee.expected_refund(감면 환급)와는 별개다.

    환불 대상은 온라인으로 먼저 낸 금액(fee.online_prepay)이다. 현장 결제·결제 방식 미확인 금액이나 감면 환급이
    섞이면 실제로 돌려받는 범위를 확인할 수 없어 금액을 내지 않는다.
    """

    status: Literal["calculated", "needs_review"]
    reason: RefundReason
    # 이용일 며칠 전 취소인지. 사용자 취소일 때만 값이 있다.
    days_before: int | None
    rate_percent: int | None
    refund_amount: int | None
    # 환불 후에도 내는 금액(온라인 선결제액 − 환불액)
    cost_after_refund: int | None
    # 적용한 환불 규정의 신청 방법·환급 시기
    note: str | None
    # 적용한 환불 규정의 출처. 규정을 고르지 못했으면 None이고, 안내할 출처는 review_items에 있다.
    source_id: str | None
    review_items: list[ReviewItem]


class CompareResult(BaseModel):
    facility_id: str
    facility_name: str
    fee: FeeResult
    terms: Terms
    checklist: list[str]
    checklist_review_items: list[ReviewItem]
    sources: list[Source]
    # conditions.cancellation을 보낸 경우에만 값이 있다.
    cancel_refund: CancelRefund | None = None


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
