# 시설별 공통 시간·요금 조회 (SQLite, Python 표준 라이브러리).
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def normalize_use_date(value):
    """허용되는 날짜 입력을 SQLite 비교용 YYYY-MM-DD 형식으로 통일한다."""
    if not isinstance(value, str):
        raise ValueError('이용일은 날짜 문자열이어야 합니다')
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError('이용일 날짜 형식 오류') from exc

def fetch(db,sql,params=()):
    con=sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory=sqlite3.Row
    try: return [dict(x) for x in con.execute(sql,params)]
    finally: con.close()

def facilities(db):
    return fetch(db,'SELECT id,name,facility_type,district,address,booking_url FROM facilities ORDER BY name')

def sources(db, facility_id=None, use_date=None):
    """출처의 재이용 조건을 확인 상태와 함께 조회한다.

    license=None이면 확인되지 않았다는 뜻이며 허락/금지를 단정하지 않는다.
    facility_id 단독 검색 또는 facility_id+use_date의 적용규정 검색을 지원한다.
    """
    if use_date is not None and facility_id is None:
        raise ValueError('이용일로 출처를 조회할 때 facility_id가 필요합니다')
    where = []
    params = []
    if facility_id is not None:
        where.append('r.facility_id=?')
        params.append(facility_id)
    if use_date is not None:
        where.append('? BETWEEN r.effective_from AND r.effective_to')
        params.append(normalize_use_date(use_date))
    condition = ' WHERE ' + ' AND '.join(where) if where else ''
    return fetch(db, """SELECT DISTINCT s.id AS source_id,s.url,s.title,s.checked_on,
        s.verification_level,s.license,
        CASE WHEN s.license IS NULL THEN 'unverified' ELSE 'confirmed' END AS license_status,
        s.note
        FROM sources s JOIN rule_sets r ON r.source_id=s.id"""
        + condition + ' ORDER BY s.id', tuple(params))


def closure_rules(db,facility_id,use_date):
    # 규정 적용기간 내의 정기 휴장 목록. 출처는 기존 rule_sets -> sources를 재사용.
    use_date=normalize_use_date(use_date)
    return fetch(db,'''SELECT c.closure_type AS type,c.closure_value AS value,c.note,
       r.effective_from,r.effective_to,s.url AS source_url,s.checked_on
       FROM closure_rules c JOIN rule_sets r ON r.id=c.rule_set_id
       JOIN sources s ON s.id=r.source_id
       WHERE r.facility_id=? AND ? BETWEEN r.effective_from AND r.effective_to
       ORDER BY c.closure_type,c.closure_value''',(facility_id,use_date))


def closure_status(db,facility_id,use_date,holiday_codes=None):
    # 명절 날짜를 변환하지 않는다. holiday_codes는 백엔드의 검증된 날짜 데이터가 공급한다.
    use_date=normalize_use_date(use_date)
    if holiday_codes is not None:
        if not isinstance(holiday_codes,(list,tuple,set)) or any(
                not isinstance(x,str) or x not in ('lunar_new_year_day','chuseok_day')
                for x in holiday_codes):
            raise ValueError('holiday_codes는 지원하는 명절 코드 목록이어야 합니다')
    active=fetch(db,'''SELECT r.id,s.url AS source_url FROM rule_sets r
       JOIN sources s ON s.id=r.source_id
       WHERE r.facility_id=? AND ? BETWEEN r.effective_from AND r.effective_to''',
       (facility_id,use_date))
    if not active:
        return {'status':'no_active_rule_set','facility_id':facility_id,
                'date':use_date,'is_closed':None,'matched_rules':[]}
    rules=closure_rules(db,facility_id,use_date)
    codes=set(holiday_codes or [])
    matched=[x for x in rules if
       (x['type']=='annual_date' and x['value']==use_date[5:]) or
       (x['type']=='exact_date' and x['value']==use_date) or
       (x['type']=='holiday_code' and x['value'] in codes)]
    if matched: status,closed='closed',True
    elif holiday_codes is None and any(x['type']=='holiday_code' for x in rules):
        status,closed='needs_calendar_resolution',None
    else: status,closed='no_scheduled_closure',False
    return {'status':status,'facility_id':facility_id,'date':use_date,
            'is_closed':closed,'matched_rules':matched,'source_url':active[0]['source_url'],
            'note':'임시 휴장·행사·별도 공지는 반영되지 않았습니다. 실제 예약 가능 여부는 공식 예약 사이트에서 확인해야 합니다.'}


