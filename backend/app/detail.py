"""시설 상세(API-03). 이용일에 유효한 이용시간 규정과 시설 기본정보를 묶는다."""

from datetime import date

from app.models import FacilityDetail, FacilityRules, TimeOption


def facility_detail(rules: FacilityRules, day: date) -> FacilityDetail:
    policies = sorted((p for p in rules.time_policies if p.in_effect(day)), key=lambda p: (p.sport, p.policy_id))
    notes = [note for note in rules.closure_notes if note.in_effect(day)]
    # 기간이 겹쳐 안내가 둘 이상이면 어느 쪽인지 알 수 없으므로 표시하지 않는다.
    closure = notes[0] if len(notes) == 1 else None

    source_id = rules.period_source_on(day)
    used = {source_id, *(p.source_id for p in policies)} - {None}
    if closure is not None:
        used.add(closure.source_id)

    return FacilityDetail(
        facility_id=rules.facility_id,
        name=rules.name,
        # 이용일에 적용되는 기본요금 규정이 있는 종목만. 규정 기간 밖이거나 그 달에 규정이 없으면 빠진다.
        sports=sorted(
            {
                r.sport
                for r in rules.fee_rules
                if r.type == "base" and r.in_effect(day) and (r.months is None or day.month in r.months)
            }
        ),
        district=rules.district,
        address=rules.info.address,
        phone=rules.info.phone,
        operating_hours=rules.info.operating_hours,
        closure_note=closure.note if closure is not None else None,
        booking_url=rules.info.booking_url,
        time_options=[
            TimeOption(**p.model_dump(include=set(TimeOption.model_fields))) for p in policies
        ],
        source_id=source_id,
        sources=[source for source in rules.sources if source.source_id in used],
    )
