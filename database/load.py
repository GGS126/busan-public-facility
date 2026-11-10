"""시설 원본 JSON -> SQLite. 원자적 재적재와 공통 감면 분류 적용."""
import argparse
import datetime as dt
import json
import sqlite3
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# 원본 문구의 묶음 감면유형을 '실제 명시된 유형'으로 세분화한다.
# 후손·가족 대상 요건은 원문 표현(original_group_label)과 증빙자료로 확인한다.
CATEGORY_NAMES = {
    'low_income': '기초생활수급자', 'disabled': '장애인',
    'independence_merit': '독립유공자 및 해당 유족·가족',
    'national_merit': '국가유공자 및 해당 유족·가족',
    'may18_merit': '5·18민주유공자 및 해당 유족·가족',
    'special_mission_merit': '특수임무유공자 및 해당 유족·가족',
    'righteous_injury': '의사상자 및 해당 유족·가족',
    'multi_child': '다자녀 가정', 'war_veteran': '참전유공자',
    'agent_orange': '고엽제 관련 대상자(환자 및 2세)',
    'pows': '등록 포로 및 억류지 출신 포로가족',
    'children_group': '체육행사 등에 참여하는 10명 이상 어린이',
}
# 각 원본 레코드가 포괄한 카테고리를 명시적 목록으로 펼친다.
GROUP_TO_CODES = {
    'low_income': ('low_income',), 'disabled': ('disabled',),
    'veterans': ('independence_merit', 'national_merit', 'may18_merit', 'special_mission_merit'),
    'merit_families': ('independence_merit', 'national_merit', 'may18_merit', 'special_mission_merit', 'righteous_injury'),
    'multichild': ('multi_child',), 'war_veteran': ('war_veteran',),
    'agent_orange': ('agent_orange',), 'pows': ('pows',),
    'children_group': ('children_group',),
    'independence_merit': ('independence_merit',),
    'national_merit': ('national_merit',),
    'may18_merit': ('may18_merit',),
    'special_mission_merit': ('special_mission_merit',),
    'righteous_injury': ('righteous_injury',),
    'multi_child': ('multi_child',),
    'agent_orange': ('agent_orange',),
    'pows': ('pows',),
    'war_veteran': ('war_veteran',),
}

def validate_options(options):
    if not isinstance(options,list): raise ValueError('options는 목록이어야 함')
    if len({(o['id'],o['application_type']) for o in options})!=len(options): raise ValueError('동일 적용 방식 옵션 중복')
    types=('hour_blocks_plus_steps','rounded_units','time_overlap_units','flat','per_item')
    for o in options:
        if not isinstance(o.get('id'),str) or not o['id'].strip(): raise ValueError('옵션 ID 누락')
        if not isinstance(o.get('name'),str) or not o['name'].strip(): raise ValueError('옵션 이름 누락')
        if o['calculation_type'] not in types: raise ValueError('옵션 계산방식 오류')
        if o['rounding_policy'] not in ('round_up','exact_units','proportional_if_exact'): raise ValueError('옵션 단위 정책 오류')
        if o['application_type'] not in ('optional','mandatory_when_applicable','included_in_base_price'): raise ValueError('옵션 적용 방식 오류')
        begin=o.get('applies_from'); finish=o.get('applies_to')
        if not isinstance(begin,str) or not isinstance(finish,str):
            raise ValueError('옵션 적용 시작·종료시간은 필수')
        try:
            start=dt.datetime.strptime(begin,'%H:%M')
            end=dt.datetime.strptime(finish,'%H:%M')
        except ValueError as exc:
            raise ValueError('옵션 적용시간 형식 오류') from exc
        if start>=end:
            raise ValueError('옵션 적용시간 순서 오류')
        if type(o.get('hour_price')) is not int or o['hour_price']<0:
            raise ValueError('시간당 옵션 요금 오류')
        extra_minutes=o.get('extra_unit_minutes')
        extra_price=o.get('extra_unit_price')
        if (extra_minutes is None) != (extra_price is None):
            raise ValueError('추가 단위 시간 및 금액은 함께 입력해야 함')
        if extra_minutes is not None:
            if type(extra_minutes) is not int or not (0<extra_minutes<60) or 60%extra_minutes:
                raise ValueError('추가 요금 단위는 60분의 약수여야 함')
            if type(extra_price) is not int or extra_price<0:
                raise ValueError('추가 요금 금액 오류')
        if o['calculation_type']=='hour_blocks_plus_steps' and extra_minutes is None:
            raise ValueError('남은시간 계산 단위 누락')
        if o['calculation_type']!='hour_blocks_plus_steps' and extra_minutes is not None:
            raise ValueError('이 계산 방식에는 추가 단위 요금 불필요')