def backend_time_policy(db, facility_id, use_date):
    """PR #19 TimePolicy와의 안전한 호환성 점검 및 변환 자료.

    확정되지 않은 허용 시간 목록을 임의 생성하지 않는다. compatible=True일 때만
    policy를 백엔드의 TimePolicy 모델에 전달할 수 있다.
    """
    use_date = normalize_use_date(use_date)
    rows = fetch(db, """SELECT r.id AS rule_set_id,r.effective_from,r.effective_to,
           f.facility_type,f.open_time,f.close_time,
           t.selection_type,t.available_start_time,t.available_end_time,
           t.min_minutes,t.max_minutes,t.step_minutes,t.daily_limit_minutes,t.note,
           s.id AS source_id,s.url AS source_url
       FROM rule_sets r JOIN facilities f ON f.id=r.facility_id
       JOIN time_selection_policies t ON t.rule_set_id=r.id
       JOIN sources s ON s.id=r.source_id
       WHERE r.facility_id=? AND ? BETWEEN r.effective_from AND r.effective_to
       ORDER BY r.id""", (facility_id, use_date))
    base = {'facility_id': facility_id, 'date': use_date}
    if not rows:
        return {**base, 'status': 'no_active_rule_set', 'compatible': False,
                'policy': None, 'review_items': [{'code':'rule_missing',
                'reason':'해당 이용일에 적용되는 이용시간 규정이 없습니다.'}]}
    if len(rows) != 1:
        return {**base, 'status':'needs_review','compatible':False,'policy':None,
                'review_items':[{'code':'rule_conflict',
                'reason':'동일 날짜에 유효한 이용시간 규정이 여러 개입니다.'}]}
    x = rows[0]
    common = {'policy_id': x['rule_set_id'] + '_time',
              'sport': x['facility_type'], 'effective_from':x['effective_from'],
              'effective_to':x['effective_to'], 'source_id':x['source_id']}
    if x['selection_type'] == 'fixed_slot':
        slots = fetch(db, """SELECT start_time,end_time FROM pricing_rules
            WHERE rule_set_id=? AND selection_type='fixed_slot'
            ORDER BY slot_no""", (x['rule_set_id'],))
        if not slots:
            return {**base, 'status':'needs_review','compatible':False,'policy':None,
                    'review_items':[{'code':'slot_missing','reason':'지정 회차 정보가 없습니다.'}]}
        policy = {**common,'selection':'fixed_slot','slots':slots,
                  'allowed_minutes':[], 'open_time':x['open_time'],
                  'close_time':x['close_time']}
        return {**base,'status':'compatible','compatible':True,
                'policy':policy,'source_url':x['source_url'],'review_items':[]}
    if x['selection_type'] == 'flexible_interval':
        # 120분 기준 요금이 있다는 사실만으로 60분·120분만 허용한다고 단정할 수 없다.
        # max_minutes=120, step_minutes=NULL 등으로는 정확한 allowed_minutes를 복원할 수 없다.
        return {**base,'status':'needs_review','compatible':False,'policy':None,
                'source_url':x['source_url'],
                'known_constraints':{'selection':'flexible',
                    'open_time':x['available_start_time'] or x['open_time'],
                    'close_time':x['available_end_time'] or x['close_time'],
                    'min_minutes':x['min_minutes'],'max_minutes':x['max_minutes'],
                    'step_minutes':x['step_minutes'],
                    'daily_limit_minutes':x['daily_limit_minutes'],
                    'priced_duration_minutes':[x['duration_minutes'] for x in fetch(db,
                        "SELECT DISTINCT duration_minutes FROM pricing_rules WHERE rule_set_id=? ORDER BY duration_minutes",
                        (x['rule_set_id'],))]},
                'review_items':[{'code':'allowed_minutes_unverified',
                    'reason':'PR #19의 flexible 형식은 허용 이용시간 목록(allowed_minutes)이 필수이나, 공식 자료에서 정확한 목록이 확인되지 않았습니다. 2시간 요금과 최대 2시간 제한을 근거로 60분/120분만 허용한다고 추정하지 않습니다.'}]}
    return {**base,'status':'needs_review','compatible':False,'policy':None,
            'review_items':[{'code':'selection_unknown','reason':'알 수 없는 이용시간 선택 형식입니다.'}]}


