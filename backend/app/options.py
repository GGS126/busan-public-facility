"""직접 입력 화면의 선택지(API-05). 등록된 시설에 실제로 있는 값만 반환한다."""

from app.models import Option, OptionsResponse, RuleData


def build_options(data: RuleData) -> OptionsResponse:
    sports = {sport for facility in data.facilities for sport in facility.sports}
    districts = {facility.district for facility in data.facilities if facility.district is not None}
    discounts = {rule.discount_type for facility in data.facilities for rule in facility.discount_rules}

    return OptionsResponse(
        sports=[Option(code=code, label=data.labels.sports[code]) for code in sorted(sports)],
        districts=sorted(districts),
        discount_types=[Option(code=code, label=data.labels.discount_types[code]) for code in sorted(discounts)],
    )