def insert_options(con,rid,options):
    validate_options(options)
    for o in options:
        con.execute('INSERT OR IGNORE INTO option_categories(id,name) VALUES(?,?)',(o['id'],o['name']))
        option_id=rid+'_'+o['id']+'_'+o['application_type']
        con.execute('''INSERT INTO facility_options
          (id,rule_set_id,option_id,calculation_type,application_type,rounding_policy,applies_from,applies_to,note,hour_price,extra_unit_minutes,extra_unit_price)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
          (option_id,rid,o['id'],o['calculation_type'],o['application_type'],o['rounding_policy'],o.get('applies_from'),o.get('applies_to'),o.get('note'),o['hour_price'],o.get('extra_unit_minutes'),o.get('extra_unit_price')))

CLOSURE_HOLIDAY_CODES = frozenset(('lunar_new_year_day', 'chuseok_day'))

def validate_closure_rules(d):
    rules = d.get('closure_rules')
    if not isinstance(rules,list):
        raise ValueError('closure_rules는 빈 목록을 포함해 반드시 목록이어야 합니다')
    seen = set()
    for item in rules:
        if not isinstance(item,dict):
            raise ValueError('휴장 규정 객체 형식 오류')
        typ, val, note = item.get('type'), item.get('value'), item.get('note')
        if not isinstance(val,str) or not val.strip() or not isinstance(note,str) or not note.strip():
            raise ValueError('휴장 규정 값 또는 안내 누락')
        if typ == 'annual_date':
            try:
                mm, dd = map(int,val.split('-'))
                if val != f'{mm:02d}-{dd:02d}': raise ValueError()
                dt.date(2024,mm,dd)
            except (ValueError,TypeError) as exc:
                raise ValueError('휴장 양력 반복일 형식 오류 (MM-DD)') from exc
        elif typ == 'exact_date':
            try:
                if dt.date.fromisoformat(val).isoformat() != val: raise ValueError()
            except ValueError as exc:
                raise ValueError('휴장 날짜 형식 오류 (YYYY-MM-DD)') from exc
            if not d['rule_set']['effective_from'] <= val <= d['rule_set']['effective_to']:
                raise ValueError('휴장 날짜가 규정 적용기간 밖입니다')
        elif typ == 'holiday_code':
            if val not in CLOSURE_HOLIDAY_CODES:
                raise ValueError('지원하지 않는 휴장 명절 코드: '+val)
        else:
            raise ValueError('휴장 규정 유형 오류')
        if (typ,val) in seen: raise ValueError('중복 휴장 규정')
        seen.add((typ,val))


def insert_closure_rules(con,rid,d):
    for i,item in enumerate(d['closure_rules'],1):
        con.execute('INSERT INTO closure_rules (id,rule_set_id,closure_type,closure_value,note) VALUES(?,?,?,?,?)',
                    (f'{rid}_closure_{i}',rid,item['type'],item['value'],item['note']))


def validate_shared(d):
    """모든 시설 형식에 적용할 필수 데이터 및 날짜·환불·예약 검증."""
    for section in ('facility', 'source', 'rule_set', 'reservation'):
        if not isinstance(d.get(section), dict):
            raise ValueError(f'{section} 객체 누락 또는 형식 오류')
    for section, keys in {
        'facility': ('id', 'name', 'facility_type', 'district', 'address', 'booking_url'),
        'source': ('id', 'url', 'title', 'checked_on', 'verification_level'),
        'rule_set': ('id', 'effective_from', 'effective_to', 'status'),
    }.items():
        for key in keys:
            value = d[section].get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{section}.{key} 누락')
    source, rule_set = d['source'], d['rule_set']
    for key, value in (('source.checked_on', source['checked_on']),
                       ('rule_set.effective_from', rule_set['effective_from']),
                       ('rule_set.effective_to', rule_set['effective_to'])):
        try:
            normalized = dt.date.fromisoformat(value).isoformat()
        except (ValueError, TypeError) as exc:
            raise ValueError(f'{key} 날짜 오류') from exc
        section, field = key.split('.')
        d[section][field] = normalized
    if rule_set['effective_from'] > rule_set['effective_to']:
        raise ValueError('규정 적용기간 순서 오류')
    validate_closure_rules(d)
    if source['verification_level'] not in ('official_page_verified', 'user_transcribed_official'):
        raise ValueError('출처 검증 분류 오류')
    if rule_set['status'] != 'confirmed':
        raise ValueError('규정 상태 오류')
    booking = d['reservation']
    for key in ('online_open_days_before', 'online_close_days_before',
                'normal_cancel_online_min_days_before'):
        value = booking.get(key)
        if type(value) is not int or value < 0:
            raise ValueError(f'reservation.{key} 오류')
    if booking['online_open_days_before'] < booking['online_close_days_before']:
        raise ValueError('예약 신청 가능 기간 순서 오류')
    refunds = d.get('refunds')
    if not isinstance(refunds, list) or not refunds:
        raise ValueError('환불 규정 목록 누락')
    ids = set()
    for refund in refunds:
        if not isinstance(refund, dict):
            raise ValueError('환불 규정 형식 오류')
        key = refund.get('id')
        if not isinstance(key, str) or not key.strip() or key in ids:
            raise ValueError('환불 규정 ID 누락 또는 중복')
        ids.add(key)
        for bound in ('min', 'max'):
            val = refund.get(bound)
            if val is not None and (type(val) is not int or val < 0):
                raise ValueError('환불 기준 일수 오류')
        if refund.get('min') is not None and refund.get('max') is not None and refund['min'] > refund['max']:
            raise ValueError('환불 기간 순서 오류')
        percent = refund.get('rate')
        if percent is not None and (type(percent) is not int or not 0 <= percent <= 100):
            raise ValueError('환불률 오류')
        for key_name in ('reason', 'channel', 'condition'):
            if not isinstance(refund.get(key_name), str) or not refund[key_name].strip():
                raise ValueError(f'환불 규정 {key_name} 누락')

def validate(d):
    validate_shared(d)
    for field in ('slots', 'options', 'discounts', 'discount_common'):
        if field not in d:
            raise ValueError(f'필수 키 누락: {field}')
    if not isinstance(d['slots'],list) or not d['slots']: raise ValueError('시간대 최소 1개 필요')
    seen=set()
    for slot in d['slots']:
        if slot['no'] in seen: raise ValueError('중복 회차')
        seen.add(slot['no'])
        a=dt.datetime.strptime(slot['from'],'%H:%M'); b=dt.datetime.strptime(slot['to'],'%H:%M')
        if int((b-a).total_seconds()/60)!=slot['minutes']: raise ValueError('회차 시간 불일치')
        for k in ('weekday','weekend','light'):
            if type(slot[k]) is not int or slot[k]<0: raise ValueError(f'회차 {slot["no"]}: {k} 요금 오류')
    validate_options(d['options'])
    common=d['discount_common']
    if type(common.get('percent')) is not int or not 0<=common['percent']<=100: raise ValueError('감면율 오류')
    codes=[]
    for discount in d['discounts']:
        if discount['id'] not in GROUP_TO_CODES: raise ValueError('알 수 없는 감면 분류: '+discount['id'])
        if 'percent' in discount and (type(discount['percent']) is not int or not 0 <= discount['percent'] <= 100):
            raise ValueError('개별 감면율 오류: '+discount['id'])
        codes.extend(GROUP_TO_CODES[discount['id']])
    if len(set(codes))!=len(codes): raise ValueError('동일 시설 감면 분류 중복')
    return d

def ensure_rule_set_period_available(con, facility_id, rule_set_id, start, end):
    """같은 시설에서 다른 규정의 적용기간이 겹치면 안전하게 거부한다.

    시작일·종료일은 모두 포함되며, 동일 규정 ID의 갱신은 허용한다.
    """
    existing = con.execute(
        'SELECT facility_id FROM rule_sets WHERE id=?', (rule_set_id,)
    ).fetchone()
    if existing is not None and existing[0] != facility_id:
        raise ValueError(
            f'규정 ID {rule_set_id}가 다른 시설({existing[0]})에서 사용 중입니다'
        )
    conflict = con.execute(
        'SELECT id, effective_from, effective_to FROM rule_sets '
        'WHERE facility_id=? AND id<>? '
        'AND effective_from<=? AND effective_to>=? LIMIT 1',
        (facility_id, rule_set_id, end, start)
    ).fetchone()
    if conflict is not None:
        old_id, old_start, old_end = conflict
        raise ValueError(
            f'같은 시설 규정의 적용기간이 중복됩니다: '
            f'{rule_set_id}({start}~{end}) / {old_id}({old_start}~{old_end}). '
            '기존 규정을 정리하거나 적용기간을 변경하세요.'
        )


def insert_shared_records(con, d):
    """시설·출처·규정의 공통 저장 경로 (고정 회차/자유시간형)."""
    f, s, r = d['facility'], d['source'], d['rule_set']
    rid = r['id']
    con.execute("""INSERT INTO facilities
        (id,name,facility_type,district,address,phone,booking_url,open_time,close_time,holiday_note)
        VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
        name=excluded.name, facility_type=excluded.facility_type,
        district=excluded.district, address=excluded.address, phone=excluded.phone, booking_url=excluded.booking_url,
        open_time=excluded.open_time, close_time=excluded.close_time,
        holiday_note=excluded.holiday_note""",
        tuple(f.get(key) for key in ('id','name','facility_type','district','address','phone',
                                     'booking_url','open_time','close_time','holiday_note')))
    con.execute("""INSERT INTO sources
        (id,url,title,checked_on,verification_level,note) VALUES(?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET url=excluded.url,title=excluded.title,
        checked_on=excluded.checked_on,verification_level=excluded.verification_level,
        note=excluded.note""",
        tuple(s.get(key) for key in ('id','url','title','checked_on','verification_level','note')))
    ensure_rule_set_period_available(con, f['id'], rid,
                                     r['effective_from'], r['effective_to'])
    con.execute('DELETE FROM rule_sets WHERE id=?', (rid,))
    con.execute("""INSERT INTO rule_sets
        (id,facility_id,source_id,effective_from,effective_to,status)
        VALUES(?,?,?,?,?,?)""",
        (rid, f['id'], s['id'], r['effective_from'], r['effective_to'], r['status']))
    return rid


def insert_refunds_and_reservation(con, rid, d):
    """두 적재 방식에서 동일하게 처리해야 하는 취소·예약 규정."""
    for item in d['refunds']:
        con.execute('INSERT INTO refund_rules VALUES(?,?,?,?,?,?,?,?,?)',
                    (f'{rid}_{item["id"]}', rid, item['reason'], item['min'],
                     item['max'], item['rate'], item['channel'], item['condition'],
                     'confirmed'))
    insert_closure_rules(con,rid,d)
    booking = d['reservation']
    con.execute('INSERT INTO reservation_rules VALUES(?,?,?,?,?)',
                (rid, booking['online_open_days_before'],
                 booking['online_close_days_before'],
                 booking['normal_cancel_online_min_days_before'],
                 booking.get('closure_note')))


def load_fixed(data_path, db_path):
    d=validate(json.loads(Path(data_path).read_text(encoding='utf-8')))
    db_path=Path(db_path)
    # 새로운 DB에만 schema 생성. 실제 적재는 한 번의 트랜잭션으로 진행.
    con=sqlite3.connect(db_path)
    con.execute('PRAGMA foreign_keys=ON')
    try:
        con.executescript((ROOT/'schema.sql').read_text(encoding='utf-8'))
        with con:
            rid = insert_shared_records(con, d)
            for t in d['slots']:
                con.execute('INSERT INTO pricing_rules VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (f'{rid}_slot{t["no"]}',rid,'fixed_slot',t['no'],t['from'],t['to'],t['minutes'],t['weekday'],t['weekend'],t['light']))
            con.execute('INSERT INTO time_selection_policies VALUES(?,?,?,?,?,?,?,?,?,?)',
                (rid,'fixed_slot',None,None,None,None,None,None,'confirmed','저장된 고정 회차만 선택 가능'))
            insert_options(con,rid,d['options'])
            c=d['discount_common']
            for item in d['discounts']:
                for code in GROUP_TO_CODES[item['id']]:
                    con.execute('INSERT OR IGNORE INTO discount_categories(id,name) VALUES(?,?)',(code,CATEGORY_NAMES[code]))
                    con.execute('''INSERT INTO facility_discounts
                        (id,rule_set_id,category_id,percent,basis,applies_to,excluded_from,
                         processing,documents,deadline,note,original_group_label)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (f'{rid}_{code}',rid,code,item.get('percent',c['percent']),c['basis'],c['applies_to'],c['excluded_from'],
                         c['processing'],c['documents'],c['deadline'],c['note'],item['category']))
            insert_refunds_and_reservation(con, rid, d)
    finally:
        con.close()