def pricing_rules(db,facility_id,use_date,is_weekend_or_holiday):
    use_date=normalize_use_date(use_date)
    if type(is_weekend_or_holiday) is not bool: raise ValueError('is_weekend_or_holiday는 bool 필수')
    col='weekend_holiday_base_won' if is_weekend_or_holiday else 'weekday_base_won'
    return fetch(db,f'''SELECT p.id AS price_rule_id,p.rule_set_id,p.selection_type,p.slot_no,p.start_time,p.end_time,
       p.duration_minutes,p.{col} AS base_fee_won,p.mandatory_light_won,
       p.{col}+p.mandatory_light_won AS initial_payment_won,
       ts.available_start_time,ts.available_end_time,ts.min_minutes,ts.max_minutes,ts.step_minutes,ts.daily_limit_minutes,
       s.id AS source_id,s.url AS source_url,s.checked_on
       FROM pricing_rules p JOIN rule_sets r ON r.id=p.rule_set_id
       JOIN sources s ON s.id=r.source_id
       JOIN time_selection_policies ts ON ts.rule_set_id=r.id
       WHERE r.facility_id=? AND ? BETWEEN r.effective_from AND r.effective_to
       ORDER BY p.slot_no,p.duration_minutes''',(facility_id,use_date))

def slots(db,facility_id,use_date,is_weekend_or_holiday):
    return [p for p in pricing_rules(db,facility_id,use_date,is_weekend_or_holiday) if p['selection_type']=='fixed_slot']

def duration_prices(db,facility_id,use_date):
    return [p for p in pricing_rules(db,facility_id,use_date,False) if p['selection_type']=='flexible_interval']

def discounts(db,facility_id,use_date):
    use_date=normalize_use_date(use_date)
    return fetch(db,'''SELECT category_id,category_name,percent,guardian_max_count,guardian_condition,guardian_evidence_note,discount_rounding_policy,
    CASE WHEN discount_rounding_policy IS NULL THEN 'unverified' ELSE 'confirmed' END AS rounding_status,
    basis,applies_to,excluded_from,
    processing,deadline,documents,source_url,checked_on
    FROM v_facility_discounts WHERE facility_id=? AND ? BETWEEN effective_from AND effective_to
    ORDER BY category_name''',(facility_id,use_date))

