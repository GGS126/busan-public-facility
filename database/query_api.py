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
    return fetch(db,'''SELECT category_id,category_name,percent,basis,applies_to,excluded_from,
    processing,deadline,documents,source_url,checked_on
    FROM v_facility_discounts WHERE facility_id=? AND ? BETWEEN effective_from AND effective_to
    ORDER BY category_name''',(facility_id,use_date))

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
    parser.add_argument('resource',choices=['facilities','pricing','slots','duration_prices','quote','duration_quote','optional_lighting','options','discounts','refunds'])
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
        elif a.resource=='options':result=facility_options(a.db,a.facility,a.date)
        elif a.resource=='discounts':result=discounts(a.db,a.facility,a.date)
        elif a.resource=='refunds':result=refund_rules(a.db,a.facility,a.date)
        elif a.resource=='optional_lighting':result=optional_lighting_quote(a.db,a.facility,a.date,a.optional_lighting_minutes)
        else:
            if not a.start_time or not a.end_time:parser.error('--start-time, --end-time 필요')
            selected=a.discount_categories.split(',') if a.discount_categories else None
            result=quote(a.db,a.facility,a.date,a.start_time,a.end_time,is_weekend,a.optional_lighting_minutes,selected)
    print(json.dumps(result,ensure_ascii=False,indent=2))