def validate_duration_discounts(d):
    """원본 JSON의 시설별 감면 정책을 검사하고, 추정 기본값을 만들지 않는다."""
    common = d.get('discount_common')
    if not isinstance(common, dict):
        raise ValueError('discount_common: 감면 규정 데이터 누락')
    for field in ('basis', 'applies_to', 'processing'):
        if not isinstance(common.get(field), str) or not common[field].strip():
            raise ValueError(f'discount_common.{field} 누락')
    # 구덕의 기존 루트 필드는 계속 지원하고 실제 감면 계산 기준과 일치시키되,
    # 다른 시설의 처리 기준을 특정 시설의 값으로 강제하지 않는다.
    basis = d.get('discount_calculation_policy')
    if basis is not None and basis != common['basis']:
        raise ValueError('discount_calculation_policy와 discount_common.basis 불일치')
    excluded = d.get('discount_excluded_fee_types')
    if not isinstance(excluded, list) or any(not isinstance(x, str) or not x.strip() for x in excluded):
        raise ValueError('discount_excluded_fee_types 목록 오류')
    if len(set(excluded)) != len(excluded):
        raise ValueError('감면 제외 요금 유형 중복')
    for field in ('documents', 'deadline', 'note'):
        if common.get(field) is not None and not isinstance(common[field], str):
            raise ValueError(f'discount_common.{field} 문자열 또는 null 필수')
    for item in d.get('discounts_confirmed', []):
        for field in ('basis', 'applies_to', 'processing'):
            val = item.get(field, common[field])
            if not isinstance(val, str) or not val.strip():
                raise ValueError(f'감면 대상 {item["id"]}: {field} 누락')
        for field in ('documents', 'deadline', 'note'):
            val = item.get(field, common.get(field))
            if val is not None and not isinstance(val, str):
                raise ValueError(f'감면 대상 {item["id"]}: {field} 형식 오류')