def discount_proration_check(db, facility_id, use_date, base_fee_won,
                              participant_count, eligible_count, category_id,
                              guardian_count=None, severe_disabled_count=None):
    """DB 규정의 비례 감면 정합성 검사. 결제/API 오류 생성은 백엔드 책임.

    끝전/인원별 배분의 공식 규칙이 불명확하면 환급·최종 금액은 반환하지 않는다.
    """
    from fractions import Fraction
    if type(base_fee_won) is not int or base_fee_won < 0:
        raise ValueError('기본요금은 0 이상의 정수여야 합니다')
    if (type(participant_count) is not int or participant_count <= 0 or
        type(eligible_count) is not int or not (0 <= eligible_count <= participant_count)):
        raise ValueError('참여인원 및 감면 대상 인원 오류')
    rules = {r['category_id']:r for r in discounts(db, facility_id, use_date)}
    if category_id not in rules:
        raise ValueError('등록되지 않은 감면 유형')
    rule = rules[category_id]
    # 보호자 규정은 각 시설의 JSON에 확인된 상한이 있을 때만 적용한다.
    # NULL은 미확인: 보호자 감면을 허용한다고 추측해서는 안 된다.
    if category_id == 'disabled' and eligible_count > 0:
        if rule['guardian_max_count'] == 1:
            if (type(guardian_count) is not int or type(severe_disabled_count) is not int or
                guardian_count < 0 or severe_disabled_count < 0 or
                guardian_count > eligible_count or severe_disabled_count > eligible_count - guardian_count):
                return {'status':'needs_review','discount_refund_won':None,
                        'net_court_fee_won':None,'review_items':[{'code':'guardian_counts_required',
                        'reason':'보호자 감면 규정이 확인된 시설은 보호자 수와 중증 장애인 본인 수를 구분해 입력해야 합니다.'}]}
            if guardian_count > 1 or (guardian_count and severe_disabled_count < 1):
                return {'status':'needs_review','discount_refund_won':None,
                        'net_court_fee_won':None,'review_items':[{'code':'guardian_limit_exceeded',
                        'reason':'해당 시설의 보호자 감면은 중증 장애인 동반 시 최대 1명입니다.'}]}
        elif guardian_count not in (None, 0):
            return {'status':'needs_review','discount_refund_won':None,
                    'net_court_fee_won':None,'review_items':[{'code':'guardian_policy_unverified',
                    'reason':'해당 시설에서 보호자 감면 허용 여부 또는 상한이 확인되지 않았습니다.'}]}
        elif severe_disabled_count not in (None, 0):
            # 장애인 본인 수만 제공되는 경우에는 감면 대상 총 인원에 포함돼야 한다.
            if type(severe_disabled_count) is not int or not (0 <= severe_disabled_count <= eligible_count):
                raise ValueError('중증 장애인 본인 인원 오류')
    elif guardian_count not in (None, 0) or severe_disabled_count not in (None, 0):
        raise ValueError('보호자 인원 입력은 장애인 감면에만 사용합니다')
    base = {'facility_id': facility_id, 'date': normalize_use_date(use_date),
            'base_fee_won':base_fee_won, 'participant_count':participant_count,
            'eligible_count':eligible_count, 'discount_category_id':category_id,
            'rounding_policy':rule['discount_rounding_policy'],
            'rounding_status':rule['rounding_status'],
            'source_url':rule['source_url'], 'checked_on':rule['checked_on']}
    if rule['basis'] != 'per_eligible_person_equal_split':
        return {**base,'status':'needs_review','discount_refund_won':None,
                'net_court_fee_won':None,'review_items':[{'code':'discount_proration_unverified',
                'reason':'인원별 기본요금 배분 공식이 확인되지 않았습니다.'}]}
    if eligible_count == 0:
        return {**base, 'status':'confirmed', 'discount_refund_won':0,
                'net_court_fee_won':base_fee_won}
    # 감면이 이용자마다 다른 경우는 해당 자격의 합산 규칙을 별도로 확인해야 한다.
    refund_per_person = Fraction(base_fee_won * rule['percent'], participant_count * 100)
    policy = rule['discount_rounding_policy']
    # 'per_eligible_person_equal_split'은 1인당 반환액을 먼저 계산하는 방식.
    # 각 감면 대상자의 반환액을 원 단위로 처리한 후 인원수만큼 합산한다.
    if refund_per_person.denominator == 1:
        rounded_per_person = int(refund_per_person)
    elif policy is None:
        return {**base,'status':'needs_review','discount_refund_won':None,
                'net_court_fee_won':None,'review_items':[{'code':'discount_rounding_unverified',
                'reason':'인원별 감면액에 원 미만의 끝전이 발생하지만 공식 처리 기준이 확인되지 않았습니다.'}]}
    elif policy == 'round_half_up':
        rounded_per_person = (2 * refund_per_person.numerator + refund_per_person.denominator) // (2 * refund_per_person.denominator)
    elif policy == 'floor_won':
        rounded_per_person = refund_per_person.numerator // refund_per_person.denominator
    elif policy == 'ceil_won':
        rounded_per_person = -(-refund_per_person.numerator // refund_per_person.denominator)
    elif policy in ('truncate_10_won', 'truncate_100_won'):
        unit = 10 if policy == 'truncate_10_won' else 100
        rounded_per_person = (refund_per_person.numerator // (refund_per_person.denominator * unit)) * unit
    else:
        # DB의 CHECK 제약과 별개로 알 수 없는 정책을 계산에 사용하는 것을 방지한다.
        return {**base,'status':'needs_review','discount_refund_won':None,
                'net_court_fee_won':None,'review_items':[{'code':'discount_rounding_unknown',
                'reason':'DB의 감면 끝전 처리 정책을 해석할 수 없습니다.'}]}
    refund = rounded_per_person * eligible_count
    return {**base,'status':'confirmed','discount_refund_won':refund,
            'net_court_fee_won':base_fee_won-refund}

def discount_selection_review(db, facility_id, use_date, category_ids):
    """중복 적용 근거가 없는 복수 감면은 금액을 산출하지 않는다.

    이 함수는 감면 자격의 존재만 조회한다. 중복 선택 시 더 높은 감면율을
    임의로 택하거나 두 감면율을 합산하지 않는다.
    """
    if category_ids is None:
        return None
    if not isinstance(category_ids, (list, tuple)) or any(
        not isinstance(code, str) or not code.strip() for code in category_ids
    ):
        raise ValueError('감면 대상은 문자열 ID 목록이어야 합니다')
    selected = list(dict.fromkeys(category_ids))
    if not selected:
        return None
    rules = discounts(db, facility_id, use_date)
    by_category = {rule['category_id']: rule for rule in rules}
    unknown = [code for code in selected if code not in by_category]
    if unknown:
        raise ValueError('해당 시설 및 이용일에 등록되지 않은 감면 대상: ' + ', '.join(unknown))
    if len(selected) < 2:
        return None
    matched = [by_category[code] for code in selected]
    return {
        'status': 'needs_review',
        'reason': '복수 감면 자격의 중복 적용 기준이 공식 자료로 확인되지 않았습니다.',
        'facility_id': facility_id,
        'date': normalize_use_date(use_date),
        'selected_discount_categories': selected,
        'selected_discount_rules': [
            {'category_id': r['category_id'], 'category_name': r['category_name'],
             'percent': r['percent'], 'source_url': r['source_url'],
             'checked_on': r['checked_on']}
            for r in matched
        ],
        'base_fee_won': None,
        'lighting_fee_won': None,
        'discount_won': None,
        'total_won': None,
        'payment_due': None,
        'expected_refund': None,
        'net_cost_after_refund': None,
        'review_items': [{
            'code': 'discount_stacking_unverified',
            'target': 'discount',
            'reason': '여러 감면 자격을 동시에 충족할 때 합산·최고율 적용 등 처리 기준이 확인되지 않았습니다.',
            'source_urls': list(dict.fromkeys(r['source_url'] for r in matched)),
            'checked_on': [r['checked_on'] for r in matched]
        }]
    }

def refund_rules(db,facility_id,use_date):
    use_date=normalize_use_date(use_date)
    return fetch(db,'''SELECT rr.reason,rr.days_before_min,rr.days_before_max,rr.rate_percent,
    rr.channel,rr.condition,rr.status FROM refund_rules rr JOIN rule_sets r ON r.id=rr.rule_set_id
    WHERE r.facility_id=? AND ? BETWEEN r.effective_from AND r.effective_to''',(facility_id,use_date))

def facility_options(db,facility_id,use_date):
    use_date=normalize_use_date(use_date)
    records=fetch(db,'''SELECT o.*,c.name AS option_name FROM facility_options o
        JOIN option_categories c ON c.id=o.option_id JOIN rule_sets r ON r.id=o.rule_set_id
        WHERE r.facility_id=? AND ? BETWEEN r.effective_from AND r.effective_to
        ORDER BY o.option_id,o.id''',(facility_id,use_date))
    return records

def option_charge(minutes,rule):
    if type(minutes) is not int or minutes<0: raise ValueError('옵션 사용시간 오류')
    if minutes==0:return {'status':'priced','amount_won':0,'billed_minutes':0}
    unit=60; price=rule['hour_price']
    typ=rule['calculation_type']
    if typ=='hour_blocks_plus_steps':
        step=rule['extra_unit_minutes']; step_price=rule['extra_unit_price']
        hours,extra=divmod(minutes,unit)
        steps=(extra+step-1)//step
        return {'status':'priced','amount_won':hours*price+steps*step_price,
                'billed_minutes':hours*unit+steps*step}
    if typ in ('rounded_units','time_overlap_units'):
        if rule['rounding_policy']=='round_up':blocks=(minutes+unit-1)//unit
        elif rule['rounding_policy']=='exact_units':
            if minutes%unit:return {'status':'option_calculation_unavailable'}
            blocks=minutes//unit
        elif rule['rounding_policy']=='proportional_if_exact':
            numerator=minutes*price
            if numerator%unit:return {'status':'option_calculation_unavailable'}
            return {'status':'priced','amount_won':numerator//unit,'billed_minutes':minutes}
        return {'status':'priced','amount_won':blocks*price,'billed_minutes':blocks*unit}
    if typ in ('flat','per_item'):
        return {'status':'priced','amount_won':price,'billed_minutes':minutes}
    raise ValueError('지원하지 않는 옵션 계산')

def optional_lighting_quote(db,facility_id,use_date,lighting_minutes,options=None):
    if type(lighting_minutes) is not int or lighting_minutes<0:raise ValueError('조명 이용시간 오류')
    if not lighting_minutes:return {'status':'priced','lighting_minutes':0,'optional_lighting_fee_won':0}
    if options is None:
        options=facility_options(db,facility_id,use_date)
    rules=[r for r in options if r['option_id']=='lighting' and r['application_type']=='optional']
    if not rules:return {'status':'optional_lighting_not_supported'}
    if len(rules)!=1:raise ValueError('중복 조명 옵션')
    result=option_charge(lighting_minutes,rules[0])
    if result['status']!='priced':return result
    return {'status':'priced','lighting_minutes':lighting_minutes,'optional_lighting_fee_won':result['amount_won'],
            'billed_lighting_minutes':result['billed_minutes'],'optional_before_time':rules[0]['applies_to']}

def quote(db,facility_id,use_date,start_time,end_time,is_weekend_or_holiday,optional_lighting_minutes=0,discount_category_ids=None):
    # 동일 요청 형식으로 고정 회차와 자유 선택의 기본요금 및 조명료를 계산.
    use_date=normalize_use_date(use_date)
    if type(is_weekend_or_holiday) is not bool: raise ValueError('주말·공휴일 판정은 bool이어야 합니다')
    if type(optional_lighting_minutes) is not int or optional_lighting_minutes<0: raise ValueError('선택 조명 이용시간 오류')
    def parse(t,allow_24=False):
        if allow_24 and t=='24:00':return 1440
        if len(t)!=5 or t[2]!=':':raise ValueError('시간은 HH:MM 형식')
        h,m=int(t[:2]),int(t[3:]);
        if not (0<=h<=23 and 0<=m<=59):raise ValueError('시간 범위 오류')
        return h*60+m
    start,end=parse(start_time),parse(end_time,True)
    if end<=start:raise ValueError('종료시간은 시작시간 이후여야 합니다')
    duration=end-start
    prices=pricing_rules(db,facility_id,use_date,is_weekend_or_holiday)
    if not prices:return {'status':'not_available','reason':'적용기간 내 요금 규정 없음'}
    typ=prices[0]['selection_type']
    if typ=='fixed_slot':
        matches=[r for r in prices if r['start_time']==start_time and r['end_time']==end_time]
    else:
        # 자유시간형은 시간 정책을 요금 규칙 존재 여부와 독립적으로 확인한다.
        # 요금 규칙이 없을 뿐인 60/90분은 무조건 이용 불가로 처리하지 않는다.
        policy=prices[0]
        min_start=parse(policy['available_start_time']) if policy['available_start_time'] else 0
        max_end=parse(policy['available_end_time'],True) if policy['available_end_time'] else 1440
        step=policy['step_minutes']
        if (start<min_start or end>max_end
            or (step is not None and (start-min_start)%step)
            or (policy['min_minutes'] is not None and duration<policy['min_minutes'])
            or (policy['max_minutes'] is not None and duration>policy['max_minutes'])
            or (policy['daily_limit_minutes'] is not None and duration>policy['daily_limit_minutes'])):
            return {'status':'invalid_time','reason':'해당 시설의 이용시간 정책에 맞지 않는 시간'}
        matches=[r for r in prices if r['duration_minutes']==duration]
        if not matches:
            return {
                'status':'needs_review',
                'facility_id':facility_id,'date':use_date,
                'start_time':start_time,'end_time':end_time,
                'duration_minutes':duration,
                'base_fee_won':None,'lighting_fee_won':None,'total_won':None,
                'payment_due':None,'expected_refund':None,'net_cost_after_refund':None,
                'review_items':[{
                    'code':'rule_missing','target':'base',
                    'reason':'해당 이용시간의 공식 기본요금 규정이 확인되지 않아 요금을 계산할 수 없습니다. 이용 가능 여부도 공식 예약 규정으로 확인해야 합니다.',
                    'source_id':policy['source_id'],
                    'source_url':policy['source_url'],
                    'checked_on':policy['checked_on']
                }],
                'booking_availability_verified':False
            }
    if not matches:return {'status':'invalid_time','reason':'해당 시설에서 선택할 수 없는 시간 또는 이용시간'}
    if len(matches)!=1:raise ValueError('중복된 요금 규정')
    discount_review=discount_selection_review(db,facility_id,use_date,discount_category_ids)
    if discount_review is not None:
        discount_review.update(start_time=start_time, end_time=end_time)
        return discount_review
    p=matches[0];light=p['mandatory_light_won']; light_minutes=0
    # 견적 1회당 옵션 조회도 1회만 수행해 이후 계산에서 재사용한다.
    facility_option_records=facility_options(db,facility_id,use_date)
    if typ=='flexible_interval':
        records=[r for r in facility_option_records if r['option_id']=='lighting' and r['application_type']=='mandatory_when_applicable']
        if len(records)>1:raise ValueError('조명 옵션 중복')
        if records:
            h=records[0];threshold=parse(h['applies_from']) if h['applies_from'] else 0
            boundary=parse(h['applies_to'],True) if h['applies_to'] else 1440
            light_minutes=max(0,min(end,boundary)-max(start,threshold))
            result=option_charge(light_minutes,h)
            if result['status']!='priced':
                return {'status':'lighting_calculation_unavailable','base_fee_won':p['base_fee_won'],'lighting_fee_won':None,'total_won':None}
            light=result['amount_won']
    # 고정회차에 포함된 필수 옵션의 요금은 pricing_rules에 이미 존재한다.
    # 별도 옵션 규칙을 조회하더라도 같은 요금을 중복 합산하지 않는다.
    if typ=='fixed_slot' and p['mandatory_light_won']:
        included=[r for r in facility_option_records
                  if r['option_id']=='lighting' and r['application_type']=='included_in_base_price'
                  and parse(r['applies_from'])<=start and end<=parse(r['applies_to'])]
        if not included:
            return {'status':'option_rule_inconsistent','reason':'필수 조명 포함 회차의 옵션 규칙이 일치하지 않음'}
    optional=optional_lighting_quote(db,facility_id,use_date,optional_lighting_minutes,options=facility_option_records)
    if optional['status']!='priced':return optional
    if optional_lighting_minutes:
        if typ!='fixed_slot' or p['mandatory_light_won'] or optional_lighting_minutes>duration:
            return {'status':'invalid_optional_lighting','reason':'선택 조명은 필수 조명료가 포함되지 않은 고정 회차에서만 사용 가능'}
        options=[r for r in facility_option_records
                 if r['option_id']=='lighting' and r['application_type']=='optional']
        if len(options)!=1:
            return {'status':'invalid_optional_lighting','reason':'선택 조명 규칙 없음'}
        r=options[0]
        if start<parse(r['applies_from']) or end>parse(r['applies_to']):
            return {'status':'invalid_optional_lighting','reason':'선택 조명 가능 시간 밖의 회차'}
    # 단일 감면은 이 함수에서 적용하지 않는다: 반환 금액은 감면 전 금액이다.
    single_discount_selected=bool(discount_category_ids)
    return {'status':'priced','facility_id':facility_id,'date':use_date,'selection_type':typ,
            'start_time':start_time,'end_time':end_time,'duration_minutes':duration,
            'price_rule_id':p['price_rule_id'],'base_fee_won':p['base_fee_won'],
            'lighting_minutes':light_minutes,'lighting_fee_won':light,
            'total_won':p['base_fee_won']+light+optional['optional_lighting_fee_won'],
            'optional_lighting_minutes':optional_lighting_minutes,
            'optional_lighting_on_site_won':optional['optional_lighting_fee_won'],
            'booking_availability_verified':False,
            'discount_application_status':'not_calculated' if single_discount_selected else 'not_requested'}

duration_quote=quote
if __name__=='__main__':
    parser=argparse.ArgumentParser(description='공통 시설 요금 조회')
    parser.add_argument('resource',choices=['facilities','pricing','slots','duration_prices','quote','duration_quote','optional_lighting','options','discounts','refunds','backend_time_policy'])
    parser.add_argument('--facility');parser.add_argument('--date');parser.add_argument('--weekend',choices=['true','false'])
    parser.add_argument('--start-time');parser.add_argument('--end-time')
    parser.add_argument('--optional-lighting-minutes',type=int,default=0)
    parser.add_argument('--discount-categories',help='감면 대상 ID를 쉼표로 구분 (예: independence_merit,disabled)')
    parser.add_argument('--db',default=str(ROOT/'facilities.sqlite3'))
    a=parser.parse_args()
    if a.resource=='facilities':result=facilities(a.db)
    else:
        if not a.facility or not a.date:parser.error('--facility, --date 필요')
        if a.resource in ('pricing','slots','quote','duration_quote') and a.weekend is None:parser.error('--weekend 필요')
        is_weekend=a.weekend=='true'
        if a.resource=='pricing':result=pricing_rules(a.db,a.facility,a.date,is_weekend)
        elif a.resource=='slots':result=slots(a.db,a.facility,a.date,is_weekend)
        elif a.resource=='duration_prices':result=duration_prices(a.db,a.facility,a.date)
        elif a.resource=='backend_time_policy':result=backend_time_policy(a.db,a.facility,a.date)
        elif a.resource=='options':result=facility_options(a.db,a.facility,a.date)
        elif a.resource=='discounts':result=discounts(a.db,a.facility,a.date)
        elif a.resource=='refunds':result=refund_rules(a.db,a.facility,a.date)
        elif a.resource=='optional_lighting':result=optional_lighting_quote(a.db,a.facility,a.date,a.optional_lighting_minutes)
        else:
            if not a.start_time or not a.end_time:parser.error('--start-time, --end-time 필요')
            selected=a.discount_categories.split(',') if a.discount_categories else None
            result=quote(a.db,a.facility,a.date,a.start_time,a.end_time,is_weekend,a.optional_lighting_minutes,selected)
    print(json.dumps(result,ensure_ascii=False,indent=2))
