"""시설 원본 JSON -> SQLite. 원자적 재적재와 공통 감면 분류 적용."""
import argparse
import datetime as dt
import json
import sqlite3
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

def validate(d):
    for field in ('facility','source','rule_set','slots','options','discounts','discount_common','refunds','reservation'):
        if field not in d: raise ValueError(f'필수 키 누락: {field}')
    f,s,r = d['facility'], d['source'], d['rule_set']
    for k in ('id','name','facility_type','address','booking_url'):
        if not isinstance(f.get(k),str) or not f[k].strip(): raise ValueError(f'facility.{k} 누락')
    for k in ('id','url','title','checked_on'):
        if not isinstance(s.get(k),str) or not s[k].strip(): raise ValueError(f'source.{k} 누락')
    for v in (s['checked_on'],r['effective_from'],r['effective_to']): dt.date.fromisoformat(v)
    if r['effective_from']>r['effective_to']: raise ValueError('규정 기간 역전')
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
    for refund in d['refunds']:
        if refund['rate'] is not None and (type(refund['rate']) is not int or not 0<=refund['rate']<=100): raise ValueError('환불률 오류')
    return d

def load_fixed(data_path, db_path):
    d=validate(json.loads(Path(data_path).read_text(encoding='utf-8')))
    db_path=Path(db_path)
    # 새로운 DB에만 schema 생성. 실제 적재는 한 번의 트랜잭션으로 진행.
    con=sqlite3.connect(db_path)
    con.execute('PRAGMA foreign_keys=ON')
    try:
        con.executescript((ROOT/'schema.sql').read_text(encoding='utf-8'))
        with con:
            f,s,r=d['facility'],d['source'],d['rule_set']; rid=r['id']
            # REPLACE 시설행은 FK 손상을 유발할 수 있어 UPSERT로 유지
            con.execute('''INSERT INTO facilities(id,name,facility_type,address,phone,booking_url,open_time,close_time,holiday_note)
                VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,facility_type=excluded.facility_type,address=excluded.address,
                phone=excluded.phone,booking_url=excluded.booking_url,open_time=excluded.open_time,
                close_time=excluded.close_time,holiday_note=excluded.holiday_note''',
                tuple(f.get(k) for k in ('id','name','facility_type','address','phone','booking_url','open_time','close_time','holiday_note')))
            con.execute('''INSERT INTO sources(id,url,title,checked_on,verification_level,note)
                VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                url=excluded.url,title=excluded.title,checked_on=excluded.checked_on,
                verification_level=excluded.verification_level,note=excluded.note''',
                tuple(s.get(k) for k in ('id','url','title','checked_on','verification_level','note')))
            con.execute('DELETE FROM rule_sets WHERE id=?',(rid,))
            con.execute('INSERT INTO rule_sets(id,facility_id,source_id,effective_from,effective_to,status) VALUES(?,?,?,?,?,?)',
                (rid,f['id'],s['id'],r['effective_from'],r['effective_to'],r['status']))
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
            for rr in d['refunds']:
                con.execute('INSERT INTO refund_rules VALUES(?,?,?,?,?,?,?,?,?)',
                    (f'{rid}_{rr["id"]}',rid,rr['reason'],rr['min'],rr['max'],rr['rate'],rr['channel'],rr['condition'],
                     'confirmed'))
            a=d['reservation']
            con.execute('INSERT INTO reservation_rules VALUES(?,?,?,?,?)',
                (rid,a['online_open_days_before'],a['online_close_days_before'],a['normal_cancel_online_min_days_before'],a['closure_note']))
    finally:
        con.close()