def insert_duration_discounts(con, rid, d):
    """감면율·범위·처리·증빙 문구는 JSON에서만 읽어 저장한다."""
    common = d['discount_common']
    excluded = ','.join(d['discount_excluded_fee_types']) or None
    for item in d.get('discounts_confirmed', []):
        cat = item['id']
        con.execute('INSERT OR IGNORE INTO discount_categories(id,name) VALUES(?,?)',
                    (cat, CATEGORY_NAMES[cat]))
        con.execute("""INSERT INTO facility_discounts
          (id,rule_set_id,category_id,percent,basis,applies_to,excluded_from,
           processing,documents,deadline,note,original_group_label,verification_status)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (f'{rid}_{cat}', rid, cat, item['rate_percent'],
           item.get('basis', common['basis']), item.get('applies_to', common['applies_to']),
           excluded, item.get('processing', common['processing']),
           item.get('documents', common.get('documents')),
           item.get('deadline', common.get('deadline')),
           item.get('note', common.get('note')), item['source_label'], 'official_confirmed'))


def load_duration(data_path,db_path):
 d=json.loads(Path(data_path).read_text(encoding='utf-8'))
 validate_shared(d)
 f,s,r=d['facility'],d['source'],d['rule_set']
 p=d['pricing']; t=d['time_policy']; validate_options(d['options'])
 for k in ('reference_minutes','weekday_fee_won','weekend_holiday_fee_won'):
  if type(p[k])!=int or p[k]<0:raise ValueError('요금/시간 유효성 오류: '+k)
 if p['reference_minutes']<=0:raise ValueError('요금 기준 시간 오류')
 # 1시간 요금은 공식 근거가 있을 때에만 저장한다.
 # 2시간 요금의 절반을 임의로 1시간 요금으로 만들어서는 안 된다.
 hourly=p.get('hourly_fee_won')
 weekend_hourly=p.get('hourly_weekend_holiday_fee_won')
 if hourly is not None:
  if type(hourly) is not int or hourly < 0:
   raise ValueError('1시간 평일 요금 오류')
  # 주말이 평일과 같은 요금이라는 근거가 있어도 1시간 요금 자체의
  # 존재가 먼저 확인되어야 한다.
  if weekend_hourly is None and p['weekday_fee_won']==p['weekend_holiday_fee_won']:
   weekend_hourly=hourly
  if type(weekend_hourly) is not int or weekend_hourly < 0:
   raise ValueError('1시간 주말·공휴일 요금 확인 필요')
 elif weekend_hourly is not None:
  raise ValueError('평일 1시간 요금 없이 주말 요금만 등록할 수 없음')
 if p['reference_minutes'] != 120:
  raise ValueError('현재 시간형 적재는 2시간 기준 요금만 지원')
 for key in ('available_start_time','available_end_time'):
  try: dt.datetime.strptime(t[key],'%H:%M')
  except (KeyError, ValueError, TypeError) as exc: raise ValueError('이용 가능시간 오류: '+key) from exc
 if t.get('selection_type')!='flexible_interval': raise ValueError('시간 선택 방식 오류')
 # JSON의 시간 선택 정책을 그대로 저장한다. 미확정(NULL) 값은 임의로 60분으로 채우지 않는다.
 for key in ('daily_limit_minutes', 'max_minutes'):
  if type(t.get(key)) is not int or t[key] <= 0:
   raise ValueError('이용 시간 제한 오류: '+key)
 for key in ('min_minutes', 'step_minutes'):
  value=t.get(key)
  if value is not None and (type(value) is not int or value <= 0):
   raise ValueError('이용 시간 정책 오류: '+key)
 if t['min_minutes'] is not None and t['min_minutes'] > t['max_minutes']:
  raise ValueError('최소 이용시간이 최대 이용시간보다 큼')
 # 현재 적재기는 1시간/2시간 요금 규칙만 제공한다. 180분 허용 정책은
 # 저장할 수 있지만 180분의 요금을 만들어낼 수는 없다.
 if t['max_minutes'] < p['reference_minutes'] or t['daily_limit_minutes'] < p['reference_minutes']:
  raise ValueError('2시간 기본요금 규칙과 이용 시간 제한이 충돌')
 if t['min_minutes'] is not None and t['min_minutes'] > p['reference_minutes']:
  raise ValueError('2시간 기본요금 규칙보다 최소 이용시간이 큼')
 if len({x['id'] for x in d['discounts_pending']})!=len(d['discounts_pending']):raise ValueError('중복 감면 유형')
 if len({x['id'] for x in d.get('discounts_confirmed',[])})!=len(d.get('discounts_confirmed',[])):raise ValueError('중복 감면')
 for x in d.get('discounts_confirmed',[]):
  if x['id'] not in ('national_merit','independence_merit','may18_merit','special_mission_merit','war_veteran','disabled','multi_child','low_income'): raise ValueError('알 수 없는 확정 감면 대상: '+x['id'])
  if type(x['rate_percent']) is not int or not 0<=x['rate_percent']<=100:raise ValueError('잘못된 감면율')
 validate_duration_discounts(d)
 con=sqlite3.connect(db_path);con.execute('PRAGMA foreign_keys=ON')
 try:
  con.executescript((ROOT/'schema.sql').read_text(encoding='utf-8'))
  with con:
   rid = insert_shared_records(con, d)
   con.execute('INSERT INTO pricing_rules VALUES(?,?,?,?,?,?,?,?,?,?)',(f'{rid}_2hours',rid,'flexible_interval',None,None,None,p['reference_minutes'],p['weekday_fee_won'],p['weekend_holiday_fee_won'],0))
   if hourly is not None:
    con.execute('INSERT INTO pricing_rules VALUES(?,?,?,?,?,?,?,?,?,?)',(f'{rid}_1hour',rid,'flexible_interval',None,None,None,60,hourly,weekend_hourly,0))
   insert_options(con,rid,d['options'])
   con.execute('INSERT INTO time_selection_policies VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,t['selection_type'],t['available_start_time'],t['available_end_time'],t.get('min_minutes'),t['max_minutes'],t.get('step_minutes'),t['daily_limit_minutes'],t['status'],t['note']))
   insert_duration_discounts(con, rid, d)
   insert_refunds_and_reservation(con, rid, d)
 finally:con.close()



def load(data_path, db_path=ROOT/'facilities.sqlite3'):
    """자동 형식 판별: 고정회차형 / 기간형. 잘못된 입력은 트랜잭션으로 롤백."""
    data_path=Path(data_path)
    d=json.loads(data_path.read_text(encoding='utf-8'))
    if 'slots' in d and 'pricing' not in d:
        load_fixed(data_path, db_path)
    elif 'pricing' in d and 'slots' not in d:
        load_duration(data_path, db_path)
    else:
        raise ValueError('알 수 없는 자료 형식: slots 또는 pricing 중 하나만 필요')


def load_many(paths, db_path=ROOT/'facilities.sqlite3'):
    """모든 파일 선검사 후 임시 DB에서 갱신해 전체 성공 시에만 원본 교체."""
    import os, tempfile
    paths=[Path(p) for p in paths]
    # SQLite 완결성 및 WAL 고려해 SQLite 백업 API로 임시 복사
    db_path=Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=db_path.parent) as temp:
        staged=Path(temp)/'staged.sqlite3'
        if db_path.exists():
            # sqlite3.Connection.__exit__ commits/rolls back, but does NOT close.
            # Windows will not replace a DB file still held open by SQLite.
            with closing(sqlite3.connect(db_path)) as original, closing(sqlite3.connect(staged)) as draft:
                original.backup(draft)
        for p in paths: load(p, staged)
        with closing(sqlite3.connect(staged)) as con:
            con.execute('PRAGMA foreign_keys=ON')
            if con.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('외래키 무결성 검사 실패')
            if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('DB 무결성 검사 실패')
        # 모든 자체 연결을 닫은 뒤 파일 교체. 외부 SQLite 뷰어가 열어
        # 두었다면 Windows가 여전히 교체를 차단할 수 있으므로 안내한다.
        try:
            os.replace(staged,db_path)
        except PermissionError as exc:
            raise PermissionError(
                f'DB 파일을 교체할 수 없습니다: {db_path}. '
                'SQLite Viewer/DB Browser, VS Code의 DB 연결 또는 다른 프로그램에서 '
                '이 DB를 열어 두었다면 연결을 닫고 다시 실행하세요.'
            ) from exc


if __name__=='__main__':
    p=argparse.ArgumentParser(description='고정 회차/시간당 요금 공통 적재 도구')
    p.add_argument('--data', nargs='+', required=True, help='원본 JSON 한 개 이상')
    p.add_argument('--db',default=str(ROOT/'facilities.sqlite3'))
    a=p.parse_args()
    load_many(a.data,a.db)
    print('적재 및 무결성 검증 성공:',a.db,'/',len(a.data),'개 시설 자료')