def load_duration(data_path,db_path):
 d=json.loads(Path(data_path).read_text(encoding='utf-8'))
 f,s,r=d['facility'],d['source'],d['rule_set']
 assert r['effective_from']<=r['effective_to']
 dt.date.fromisoformat(r['effective_from']);dt.date.fromisoformat(r['effective_to'])
 p=d['pricing']; t=d['time_policy']; validate_options(d['options'])
 for k in ('reference_minutes','weekday_fee_won','weekend_holiday_fee_won'):
  if type(p[k])!=int or p[k]<0:raise ValueError('요금/시간 유효성 오류: '+k)
 if p['reference_minutes']<=0:raise ValueError('요금 기준 시간 오류')
 if len({x['id'] for x in d['discounts_pending']})!=len(d['discounts_pending']):raise ValueError('중복 감면 유형')
 if len({x['id'] for x in d.get('discounts_confirmed',[])})!=len(d.get('discounts_confirmed',[])):raise ValueError('중복 감면')
 for x in d.get('discounts_confirmed',[]):
  if x['id'] not in ('national_merit','independence_merit','may18_merit','special_mission_merit','war_veteran','disabled','multi_child','low_income'): raise ValueError('알 수 없는 확정 감면 대상: '+x['id'])
  if type(x['rate_percent']) is not int or not 0<=x['rate_percent']<=100:raise ValueError('잘못된 감면율')
 if d.get('discount_calculation_policy') not in ('representative_full_court',):raise ValueError('감면 계산 기준 오류')
 con=sqlite3.connect(db_path);con.execute('PRAGMA foreign_keys=ON')
 try:
  con.executescript((ROOT/'schema.sql').read_text(encoding='utf-8'))
  with con:
   con.execute('''INSERT INTO facilities(id,name,facility_type,address,phone,booking_url,open_time,close_time,holiday_note)
    VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,facility_type=excluded.facility_type,address=excluded.address,phone=excluded.phone,booking_url=excluded.booking_url,open_time=excluded.open_time,close_time=excluded.close_time,holiday_note=excluded.holiday_note''',
    (f['id'],f['name'],f['facility_type'],f['address'],f['phone'],f['booking_url'],f['open_time'],f['close_time'],f['holiday_note']))
   con.execute('''INSERT INTO sources(id,url,title,checked_on,verification_level,note) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET url=excluded.url,title=excluded.title,checked_on=excluded.checked_on,verification_level=excluded.verification_level,note=excluded.note''',tuple(s[k] for k in ('id','url','title','checked_on','verification_level','note')))
   rid=r['id'];con.execute('DELETE FROM rule_sets WHERE id=?',(rid,))
   con.execute('INSERT INTO rule_sets(id,facility_id,source_id,effective_from,effective_to,status) VALUES(?,?,?,?,?,?)',(rid,f['id'],s['id'],r['effective_from'],r['effective_to'],r['status']))
   con.execute('INSERT INTO pricing_rules VALUES(?,?,?,?,?,?,?,?,?,?)',('gudeok_2hours',rid,'flexible_interval',None,None,None,p['reference_minutes'],p['weekday_fee_won'],p['weekend_holiday_fee_won'],0))
   con.execute('INSERT INTO pricing_rules VALUES(?,?,?,?,?,?,?,?,?,?)',('gudeok_1hour',rid,'flexible_interval',None,None,None,60,p['hourly_fee_won'],p['hourly_fee_won'],0))
   insert_options(con,rid,d['options'])
   con.execute('INSERT INTO time_selection_policies VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,t['selection_type'],t['available_start_time'],t['available_end_time'],60,120,60,t['daily_limit_minutes'],t['status'],t['note']))
   for x in d.get('discounts_confirmed',[]):
    cat=x['id']
    if cat not in ('national_merit','independence_merit','may18_merit','special_mission_merit','war_veteran','disabled','multi_child','low_income'):raise ValueError('알 수 없는 감면 대상')
    con.execute('INSERT OR IGNORE INTO discount_categories(id,name) VALUES(?,?)',(cat,CATEGORY_NAMES[cat]))
    con.execute('''INSERT INTO facility_discounts(id,rule_set_id,category_id,percent,basis,applies_to,excluded_from,processing,documents,deadline,note,original_group_label,verification_status)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(rid+'_'+cat,rid,cat,x['rate_percent'],d['discount_calculation_policy'],'base_court_fee_only','lighting_fee','pay_full_then_refund','사용일 당일 관제실 증빙 제시, 감경대상자 확인서 작성 제출','이용일 당일 이용 전 또는 후','예약 대표자 본인이 감면 자격을 증빙한 경우에만 코트 기본 이용료의 50% 반환. 동반자 자격만으로는 감면하지 않음. 조명료 제외.',x['source_label'],'official_confirmed'))
   for x in d['refunds']:
    con.execute('INSERT INTO refund_rules VALUES(?,?,?,?,?,?,?,?,?)',(rid+'_'+x['id'],rid,x['reason'],x['min'],x['max'],x['rate'],x['channel'],x['condition'],'confirmed'))
   a=d['reservation']
   con.execute('INSERT INTO reservation_rules VALUES(?,?,?,?,?)',(rid,a['online_open_days_before'],a['online_close_days_before'],a['normal_cancel_online_min_days_before'],a['closure_note']))
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
            with sqlite3.connect(db_path) as original, sqlite3.connect(staged) as draft:
                original.backup(draft)
        for p in paths: load(p, staged)
        with sqlite3.connect(staged) as con:
            con.execute('PRAGMA foreign_keys=ON')
            if con.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('외래키 무결성 검사 실패')
            if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('DB 무결성 검사 실패')
        # 복사+교체: 경로 사용 중인 연결이 없다면 원자적 교체
        os.replace(staged,db_path)


if __name__=='__main__':
    p=argparse.ArgumentParser(description='고정 회차/시간당 요금 공통 적재 도구')
    p.add_argument('--data', nargs='+', required=True, help='원본 JSON 한 개 이상')
    p.add_argument('--db',default=str(ROOT/'facilities.sqlite3'))
    a=p.parse_args()
    load_many(a.data,a.db)
    print('적재 및 무결성 검증 성공:',a.db,'/',len(a.data),'개 시설 자료')
